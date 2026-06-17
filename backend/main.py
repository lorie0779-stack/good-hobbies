import datetime
import os
import shutil

from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel

import models
from database import BASE_DIR, DB_PATH, engine, get_db

models.Base.metadata.create_all(bind=engine)

# Bearer token 驗證：token 從環境變數讀取（Fly secret），未設定則視為關閉驗證（本機開發）
API_TOKEN = os.getenv("API_TOKEN", "").strip()
_bearer = HTTPBearer(auto_error=False)


def require_token(creds: HTTPAuthorizationCredentials = Security(_bearer)) -> None:
    if not API_TOKEN:
        return  # 本機未設 token → 不擋，方便開發
    if creds is None or creds.scheme.lower() != "bearer" or creds.credentials != API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


app = FastAPI(title="瑪利歐金幣系統 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康檢查：給 Fly health check 用，不需驗證
@app.get("/api/health")
def health():
    return {"status": "ok"}


class TaskAction(BaseModel):
    player_id: str
    task_id: str
    task_name: str
    points: int
    action_type: str  # 'earn', 'lose', 'shop_spend', 'admin_adjust'


def _backup_db() -> None:
    if not os.path.exists(DB_PATH):
        return
    backup_dir = os.path.join(BASE_DIR, "backups")
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d")
    dest = os.path.join(backup_dir, f"mario_db.{stamp}.sqlite")
    if not os.path.exists(dest):
        shutil.copy2(DB_PATH, dest)
    # 保留最近 14 天
    backups = sorted(f for f in os.listdir(backup_dir) if f.endswith(".sqlite"))
    for old in backups[:-14]:
        os.remove(os.path.join(backup_dir, old))


def _migrate_db() -> None:
    from sqlalchemy import text
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE behavior_logs ADD COLUMN deleted_at DATETIME"))
            conn.commit()
        except Exception:
            pass  # 欄位已存在


@app.on_event("startup")
def on_startup() -> None:
    _backup_db()
    _migrate_db()


# 1. 取得玩家當前所有資料
@app.get("/api/player/{player_id}")
def get_player_data(player_id: str, db: Session = Depends(get_db), _: None = Depends(require_token)):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    status = db.query(models.PlayerStatus).filter(models.PlayerStatus.player_id == player_id).first()
    if not status:
        status = models.PlayerStatus(player_id=player_id, total_coins=0)
        db.add(status)
        db.commit()
        db.refresh(status)

    # 只回傳未被軟刪除的紀錄
    logs = (
        db.query(models.BehaviorLog)
        .filter(
            models.BehaviorLog.player_id == player_id,
            models.BehaviorLog.deleted_at == None,
        )
        .order_by(models.BehaviorLog.id.desc())
        .all()
    )

    completed = db.query(models.CompletedTask).filter(
        models.CompletedTask.player_id == player_id,
        models.CompletedTask.date_str == today_str,
    ).all()

    return {
        "total_coins": status.total_coins,
        "logs": [
            {
                "timestamp": log.timestamp.strftime("%Y/%m/%d %H:%M"),
                "task_name": log.task_name,
                "action_type": log.action_type,
                "point_change": log.point_change,
            }
            for log in logs
        ],
        "completed_tasks": [c.task_id for c in completed],
    }


# 2. 紀錄點數變動與任務打勾
@app.post("/api/action")
def record_action(action: TaskAction, db: Session = Depends(get_db), _: None = Depends(require_token)):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")

    status = db.query(models.PlayerStatus).filter(models.PlayerStatus.player_id == action.player_id).first()
    if not status:
        status = models.PlayerStatus(player_id=action.player_id, total_coins=0)
        db.add(status)

    status.total_coins += action.points
    if status.total_coins < 0:
        status.total_coins = 0

    new_log = models.BehaviorLog(
        player_id=action.player_id,
        task_name=action.task_name,
        action_type=action.action_type,
        point_change=action.points,
        timestamp=datetime.datetime.now(),
    )
    db.add(new_log)

    if action.action_type == "earn":
        new_completed = models.CompletedTask(
            player_id=action.player_id,
            task_id=action.task_id,
            date_str=today_str,
        )
        db.add(new_completed)

    db.commit()
    return {"status": "success", "total_coins": status.total_coins}


# 3. 系統管理員重置（軟刪除，資料保留可復原）
@app.post("/api/admin/reset/{player_id}")
def reset_player(player_id: str, db: Session = Depends(get_db), _: None = Depends(require_token)):
    now = datetime.datetime.now()

    status = db.query(models.PlayerStatus).filter(models.PlayerStatus.player_id == player_id).first()
    if status:
        status.total_coins = 0

    # 軟刪除：標記 deleted_at，不實際刪除資料
    (
        db.query(models.BehaviorLog)
        .filter(
            models.BehaviorLog.player_id == player_id,
            models.BehaviorLog.deleted_at == None,
        )
        .update({"deleted_at": now})
    )
    db.query(models.CompletedTask).filter(models.CompletedTask.player_id == player_id).delete()

    db.commit()
    return {"status": "success"}
