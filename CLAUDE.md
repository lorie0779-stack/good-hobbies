# good-hobbies 專案系統規則（2026-07-07 建立；事實盤點見 ~/my-ai-brain/side-projects/good-hobbies.md）

Kyle/Ryder 興趣獎勵金幣系統：好習慣賺金幣、壞行為扣金幣，sqlite 帳本制記每筆交易。
權限硬規則（commit/push/deploy/rm 必問）承襲全域 `~/CLAUDE.md`，此處不重複。

## 架構事實（改東西前先對號入座）

- **前端**：原生 HTML 無框架，三頁各自獨立——
  `frontend/index.html`（孩子用主頁）、`frontend/admin-tasks.html`（家長後台，密碼保護）、
  `frontend/insights.html`(行為洞察，密碼保護）。共用邏輯是**複製貼上**的，
  改共用行為（如 resolveApiBase、token）要三頁都改。
- **後端**：`backend/main.py`（FastAPI）+ `backend/database.py`（raw sqlite3 + WAL，帳本制）。
  **不是 SQLAlchemy**——舊版才是，V2.2 起是 raw sqlite3，別照 requirements.txt 裡的
  sqlalchemy 條目誤判（它是殘留依賴）。
- **任務定義**：`frontend/tasks.json`（Kyle/Ryder/common）。它同時被
  Dockerfile COPY 進後端映像供 restore-defaults 用——所以**改 tasks.json 要重佈後端**。

## 雙部署目標（最常忘的一條）

| 改了什麼 | 要跑什麼 | 上到哪 |
|---|---|---|
| frontend/*.html | `./deploy-frontend.sh` | GitHub Pages（gh-pages 分支） |
| backend/*、tasks.json、Dockerfile | `flyctl deploy` | Fly.io（app: good-hobbies-api，東京 nrt） |

只推一邊 = 半殘上線。網址：前端 https://lorie0779-stack.github.io/good-hobbies/ 、
後端 https://good-hobbies-api.fly.dev 。Fly 機器 auto-stop，首次請求要喚醒幾秒，不是當機。

## 認證與寫死的值（手動同步點）

- 後端從 env `API_TOKEN` 讀 token（`backend/main.py:49`，本機預設 `local-dev-token`）；
  **前端三頁各自硬編正式 token**（如 `index.html:135`）。改 token = 改 Fly secret + 三個 HTML。
- 除 `/api/health` 外所有端點都要 `Authorization: Bearer <token>`。
- 家長密碼 `ADMIN_PWD = "2738"` 硬編在 admin-tasks.html 與 insights.html 兩處；
  驗過後寫 `sessionStorage.gh_authed` 跨頁共享，改密碼要兩頁同改。

## 本機開發

```bash
cd ~/Desktop/good-hobbies
pip install -r backend/requirements.txt
API_TOKEN=local-dev-token uvicorn backend.main:app --port 8001   # port 必須 8001
# 瀏覽器直接開 frontend/index.html
```

- **port 8001 是前端寫死的**：`resolveApiBase()` 在 localhost 一律打 `127.0.0.1:8001`，
  起在別的 port 前端會靜默打不到。
- resolveApiBase 三段式：localhost → `127.0.0.1:8001`；`*.github.io` → fly.dev；其他 → 同源 `/api`。

## 資料安全

- 生產資料庫在 Fly volume `/data/database.db`——孩子的真實金幣帳本，
  **任何會動線上資料的操作（migration、restore-defaults 打正式站）先問**。
- `POST /api/admin/tasks/restore-defaults` 會覆寫任務定義，別對正式站隨手打。

## Git 陷阱（踩過的雷）

- 全域 `~/.gitignore` 有 `/*`，**新檔案會被默默忽略**：commit 前跑 `git status --short`
  比對本次實際新增的檔案清單，少了的用 `git check-ignore -v` 查、`git add -f` 加。
- `.claude/`、`.gstack/` 是工具目錄，非業務碼，不隨手 commit。

## 驗收慣例

- 前端改動：本機起後端 + 開頁實際走一次受影響流程（不是只看 diff）。
- 上線後：curl `https://good-hobbies-api.fly.dev/api/health` 確認活著、開 Pages 頁面確認吃到新版。
- 未實測的東西如實標「未驗證」，不寫「應該可以」。
