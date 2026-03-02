from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# 建立本地端的 SQLite 資料庫檔案 mario_db.sqlite
SQLALCHEMY_DATABASE_URL = "sqlite:///./mario_db.sqlite"

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