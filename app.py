import os
import sys
import random
from datetime import datetime, timedelta

# 1. 先載入環境變數工具
from dotenv import load_dotenv
load_dotenv()  # <--- 關鍵！這行必須在所有自定義模組之前執行

# 2. 載入 Flask 與標準套件
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func

# 3. 載入 Word 工具
from docx import Document
from docx.shared import Pt          
from docx.oxml.ns import qn        
# ... (docx 相關 import)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TEMPLATE_PATH = os.path.join(BASE_DIR, 'template.docx')
STORAGE_FOLDER = os.path.join(BASE_DIR, 'storage')
# 4. 最後才載入你的自定義工具
from utils.word_tools import handle_word_file
from forti_mod import FortiGateConnector
from fortigate_tools import FortiManager
from mail_tools import send_approval_mail, send_final_notification


app = Flask(__name__)

# --- 從環境變數讀取配置 ---
# FortiGate 相關
FG_IP = os.getenv('FORTIGATE_IP')
FG_TOKEN = os.getenv('FORTIGATE_TOKEN')
FG_GROUP = os.getenv('VIP_GROUP_NAME', 'VIP_MANAGED_BY_AUTO_SYSTEM')
VIP_PREFIX = os.getenv('VIP_EXT_IP_PREFIX', '192.168.150')

# Flask 安全金鑰 (若 env 沒設定則使用預設值)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'sre_default_secret_key_12345')

# --- 2. 目錄與資料庫設定 ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
STORAGE_FOLDER = os.path.join(BASE_DIR, 'storage')
if not os.path.exists(STORAGE_FOLDER):
    os.makedirs(STORAGE_FOLDER)

# 資料庫路徑也可從 env 讀取
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(BASE_DIR, 'vip_management.db')}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- 3. 定義資料結構 (VIPRequest) ---
class VIPRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(20), unique=True)
    id = db.Column(db.Integer, primary_key=True)
    applicant = db.Column(db.String(50))
    email = db.Column(db.String(100))
    dept = db.Column(db.String(50))
    floor = db.Column(db.String(10))
    reason = db.Column(db.Text)
    int_ip = db.Column(db.String(20))
    int_port = db.Column(db.String(100))  
    ext_ip = db.Column(db.String(20))
    ext_port = db.Column(db.String(20))   
    file_path = db.Column(db.String(200))
    status = db.Column(db.Integer, default=1) # 1:審核中, 2:待開通, 3:已結案
    created_at = db.Column(db.DateTime, default=datetime.now)
    expire_date = db.Column(db.DateTime)
    ticket_id = db.Column(db.String(20), unique=True)
# --- 5. 路由設定 ---
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/submit_apply', methods=['POST'])
def submit_apply():
    # 1. 取得前端傳來的 Email (這行最重要，不然寄不了信)
    user_email = request.form.get('email') 
    
    # 2. 產生單號
    ticket_id = f"REQ-{datetime.now().strftime('%Y%m%d%H%M')}-{random.randint(100,999)}"

    # 3. 建立物件時把所有資料塞進去
    new_req = VIPRequest(
        ticket_id = ticket_id,
        applicant = request.form.get('applicant'),
        email = user_email,
        dept = request.form.get('dept'),         # <--- 補上
        floor = request.form.get('floor'),       # <--- 補上
        reason = request.form.get('reason'),     # <--- 補上
        int_ip = request.form.get('int_ip'),     # <--- 補上 (對應 HTML 的內網 IP)
        int_port = request.form.get('int_port'), # <--- 補上 (對應 HTML 的內網 Port)
        status = 1,
        created_at = datetime.now(),
        expire_date = datetime.now() + timedelta(days=180)
    )

    # 4. 存入資料庫
    db.session.add(new_req)
    db.session.commit() 

    # 5. 寄送郵件 (在 Word 產生前先寄，確保單號通知最優先)
    # 使用剛才抓到的 user_email
    if user_email:
        print(f"DEBUG: 準備寄信給 {user_email}")
        send_approval_mail(
            to_email=user_email, 
            ticket_id=ticket_id, 
            doc_path=None 
        )

    # 6. 處理 Word 文件 (背景產檔)
    # 6. 處理 Word 文件 (背景產檔)
    try:
        # 照順序丟進去：資料，範本路徑，儲存資料夾
        path = handle_word_file(
            new_req, 
            os.path.join(BASE_DIR, 'template.docx'), 
            STORAGE_FOLDER
        )

        if path:
            new_req.file_path = path
            db.session.commit()  # <--- 產生路徑後要再 Commit 一次！
            
    except Exception as e:
        print(f"Word 產出失敗: {e}")

    return jsonify({"status": "success", "req_no": ticket_id})
@app.route('/admin')
def admin():
    if not session.get('is_admin'): 
        return redirect(url_for('login'))
    all_requests = VIPRequest.query.order_by(VIPRequest.created_at.desc()).all()
    return render_template('admin.html', requests=all_requests)
@app.route('/assign_request/<int:id>', methods=['POST'])
def assign_request(id):
    req = VIPRequest.query.get_or_404(id)
    if req.status >= 2: 
        return jsonify({"status": "error", "message": "此單已分配過資源"})

    try:
        # 使用 env 中的 FG_IP 和 FG_TOKEN
        fm = FortiManager(FG_IP, FG_TOKEN) 
        pending_reqs = VIPRequest.query.filter(VIPRequest.status == 2).all()
        db_used_ips = [r.int_ip for r in pending_reqs if r.int_ip]
        db_used_ports = []
        for r in pending_reqs:
            if r.ext_port:
                db_used_ports.extend(r.ext_port.split(','))

        num_needed = len(req.int_port.split(',')) if req.int_port else 0
        
        # 傳入 env 中的 VIP_PREFIX 給工具模組
        next_ip, next_ports = fm.get_next_resources(num_needed, db_used_ips, db_used_ports, target_prefix=VIP_PREFIX)
        req.int_ip = next_ip
        req.ext_port = ",".join(next_ports)
        req.status = 2 
        db.session.commit()
        db.session.refresh(req)
        handle_word_file(req, TEMPLATE_PATH, STORAGE_FOLDER)
        
        # 寄信通知，帶入附件
        send_approval_mail(req.email, req.ticket_id, req.file_path)

        return jsonify({
            "status": "success", 
            "message": f"資源分配完成並已發信！分配 IP: {next_ip}"
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)})
@app.route('/approve_request/<int:id>', methods=['POST'])
def approve_request(id):
    # 1. 從資料庫讀取物件
    req = db.session.get(VIPRequest, id)
    if not req: 
        return jsonify({"status": "error", "message": "找不到此工單"})

    # 確保 IP 存在才進行切分，避免 split 報錯
    if not req.int_ip:
        return jsonify({"status": "error", "message": "工單缺少內部 IP 資訊"})

    # 2. 準備命名 (去除空格，確保符合 FortiGate 命名規則)
    ip_last_octet = req.int_ip.split('.')[-1]
    base_name = req.ticket_id

    # 3. 從環境變數直接讀取設定，避免變數未定義
    f_ip = os.getenv('FORTIGATE_IP', '192.168.20.1')
    f_token = os.getenv('FORTIGATE_TOKEN')
    f_group = os.getenv('VIP_GROUP_NAME', 'VIP_MANAGED_BY_AUTO_SYSTEM')

    # 4. 執行 FortiGate 寫入
    forti = FortiGateConnector(ip=f_ip, token=f_token)
    
    # 注意：確認 forti_mod 內的 self.ip 是否已改為 self.fortigate_public_ip
    success, msg = forti.create_vip_and_attach(
        vip_name=base_name,
        mapped_ip=req.int_ip,
        ext_port_str=req.ext_port,
        int_port_str=req.int_port,
        group_name=f_group
    )

    if not success:
        # 如果失敗，把詳細錯誤印在 Terminal 方便 SRE 查修
        print(f"❌ 設備寫入失敗詳細資訊: {msg}")
        return jsonify({"status": "error", "message": f"設備寫入失敗：{msg}"})

    # 5. 更新資料庫與發送通知
    try:
        req.expire_date = datetime.now() + timedelta(days=180)
        req.status = 3  # 已結案
        db.session.commit()
        
        # 發送信件通知
        public_ip = os.getenv('VIP_PUBLIC_IP', f_ip)
        send_final_notification(req.email, req.ticket_id, f"{public_ip}:{req.ext_port}", req.expire_date)
        
        return jsonify({"status": "success", "message": "開通成功且已寄發通知"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"程序完成但資料庫更新失敗: {str(e)}"})
# --- 其他路由 (Archive, Delete, Login, Logout, Download) ---
@app.route('/archive_request/<int:id>', methods=['POST'])
def archive_request(id):
    req = VIPRequest.query.get_or_404(id)
    req.status = 3
    db.session.commit()
    return jsonify({"status": "success", "message": "已歸檔"})
@app.route('/delete_request/<int:id>', methods=['POST'])
def delete_request(id):
    req = db.session.get(VIPRequest, id)
    if req:
        if req.file_path and os.path.exists(req.file_path):
            try: os.remove(req.file_path)
            except: pass
        db.session.delete(req)
        db.session.commit()
        return jsonify({"status": "success", "message": "已刪除"})
    return jsonify({"status": "error", "message": "找不到工單"}), 404
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == 'admin' and request.form.get('password') == '123456':
            session['is_admin'] = True
            return redirect(url_for('admin'))
    return render_template('login.html')
@app.route('/logout')
def logout():
    session.pop('is_admin', None)
    return redirect(url_for('login'))
@app.route('/download/<int:id>')
def download_file(id):
    req = db.session.get(VIPRequest, id)
    if req and req.file_path:
        return send_file(req.file_path, as_attachment=True)
    return "檔案不存在", 404
@app.route('/delete_vip/<int:id>', methods=['POST'])
def delete_vip(id):
    if not session.get('is_admin'): return jsonify({"status": "error", "message": "無權限"}), 403

    req = db.session.get(VIPRequest, id)
    if not req: return jsonify({"status": "error", "message": "找不到工單"})

    # 1. 呼叫 forti_mod 的刪除功能 (假設你已在 forti_mod 寫好 delete_vip 方法)
    forti = FortiGateConnector(ip=FG_IP, token=FG_TOKEN)
    
    # 命名規則就是 申請單ID
    base_name = req.ticket_id
    
    # 你需要去 forti_mod.py 實作 delete_vip_from_fortigate
    success, msg = forti.delete_vip_from_fortigate(base_name, group_name=FG_GROUP)

    if success:
        try:
            # 2. 設備刪除成功後，更新 SQL 狀態或刪除紀錄
            # 建議不要直接 delete，而是把 status 改成 4 (已回收)
            req.status = 4 
            db.session.commit()
            return jsonify({"status": "success", "message": "設備權限已回收，狀態已更新"})
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": f"DB 更新失敗: {str(e)}"})
    else:
        return jsonify({"status": "error", "message": f"防火牆刪除失敗: {msg}"})    
@app.route('/status')
def status_page():
    return render_template('status.html')
@app.route('/api/check_status/<ticket_id>')
def check_status(ticket_id):
    # 1. 對輸入值進行清洗
    search_id = ticket_id.strip()

    # 2. 使用 func.lower() 讓搜尋不分大小寫
    # 這行意思是：不管資料庫存 REQ 還是 req，通通轉小寫比對
    record = VIPRequest.query.filter(
        func.lower(VIPRequest.ticket_id) == func.lower(search_id)
    ).first()

    if not record:
        # Debug：如果還是找不到，印出目前資料庫前 5 筆單號到底長怎樣
        samples = [r.ticket_id for r in VIPRequest.query.limit(5).all()]
        print(f"查詢失敗！輸入值: '{search_id}', 資料庫樣本: {samples}")
        return jsonify({'status': 'error', 'message': '找不到單號'}), 404

    # 3. 如果找到了，回傳前端需要的欄位
    # 注意：這裡的欄位名稱要跟你的 index.html JS 對得起來
    return jsonify({
    'status': 'success',
    'applicant': record.applicant,
    'dept': record.dept, # 加上這個
    'expire_date': record.expire_date.strftime('%Y-%m-%d') if record.expire_date else None, # 加上這個
    'int_ip': record.int_ip,
    'int_port': record.int_port,
    'ext_port': record.ext_port,
    'current_status': record.status # 1, 2, 3
}) 
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
print(app.url_map)

