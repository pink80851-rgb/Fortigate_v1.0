# 使用輕量級 Python 3.9 鏡像
FROM python:3.9-slim

# 設定時區為台北 (對 MIS 紀錄 Log 非常重要)
ENV TZ=Asia/Taipei
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR /app

# 先複製依賴清單，利用 Docker 快取機制加速打包
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn  # 確保安裝 Gunicorn

# 複製所有程式碼 (排除 .dockerignore 內容)
COPY . .

# 建立儲存空間目錄，確保權限正確
RUN mkdir -p storage instance

# 啟動 Gunicorn：4 個 Worker 進程，監聽 5000 埠
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:5000", "app:app"]