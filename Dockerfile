# good-hobbies V2.2 後端（FastAPI + 原生 sqlite3 帳本制）→ Fly.io
# build context = repo root（才能同時帶 backend/ 與 frontend/tasks.json）
FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 後端程式碼放 /app/backend，以 `backend.main:app` 啟動
COPY backend/ ./backend/
# restore-defaults 會讀 parents[1]/frontend/tasks.json（= /app/frontend/tasks.json）
COPY frontend/tasks.json ./frontend/tasks.json

# DB 走 volume（DATABASE_PATH=/data/database.db，見 fly.toml）
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
