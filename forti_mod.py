import requests
import urllib3
import json
import os

# 停用 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class FortiGateConnector:
    def __init__(self, ip, token):
        """
        初始化 FortiGate 連接器
        """
        self.base_url = f"https://{ip}/api/v2/cmdb"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        # 這裡也可以考慮從環境變數讀取，或者讓它成為一個參數
        self.fortigate_public_ip = ip 

    def create_vip_and_attach(self, vip_name, mapped_ip, ext_port_str, int_port_str, group_name):
        e_ports = str(ext_port_str).split(',')
        i_ports = str(int_port_str).split(',')
        """
        建立 VIP 並加入群組
        """
        created_vips = []
        error_logs = []

        # ✅ 修正點 1：對應到 __init__ 裡的名稱 fortigate_public_ip
        # 如果環境變數沒設定，就拿初始化傳進來的 IP
        ext_ip = os.getenv('VIP_PUBLIC_IP') or self.fortigate_public_ip
        
        # ✅ 修正點 2：介面名稱建議也給個保險
        ext_interface = os.getenv('FORTIGATE_INTERFACE', 'wan1')
        
        for e_p, i_p in zip(e_ports, i_ports):
            e_p = e_p.strip() 
            i_p = i_p.strip()
            if not i_p: continue
            
            specific_vip_name = f"{vip_name}_{i_p}"
            vip_url = f"{self.base_url}/firewall/vip"
            
            # --- 核心修正：extip 不再寫死 ---
            vip_payload = {
                "name": specific_vip_name,
                "extip": ext_ip,  # 這裡改用變數
                "mappedip": [{"range": mapped_ip}],
                "extintf": ext_interface,
                "portforward": "enable",
                "extport": int(e_p),
                "mappedport": int(i_p),
                "comment": "Created by SRE Automation System"
            }
            
            try:
                json_bytes = json.dumps(vip_payload).encode('utf-8')
                resp = requests.post(
                    vip_url, 
                    headers=self.headers, 
                    data=json_bytes,
                    verify=False,
                    timeout=10
                )
                
                if resp.status_code == 200:
                    created_vips.append(specific_vip_name)
                else:
                    error_msg = f"VIP {specific_vip_name} 失敗: {resp.text}"
                    error_logs.append(error_msg)
            except Exception as e:
                error_logs.append(f"連線異常: {str(e)}")

        if not created_vips:
            return False, f"所有 VIP 建立皆失敗: {'; '.join(error_logs)}"

        # 2. 將成功建立的 VIP 加入群組
        grp_url = f"{self.base_url}/firewall/vipgrp/{group_name}"
        
        try:
            get_grp = requests.get(grp_url, headers=self.headers, verify=False, timeout=10)
            
            if get_grp.status_code == 200:
                # 這裡要處理 results 可能為空的情況
                res = get_grp.json().get('results', [])
                if not res: return False, f"群組 {group_name} 存在但無法讀取資料"
                
                current_data = res[0]
                members = current_data.get('member', [])
                
                existing_names = [m['name'] for m in members]
                for name in created_vips:
                    if name not in existing_names:
                        members.append({"name": name})
                
                put_payload = {"member": members}
                put_bytes = json.dumps(put_payload).encode('utf-8')
                
                put_resp = requests.put(
                    grp_url, 
                    headers=self.headers, 
                    data=put_bytes, 
                    verify=False,
                    timeout=10
                )
                
                if put_resp.status_code == 200:
                    return True, f"成功開通: {', '.join(created_vips)}"
                else:
                    return False, f"VIP 建立成功但群組掛載失敗: {put_resp.text}"
            else:
                return False, f"找不到目標群組 {group_name}"
                
        except Exception as e:
            return False, f"群組操作過程發生異常: {str(e)}"
        
    def delete_vip_from_fortigate(self, vip_name, group_name):
        
        """
        刪除 FortiGate 上的 VIP 物件
        注意：如果 VIP 正在被群組 (vipgrp) 使用，直接刪除 VIP 可能會失敗。
        所以嚴謹的做法是先從群組移除，再刪除 VIP 本體。
        """
        import requests
        # 1. 取得 API 基礎路徑
        # 先刪除 VIP 本體 (如果 FortiGate 設定了 'allow-matching-objects'，
        # 有時可以直接刪，但標準做法是先從 Policy 或 Group 移除)
        url = f"https://{self.fortigate_public_ip}/api/v2/cmdb/firewall/vip/{vip_name}"
        
        try:
            # 執行 DELETE 請求
            response = requests.delete(
                url, 
                headers=self.headers, # 使用類別內定義好的 headers
                verify=False, 
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"🗑️ 設備上的 VIP {vip_name} 已成功刪除")
                return True, "Success"
            else:
                return False, f"設備回傳錯誤 ({response.status_code}): {response.text}"
                
        except Exception as e:
            return False, f"連線異常: {str(e)}"    
