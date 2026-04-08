import requests
import urllib3
import json
import os
from dotenv import load_dotenv

# 加載環境變數
load_dotenv()

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class FortiManager:
    def __init__(self, ip=None, token=None):
        """
        初始化時優先使用參數，否則讀取 env。
        """
        self.ip = ip or os.getenv('FORTIGATE_IP')
        self.token = token or os.getenv('FORTIGATE_TOKEN')
        
        # 取得 VIP 列表的 API
        self.api_url = f"https://{self.ip}/api/v2/cmdb/firewall/vip"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_current_vips(self, target_prefix):
        """
        抓取設備上現有的 VIP，並根據 target_prefix (如 192.168.150) 進行過濾。
        """
        try:
            response = requests.get(self.api_url, headers=self.headers, verify=False, timeout=10)
            if response.status_code == 200:
                all_vips = response.json().get('results', [])
                vips_data = []
                for vip in all_vips:
                    m_ip_list = vip.get("mappedip", [])
                    m_ip = m_ip_list[0].get("range") if m_ip_list else ""
                    
                    # --- 核心修正：動態匹配 Prefix ---
                    if target_prefix in str(m_ip):
                        vips_data.append({
                            "mapped_ip": m_ip,
                            "ext_port": str(vip.get("extport", ""))
                        })
                return vips_data
            return []
        except Exception as e:
            print(f"❌ FortiGate 連線出錯: {e}")
            return []

    def get_next_resources(self, num_ports, db_used_ips, db_used_ports, target_prefix=None):
        """
        自動分配 IP 與 Ports。
        target_prefix: 例如 '192.168.150'，由 app.py 從 env 傳入。
        """
        # 確保 prefix 存在
        prefix = target_prefix or os.getenv('VIP_EXT_IP_PREFIX', '192.168.150')
        
        vips_data = self.get_current_vips(prefix)
        
        # 整合設備端與資料庫端已使用的資源
        hw_used_ips = [v['mapped_ip'] for v in vips_data]
        hw_used_ports = [v['ext_port'] for v in vips_data]
        
        total_used_ips = set(hw_used_ips + db_used_ips)
        total_used_ports = set(hw_used_ports + db_used_ports)

        # 1. 尋找下一個空 IP (從第 10 碼開始到 254)
        next_ip = None
        for i in range(10, 255):
            ip = f"{prefix}.{i}"
            if ip not in total_used_ips:
                next_ip = ip
                break

        # 2. 尋找指定數量的空 Port (範圍從 60000 開始)
        next_ports = []
        for p in range(60000, 61001):
            p_str = str(p)
            if p_str not in total_used_ports:
                next_ports.append(p_str)
            
            if len(next_ports) == num_ports:
                break
        
        if not next_ip or len(next_ports) < num_ports:
            raise Exception(f"資源不足：網段 {prefix} 無法分配 IP 或足夠的 Port")

        return next_ip, next_ports