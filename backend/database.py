import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 預設用本機檔；Fly 上由 SQLALCHEMY_DATABASE_URL 指向掛載 volume 的 /data
SQLALCHEMY_DATABASE_URL = os.getenv(
    "SQLALCHEMY_DATABASE_URL",
    f"sqlite:///{os.path.join(BASE_DIR, 'mario_db.sqlite')}",
)

# 備份用：從連線字串解析出實體檔路徑（僅 sqlite 適用）
DB_PATH = (
    SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "", 1)
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite:///")
    else os.path.join(BASE_DIR, "mario_db.sqlite")
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
