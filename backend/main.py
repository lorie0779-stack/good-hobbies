import os

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

try:
    # 當以 `uvicorn backend.main:app` 從專案根目錄啟動時使用
    from backend import database  # type: ignore
except Exception:
    # 當在 backend 目錄內以 `uvicorn main:app` 啟動時使用
    import database  # type: ignore

app = FastAPI(title="瑪利歐金幣系統 API")

# 設定 CORS，允許前端網頁呼叫 API (測試期先全開)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup() -> None:
    database.init_db()
    database.ensure_users(["kyle", "ryder"])
    database.seed_tasks_if_empty()


# 健康檢查：給 Fly health check 用，公開不需 token
@app.get("/api/health")
def health():
    return {"status": "ok"}


def _extract_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    value = authorization.strip()
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return value


def _verify_token(authorization: Optional[str] = Header(default=None)) -> None:
    expected = os.getenv("API_TOKEN", "local-dev-token")
    got = _extract_token(authorization)
    if not got or got != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


class TransactionCreate(BaseModel):
    user_name: str
    delta: int
    reason: str


class TransactionCreatedResponse(BaseModel):
    transaction_id: int
    user_name: str
    delta: int
    reason: str
    created_at: str
    current_coins: int

class UserStatus(BaseModel):
    name: str
    current_coins: int
    completed_task_ids_today: list[str]


class StatusResponse(BaseModel):
    total_coins: int
    users: list[UserStatus]


@app.get("/api/status", response_model=StatusResponse)
def get_status(_: None = Depends(_verify_token)):
    users = database.list_users()
    total = sum(u.current_coins for u in users)
    user_status = []
    for u in users:
        completed_today = database.list_completed_task_ids_for_user_today(u.name)
        user_status.append(
            UserStatus(
                name=u.name,
                current_coins=u.current_coins,
                completed_task_ids_today=completed_today,
            )
        )
    return StatusResponse(total_coins=total, users=user_status)


@app.post(
    "/api/transactions",
    response_model=TransactionCreatedResponse,
    dependencies=[Depends(_verify_token)],
)
def post_transactions(body: TransactionCreate):
    try:
        tx, user = database.create_transaction(
            user_name=body.user_name,
            delta=body.delta,
            reason=body.reason,
        )
    except database.InsufficientCoinsError:
        raise HTTPException(status_code=400, detail="Insufficient coins")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return TransactionCreatedResponse(
        transaction_id=tx.id,
        user_name=user.name,
        delta=tx.delta,
        reason=tx.reason,
        created_at=tx.created_at,
        current_coins=user.current_coins,
    )


# --- 任務清單 API（從 DB 讀取，更新免上版）---

@app.get("/api/tasks")
def get_tasks(_: None = Depends(_verify_token)):
    """回傳與 tasks.json 相同結構的任務設定，供前端載入。"""
    return database.get_tasks_config()


@app.put("/api/admin/tasks", dependencies=[Depends(_verify_token)])
async def put_admin_tasks(request: Request):
    """管理員覆寫全部任務設定（與 tasks.json 同結構）。"""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not body or not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object with kyle, ryder, common")
    database.replace_tasks_config(body)
    return {"ok": True}


@app.post("/api/admin/tasks/restore-defaults", dependencies=[Depends(_verify_token)])
def restore_default_tasks():
    """
    從 repo 內建的 frontend/tasks.json 還原預設任務（Kyle/Ryder/共用）。
    用於誤操作清空後的一鍵回復。
    """
    data = database.load_default_tasks_from_file()
    if not data:
        raise HTTPException(status_code=500, detail="Default tasks.json not found on server")
    database.replace_tasks_config(data)
    return {"ok": True}


@app.get("/api/transactions/{user_name}", dependencies=[Depends(_verify_token)])
def get_transactions(user_name: str, limit: int = 100):
    return database.list_transactions(user_name=user_name, limit=limit)
