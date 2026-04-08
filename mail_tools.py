import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formataddr
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 加載環境變數
load_dotenv()

def send_approval_mail(to_email, ticket_id, doc_path=None):
    """
    發送預配通知信。
    如果 doc_path 為 None，則僅發送單號通知信。
    如果 doc_path 有值且檔案存在，則夾帶 Word 附件。
    """
    # 1. 從環境變數讀取配置
    smtp_server = os.getenv('MAIL_SERVER', '192.168.20.1')
    try:
        smtp_port = int(os.getenv('MAIL_PORT', 25))
    except (TypeError, ValueError):
        smtp_port = 25
        
    sender_email = os.getenv('MAIL_SENDER', 'FortigateVIP@meritlilin.com.tw')
    sender_name = os.getenv('MAIL_SENDER_NAME', 'FortigateVIP管理員')

    # 2. 判斷郵件標題與內文邏輯 (根據有無附件)
    if doc_path and os.path.exists(doc_path):
        subject = f"【待簽核】VIP 申請預配通知 - 單號：{ticket_id}"
        body_content = f"""
    您的網路 VIP 申請案（單號：{ticket_id}）已由資訊室完成預配。
    
    【後續作業步驟】：
    1. 請下載本郵件附件之「申請單」。
    2. 列印並完成「紙本簽名」。
    3. 將紙本交回五股資訊室。
    
    待收到紙本後，我們將正式為您開通 FortiGate 權限。"""
    else:
        subject = f"【申請成功】您的 VIP 申請已受理 - 單號：{ticket_id}"
        body_content = f"""
    您的網路 VIP 申請案已成功提交。
    
    【查詢資訊】：
    - 申請單號：{ticket_id}
    
    您可以至系統輸入此單號查詢目前的審核進度。"""

    body = f"""
    您好，
    
    {body_content}
    
    ---
    此為系統自動發送，請勿直接回覆。
    """

    # 3. 建立郵件容器
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = formataddr((sender_name, sender_email))
    msg['To'] = to_email
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    # 4. 處理附件 (僅在 doc_path 存在時執行)
    if doc_path and os.path.exists(doc_path):
        try:
            with open(doc_path, "rb") as f:
                filename = os.path.basename(doc_path)
                part = MIMEApplication(f.read(), Name=filename)
                part['Content-Disposition'] = f'attachment; filename="{filename}"'
                msg.attach(part)
                print(f"📎 郵件附件已就緒：{filename}")
        except Exception as e:
            print(f"❌ 讀取附件失敗: {e}")
    else:
        print(f"ℹ️ 本次郵件不包含附件 (單號：{ticket_id})")

    # 5. 執行發送
    try:
        print(f"📡 正在連線至 Mail Server ({smtp_server}:{smtp_port})...")
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.send_message(msg)
        print(f"✅ 郵件已成功發送至：{to_email}")
        return True
    except Exception as e:
        print(f"❌ Mail Error: {e}")
        return False

def send_final_notification(to_email, ticket_id, vip_info, expiry_date):
    """
    發送正式開通通知信
    """
    smtp_server = os.getenv('MAIL_SERVER', '192.168.20.1')
    sender_email = os.getenv('MAIL_SENDER', 'FortigateVIP@meritlilin.com.tw')
    
    subject = f"【正式開通】您的 VIP 服務已啟用 - 單號：{ticket_id}"
    expiry_str = expiry_date.strftime('%Y-%m-%d')
    
    body = f"""
    您好，
    
    您的網路 VIP 申請案（單號：{ticket_id}）已正式完成設備設定。
    
    【連線資訊】：
    - 外部連線位址：{vip_info}
    
    【服務效期】：
    - 開通日期：{datetime.now().strftime('%Y-%m-%d')}
    - 到期日期：{expiry_str} (有效期限 180 天)
    
    請注意，若到期後仍有需求，請於到期前 7 天重新提出申請。
    系統將於到期當日自動回收權限。
    
    ---
    此為系統自動發送，請勿直接回覆。
    """
    
    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = formataddr(('SRE Automation System', sender_email))
    msg['To'] = to_email
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP(smtp_server, 25, timeout=10) as server:
            server.send_message(msg)
        print(f"✅ 正式開通信已發送：{to_email}")
        return True
    except Exception as e:
        print(f"❌ Final Mail Error: {e}")
        return False