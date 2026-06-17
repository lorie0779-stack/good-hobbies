# good-hobbies V2.2 部署指南：Fly.io（後端）+ GitHub Pages（前端）
> 模式同 dry-pants：後端 FastAPI+SQLite → Fly.io（含持久 volume）、前端靜態 → GitHub Pages。
> 差異：本專案 API 加上 **Bearer token 驗證**（擋隨機掃描）。建立：2026-06-17

---

## A. 後端 → Fly.io（在 backend/ 目錄）

```bash
cd ~/Desktop/good-hobbies/backend
fly apps create good-hobbies-api                                 # 名稱需全域唯一，被佔用就改名並同步改 fly.toml 的 app=
fly volumes create good_hobbies_data --region nrt --size 1       # 1GB volume 放 SQLite，東京區
fly secrets set API_TOKEN=<你的token>                            # 設驗證 token（與前端 index.html 的 API_TOKEN 一致）
fly deploy                                                       # 用 Dockerfile build + 部署
```

### 驗證
```bash
curl https://good-hobbies-api.fly.dev/api/health                 # 公開，應回 {"status":"ok"}
curl -i https://good-hobbies-api.fly.dev/api/player/kyle         # 無 token 應 401
curl -H "Authorization: Bearer <你的token>" \
     https://good-hobbies-api.fly.dev/api/player/kyle            # 帶 token 應 200
```

### （選用）把本機既有 DB 灌進 volume，保留現有金幣
```bash
fly ssh sftp put ~/Desktop/good-hobbies/backend/mario_db.sqlite /data/mario_db.sqlite
fly apps restart good-hobbies-api
```
> 不灌的話，volume 是空的，後端會自動 create_all 建空表（金幣從 0 開始）。

---

## B. 前端 → GitHub Pages

- **正式網址：`https://lorie0779-stack.github.io/good-hobbies/`**
- API 位址自動切換：本機(127.0.0.1)打 local，其餘打 `https://good-hobbies-api.fly.dev/api`（見 index.html 開頭）。
- 每個 API 請求自動帶 `Authorization: Bearer <API_TOKEN>`。
- repo 必須維持 **public**（免費 Pages 限公開 repo）。

### 一鍵部署
```bash
~/Desktop/good-hobbies/deploy-frontend.sh
```
部署後到 GitHub repo → Settings → Pages → Source 設 `gh-pages` / `root`。

---

## C. 注意事項
- **冷啟動**：Fly scale-to-zero，閒置後首次請求約慢數秒喚醒（家庭用可接受，趨近 0 成本）。
- **Bearer token 是「擋掃描」等級**：token 內嵌在公開靜態前端，View Source 可見。
  它擋得住隨機機器人直打 fly.dev API，但擋不住看原始碼的人。要真正機密需改成登入頁。
- **換 token**：同時改 `fly secrets set API_TOKEN=` 與 `frontend/index.html` 的 `API_TOKEN`，重部署兩端。
- **CORS**：後端 `allow_origins=["*"]`，前端沒帶 cookie → 跨來源 OK。
