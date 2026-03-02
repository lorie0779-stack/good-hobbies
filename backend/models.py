from sqlalchemy import Column, Integer, String, DateTime
from database import Base  # <--- 就是這一行讓 main.py 找得到 Base
import datetime

class PlayerStatus(Base):
    __tablename__ = "player_status"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(String, unique=True, index=True)
    total_coins = Column(Integer, default=0)

class BehaviorLog(Base):
    __tablename__ = "behavior_logs"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(String, index=True)
    task_name = Column(String)
    action_type = Column(String)
    point_change = Column(Integer)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class CompletedTask(Base):
    __tablename__ = "completed_tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(String, index=True)
    task_id = Column(String)
    date_str = Column(String)