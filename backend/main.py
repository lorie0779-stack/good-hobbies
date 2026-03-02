from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
import datetime

import models
from database import engine, get_db

# 自動建立資料庫與資料表
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="瑪利歐金幣系統 API")

# 設定 CORS，允許前端網頁呼叫 API (測試期先全開)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 定義前端傳來的資料格式
class TaskAction(BaseModel):
    player_id: str
    task_id: str
    task_name: str
    points: int
    action_type: str # 'earn', 'lose', 'shop_spend', 'admin_adjust'

# 1. 取得玩家當前所有資料
@app.get("/api/player/{player_id}")
def get_player_data(player_id: str, db: Session = Depends(get_db)):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    # 讀取或初始化玩家狀態
    status = db.query(models.PlayerStatus).filter(models.PlayerStatus.player_id == player_id).first()
    if not status:
        status = models.PlayerStatus(player_id=player_id, total_coins=0)
        db.add(status)
        db.commit()
        db.refresh(status)

    # 讀取歷史紀錄
    logs = db.query(models.BehaviorLog).filter(models.BehaviorLog.player_id == player_id).order_by(models.BehaviorLog.id.desc()).all()
    
    # 讀取今日已完成的任務
    completed = db.query(models.CompletedTask).filter(
        models.CompletedTask.player_id == player_id,
        models.CompletedTask.date_str == today_str
    ).all()

    return {
        "total_coins": status.total_coins,
        "logs": [{"timestamp": log.timestamp.strftime("%Y/%m/%d %H:%M"), "task_name": log.task_name, "action_type": log.action_type, "point_change": log.point_change} for log in logs],
        "completed_tasks": [c.task_id for c in completed]
    }

# 2. 紀錄點數變動與任務打勾
@app.post("/api/action")
def record_action(action: TaskAction, db: Session = Depends(get_db)):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    
    status = db.query(models.PlayerStatus).filter(models.PlayerStatus.player_id == action.player_id).first()
    if not status:
        status = models.PlayerStatus(player_id=action.player_id, total_coins=0)
        db.add(status)

    # 更新金幣 (不允許負數)
    status.total_coins += action.points
    if status.total_coins < 0:
        status.total_coins = 0

    # 寫入歷史存摺
    new_log = models.BehaviorLog(
        player_id=action.player_id,
        task_name=action.task_name,
        action_type=action.action_type,
        point_change=action.points,
        timestamp=datetime.datetime.now()
    )
    db.add(new_log)

    # 如果是賺取點數，寫入今日完成清單以鎖定按鈕
    if action.action_type == 'earn':
        new_completed = models.CompletedTask(
            player_id=action.player_id,
            task_id=action.task_id,
            date_str=today_str
        )
        db.add(new_completed)

    db.commit()
    return {"status": "success", "total_coins": status.total_coins}

# 3. 系統管理員重置 (清空資料庫紀錄)
@app.post("/api/admin/reset/{player_id}")
def reset_player(player_id: str, db: Session = Depends(get_db)):
    status = db.query(models.PlayerStatus).filter(models.PlayerStatus.player_id == player_id).first()
    if status:
        status.total_coins = 0
    
    db.query(models.BehaviorLog).filter(models.BehaviorLog.player_id == player_id).delete()
    db.query(models.CompletedTask).filter(models.CompletedTask.player_id == player_id).delete()
    
    db.commit()
    return {"status": "success"}