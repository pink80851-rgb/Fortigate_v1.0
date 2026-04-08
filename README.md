# FortiGate VIP 自動化申請與管理系統
這是一個基於 Flask 開發的自動化維運平台，專門用於簡化企業內部的 FortiGate VIP 申請流程。系統整合了 資料庫紀錄、自動資源分配 (IP/Port)、Word 申請單自動填寫、郵件審核通知 以及 設備 API 自動寫入。

🏗️ 系統核心功能
自動化資源管理：從指定的 VIP_EXT_IP_PREFIX 網段中，自動計算並分配下一個可用的外部 IP。

文件自動化：申請提交後自動產生 Word 格式申請單 (.docx)。

三階段流程管理：

Phase 1 (待審核)：使用者填寫申請單。

Phase 2 (待開通)：MIS 分配 IP 資源並寄送初步通知。

Phase 3 (已結案)：主管點擊核准後，系統自動將設定寫入 FortiGate 防火牆。

設備連動：支援 VIP 建立、自動加入群組 (VIP Group) 以及權限回收 (Delete)。

📁 目錄結構
Plaintext
Fortigate_v1.0/
├── app.py              # 系統指揮中心 (Flask 主程式)
├── forti_mod.py        # FortiGate Connector (設備連動邏輯)
├── fortigate_tools.py  # 資源管理工具 (IP/Port 計算)
├── mail_tools.py       # 郵件寄送工具 (SMTP)
├── template.docx       # Word 申請單範本 (內含變數標籤)
├── config/
│   └── .env.example    # 環境變數設定範本
├── instance/
│   └── vip_management.db # SQLite 資料庫 (自動產生)
├── storage/            # 儲存已產出的申請單檔案
├── templates/          # 前端 HTML 頁面 (index, admin, login...)
└── utils/
    └── word_tools.py   # Word 填充與產出工具
🛠️ 安裝與啟動
1. 環境初始化
Bash
# 建議建立虛擬環境
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# 安裝依賴套件
pip install flask flask_sqlalchemy python-dotenv python-docx requests
2. 環境變數設定
請將 config/.env.example 複製到根目錄更名為 .env，並填入機房設備資訊：

Bash
# FortiGate 設定
FORTIGATE_IP=192.168.x.x
FORTIGATE_TOKEN=your_secure_token
VIP_EXT_IP_PREFIX=192.168.150 # 欲分配的對外 IP 網段
VIP_GROUP_NAME=VIP_AUTO_GROUP # 防火牆上的 VIP 群組名稱

# 郵件設定
MAIL_SERVER=smtp.yourcompany.com
MAIL_SENDER=mis@yourcompany.com
3. 啟動程式
Bash
python app.py
使用者申請介面: http://localhost:5000/

管理後台: http://localhost:5000/admin (預設帳密: admin / 123456)

🔄 核心 API 流程說明
1. submit_apply (提交申請)
接收前端 Form Data。

產生唯一的 ticket_id (格式: REQ-日期-隨機碼)。

計算過期日期 (預設 180 天)。

調用 word_tools.py 產出第一版申請單。

2. assign_request (MIS 資源分配)
呼叫 FortiManager 檢查資料庫中已使用的 IP 與 Port。

自動抓取下一個可用 IP。

更新 Word 檔案並寄送帶有附件的審核通知信。

3. approve_request (自動開通寫入)
關鍵動作：呼叫 FortiGateConnector 的 create_vip_and_attach 方法。

自動在防火牆建立 VIP 物件並將其加入指定群組。

發送「開通成功」通知信給申請人。

🔒 安全提醒
.gitignore: 務必確保 .env 與 instance/ 被排除在 Git 追蹤外。

資料備份: 建議定期備份 vip_management.db 與 storage/ 資料夾。

時區: 本系統預設使用 datetime.now()，部署時請確保伺服器時區設定正確（建議為台北時間）。
