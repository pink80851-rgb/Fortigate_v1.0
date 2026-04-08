import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from app import app, db, VIPRequest  # 匯入你的 Flask 實例與模型
from mail_tools import send_expiry_warning_mail # 記得在 mail_tools 實作這個函數

load_dotenv()

def run_daily_check():
    with app.app_context():
        # 設定預警天數
        warning_days = int(os.getenv('EXPIRY_WARNING_DAYS', 10))
        
        # 計算目標日期：今天的 10 天後
        # 例如今天 4/1，目標日期就是 4/11
        target_date_str = (datetime.now() + timedelta(days=warning_days)).strftime('%Y-%m-%d')
        
        # SQL 查詢：找出狀態為已開通，且到期日「當天」剛好是目標日期的單子
        expiring_reqs = VIPRequest.query.filter(
            VIPRequest.status == 3,
            db.func.date(VIPRequest.expire_date) == target_date_str
        ).all()

        if not expiring_reqs:
            print(f"[{datetime.now()}] 沒有即將過期的 VIP 申請。")
            return

        admin_email = os.getenv('ADMIN_EMAIL')

        for req in expiring_reqs:
            print(f"🚩 偵測到過期預警：REQ-{req.id:04d} ({req.applicant})")
            success = send_expiry_warning_mail(
                to_email=req.email,
                admin_email=admin_email,
                ticket_id=f"REQ-{req.id:04d}",
                expiry_date=req.expire_date
            )
            if success:
                print(f"✅ 預警郵件已發送至 {req.email}")
            else:
                print(f"❌ 郵件發送失敗")

if __name__ == "__main__":
    run_daily_check()