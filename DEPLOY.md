# good-hobbies V2.2 部署指南：Fly.io（後端）+ GitHub Pages（前端）
> V2.2＝raw sqlite3 帳本制（transactions 流水帳 + WAL）。後端 FastAPI → Fly.io（持久 volume）、
> 前端靜態 → GitHub Pages。API 內建 **Bearer token 驗證**。建立：2026-06-17（源自 EC2 54.237.62.8:8080 遷移）

---

## 架構重點
- 後端 API：`/api/status`、`/api/transactions`（POST）、`/api/transactions/{user}`、`/api/tasks`、
  `/api/admin/tasks`(PUT)、`/api/admin/tasks/restore-defaults`、公開 `/api/health`（健康檢查用）。
- 認證：所有 `/api/*`（除 health）需 `Authorization: Bearer <API_TOKEN>`。token 從後端 env `API_TOKEN` 讀。
- DB：raw sqlite3，路徑由 env `DATABASE_PATH` 指定（Fly 上 = `/data/database.db`，掛在 volume）。
- **build context = repo root**（根目錄 Dockerfile/fly.toml），因後端 `restore-defaults` 會讀
  `frontend/tasks.json`，需同時帶入 backend/ 與該檔。

---

## A. 後端 → Fly.io（在 repo root 執行）

```bash
cd ~/Desktop/good-hobbies
# 首次：
fly apps create good-hobbies-api
fly volumes create good_hobbies_data --region nrt --size 1
fly secrets set API_TOKEN=<你的token>          # 需與前端 index.html / admin-tasks.html 的 API_TOKEN 一致
fly deploy                                      # 用根目錄 Dockerfile（context=root）

# 日後更新：
fly deploy
```

### 驗證
```bash
curl https://good-hobbies-api.fly.dev/api/health                       # 公開 → {"status":"ok"}
curl -i https://good-hobbies-api.fly.dev/api/status                    # 無 token → 401
curl -H "Authorization: Bearer <token>" \
     https://good-hobbies-api.fly.dev/api/status                       # 帶 token → kyle/ryder 金幣
```

### 灌入既有 DB（保留金幣／帳本）
volume 啟動時會自建空 DB，sftp 不覆蓋，故需先刪再上傳：
```bash
fly ssh console --app good-hobbies-api -C "sh -c 'rm -f /data/database.db /data/database.db-wal /data/database.db-shm'"
fly ssh sftp put <你的 database.db 路徑> /data/database.db --app good-hobbies-api
fly apps restart good-hobbies-api
```

---

## B. 前端 → GitHub Pages

- **正式網址：`https://lorie0779-stack.github.io/good-hobbies/`**（含 `admin-tasks.html` 後台）
- `resolveApiBase()`：localhost→127.0.0.1:8001；github.io→`good-hobbies-api.fly.dev/api`；其餘走同源 `/api`。
- 可用 localStorage `api_base_override` 手動覆寫 API 位址。
- repo 必須維持 **public**（免費 Pages 限公開 repo）。

### 一鍵部署
```bash
~/Desktop/good-hobbies/deploy-frontend.sh
```
首次需到 GitHub repo → Settings → Pages → Source 設 `gh-pages` / `root`。

---

## C. 注意事項
- **冷啟動**：Fly scale-to-zero，閒置後首次請求約慢數秒（家庭用可接受，趨近 0 成本）。
- **Bearer token 是「擋掃描」等級**：token 內嵌在公開靜態前端，View Source 可見。擋得住隨機機器人直打
  fly.dev API，擋不住看原始碼的人。要真機密需改登入頁。
- **換 token**：同時改 `fly secrets set API_TOKEN=` 與 `frontend/index.html`＋`admin-tasks.html` 的
  `API_TOKEN`，重部署兩端。
- **金幣↔星星**：前端 10 金幣 = 1 星（`COINS_PER_STAR=10`）；HUD 顯示星數＋餘額金幣。
