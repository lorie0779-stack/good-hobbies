from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


DEFAULT_DB_FILENAME = "database.db"


@dataclass(frozen=True)
class User:
    id: int
    name: str
    current_coins: int


@dataclass(frozen=True)
class Transaction:
    id: int
    user_id: int
    delta: int
    reason: str
    created_at: str  # ISO-8601 string (UTC)


def _db_path(db_path: Optional[str] = None) -> str:
    if db_path:
        return db_path
    env = os.getenv("DATABASE_PATH")
    if env:
        return env
    # 預設使用專案根目錄的 database.db（符合 PRD：全面遷移至 SQLite database.db）
    repo_root = Path(__file__).resolve().parents[1]
    return str(repo_root / DEFAULT_DB_FILENAME)


def connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    # timeout + busy_timeout：在 BEGIN IMMEDIATE 競態下更穩健（等待鎖而非立刻失敗）
    conn = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    conn = connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              current_coins INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS transactions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              delta INTEGER NOT NULL,
              reason TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT
            );

            CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
            CREATE INDEX IF NOT EXISTS idx_transactions_created_at ON transactions(created_at);

            CREATE TABLE IF NOT EXISTS task_categories (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              player_key TEXT NOT NULL,
              category_id TEXT NOT NULL,
              title TEXT NOT NULL,
              theme TEXT NOT NULL,
              is_active INTEGER NOT NULL DEFAULT 1,
              default_open INTEGER NOT NULL DEFAULT 0,
              sort_order INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS task_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              category_id INTEGER NOT NULL,
              task_id TEXT NOT NULL,
              name TEXT NOT NULL,
              points INTEGER,
              cost_stars INTEGER,
              type TEXT NOT NULL,
              btn_class TEXT NOT NULL,
              btn_text TEXT NOT NULL,
              style TEXT,
              sort_order INTEGER NOT NULL DEFAULT 0,
              FOREIGN KEY (category_id) REFERENCES task_categories(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_task_items_category_id ON task_items(category_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


def ensure_users(names: Iterable[str], db_path: Optional[str] = None) -> None:
    conn = connect(db_path)
    try:
        conn.execute("BEGIN;")
        for name in names:
            if not name or not name.strip():
                continue
            conn.execute(
                "INSERT OR IGNORE INTO users(name, current_coins) VALUES(?, 0);",
                (name.strip(),),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_users(db_path: Optional[str] = None) -> list[User]:
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, name, current_coins FROM users ORDER BY id ASC;"
        ).fetchall()
        return [
            User(id=int(r["id"]), name=str(r["name"]), current_coins=int(r["current_coins"]))
            for r in rows
        ]
    finally:
        conn.close()


def get_user_by_name(name: str, db_path: Optional[str] = None) -> Optional[User]:
    conn = connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, name, current_coins FROM users WHERE name = ?;",
            (name,),
        ).fetchone()
        if not row:
            return None
        return User(id=int(row["id"]), name=str(row["name"]), current_coins=int(row["current_coins"]))
    finally:
        conn.close()


class InsufficientCoinsError(Exception):
    pass


def create_transaction(
    *,
    user_name: str,
    delta: int,
    reason: str,
    db_path: Optional[str] = None,
) -> tuple[Transaction, User]:
    if not user_name or not user_name.strip():
        raise ValueError("user_name is required")
    if not reason or not reason.strip():
        raise ValueError("reason is required")
    if delta == 0:
        raise ValueError("delta cannot be 0")

    conn = connect(db_path)
    try:
        # 強制序列化寫入，避免併發下餘額競態
        conn.execute("BEGIN IMMEDIATE;")

        row = conn.execute(
            "SELECT id, name, current_coins FROM users WHERE name = ?;",
            (user_name.strip(),),
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users(name, current_coins) VALUES(?, 0);",
                (user_name.strip(),),
            )
            row = conn.execute(
                "SELECT id, name, current_coins FROM users WHERE name = ?;",
                (user_name.strip(),),
            ).fetchone()

        user_id = int(row["id"])
        current = int(row["current_coins"])
        new_balance = current + int(delta)
        if new_balance < 0:
            raise InsufficientCoinsError("current_coins cannot be negative")

        # 規格要求：每次點數異動，必須先 Insert 帳本，再 Update Users
        cur = conn.execute(
            "INSERT INTO transactions(user_id, delta, reason) VALUES(?, ?, ?);",
            (user_id, int(delta), reason.strip()),
        )
        tx_id = int(cur.lastrowid)
        conn.execute(
            "UPDATE users SET current_coins = ? WHERE id = ?;",
            (new_balance, user_id),
        )

        tx_row = conn.execute(
            "SELECT id, user_id, delta, reason, created_at FROM transactions WHERE id = ?;",
            (tx_id,),
        ).fetchone()
        user_row = conn.execute(
            "SELECT id, name, current_coins FROM users WHERE id = ?;",
            (user_id,),
        ).fetchone()

        conn.commit()

        tx = Transaction(
            id=int(tx_row["id"]),
            user_id=int(tx_row["user_id"]),
            delta=int(tx_row["delta"]),
            reason=str(tx_row["reason"]),
            created_at=str(tx_row["created_at"]),
        )
        user = User(
            id=int(user_row["id"]),
            name=str(user_row["name"]),
            current_coins=int(user_row["current_coins"]),
        )
        return tx, user
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def list_completed_task_ids_for_user_today(
    user_name: str,
    db_path: Optional[str] = None,
) -> list[str]:
    """
    依據 Ledger (transactions) 回傳「今天已記過分的 earn 任務 id 列表」。
    - 僅統計 action_type = 'earn' 且 delta > 0 的交易
    - 以 SQLite DATE(created_at) = DATE('now') 做每日重置（UTC）
    """
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT t.reason
            FROM transactions AS t
            JOIN users AS u ON u.id = t.user_id
            WHERE u.name = ?
              AND t.delta > 0
              AND t.reason LIKE 'earn:%'
              AND DATE(t.created_at) = DATE('now')
            """,
            (user_name.strip(),),
        ).fetchall()

        task_ids: set[str] = set()
        for r in rows:
            raw = str(r["reason"])
            # reason 格式： actionType:taskId:taskName
            parts = raw.split(":", 2)
            if len(parts) < 2:
                continue
            action_type, task_id = parts[0], parts[1]
            if action_type != "earn":
                continue
            if task_id:
                task_ids.add(task_id)
        return sorted(task_ids)
    finally:
        conn.close()


# --- 任務清單 (admin 管理，與原 tasks.json 同結構) ---

def get_tasks_config(db_path: Optional[str] = None) -> dict:
    """從 DB 組出與 tasks.json 相同結構：{ "kyle": [...], "ryder": [...], "common": [...] }"""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            "SELECT id, player_key, category_id, title, theme, is_active, default_open, sort_order "
            "FROM task_categories ORDER BY player_key, sort_order, id;"
        ).fetchall()
        if not rows:
            return {"kyle": [], "ryder": [], "common": []}

        out: dict[str, list] = {}
        for r in rows:
            cat_id = int(r["id"])
            player_key = str(r["player_key"])
            out.setdefault(player_key, [])
            items = conn.execute(
                "SELECT task_id, name, points, cost_stars, type, btn_class, btn_text, style, sort_order "
                "FROM task_items WHERE category_id = ? ORDER BY sort_order, id;",
                (cat_id,),
            ).fetchall()
            task_list = []
            for i in items:
                t: dict = {
                    "id": str(i["task_id"]),
                    "name": str(i["name"]),
                    "type": str(i["type"]),
                    "btnClass": str(i["btn_class"]),
                    "btnText": str(i["btn_text"]),
                }
                if i["points"] is not None:
                    t["points"] = int(i["points"])
                if i["cost_stars"] is not None:
                    t["costStars"] = int(i["cost_stars"])
                if i["style"]:
                    t["style"] = str(i["style"])
                task_list.append(t)
            out.setdefault(player_key, []).append({
                "id": str(r["category_id"]),
                "title": str(r["title"]),
                "theme": str(r["theme"]),
                "isActive": bool(r["is_active"]),
                "defaultOpen": bool(r["default_open"]),
                "tasks": task_list,
            })
        out.setdefault("common", [])
        return out
    finally:
        conn.close()


def replace_tasks_config(data: dict, db_path: Optional[str] = None) -> None:
    """以與 tasks.json 相同結構的 dict 覆寫全部任務（先刪後插）；支援任意 profile 鍵。"""
    conn = connect(db_path)
    try:
        conn.execute("DELETE FROM task_items;")
        conn.execute("DELETE FROM task_categories;")
        sort_cat = 0
        for player_key in data:
            categories = data.get(player_key)
            if not isinstance(categories, list):
                continue
            for cat in categories:
                if not isinstance(cat, dict):
                    continue
                cid = cat.get("id") or ""
                title = cat.get("title") or ""
                theme = cat.get("theme") or ""
                is_active = 1 if cat.get("isActive", True) else 0
                default_open = 1 if cat.get("defaultOpen", False) else 0
                conn.execute(
                    "INSERT INTO task_categories (player_key, category_id, title, theme, is_active, default_open, sort_order) VALUES (?,?,?,?,?,?,?);",
                    (player_key, str(cid), title, theme, is_active, default_open, sort_cat),
                )
                sort_cat += 1
                cat_pk = conn.execute("SELECT last_insert_rowid();").fetchone()[0]
                tasks = cat.get("tasks")
                if not isinstance(tasks, list):
                    continue
                for sort_item, t in enumerate(tasks):
                    if not isinstance(t, dict):
                        continue
                    tid = t.get("id") or ""
                    name = t.get("name") or ""
                    typ = t.get("type") or "earn"
                    btn_class = t.get("btnClass") or "btn-question"
                    btn_text = t.get("btnText") or "?"
                    points = t.get("points")
                    cost_stars = t.get("costStars")
                    style = t.get("style")
                    conn.execute(
                        "INSERT INTO task_items (category_id, task_id, name, points, cost_stars, type, btn_class, btn_text, style, sort_order) VALUES (?,?,?,?,?,?,?,?,?,?);",
                        (cat_pk, str(tid), name, points, cost_stars, typ, btn_class, btn_text, style, sort_item),
                    )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def seed_tasks_if_empty(db_path: Optional[str] = None) -> None:
    """若 task_categories 為空，從 frontend/tasks.json 讀取並寫入 DB。"""
    conn = connect(db_path)
    try:
        n = conn.execute("SELECT COUNT(*) FROM task_categories;").fetchone()[0]
        if n > 0:
            return
    finally:
        conn.close()

    path = Path(__file__).resolve().parents[1] / "frontend" / "tasks.json"
    if not path.exists():
        return
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    replace_tasks_config(data, db_path)


def load_default_tasks_from_file() -> Optional[dict]:
    """讀取 repo 內建的 frontend/tasks.json（不存在則回傳 None）。"""
    path = Path(__file__).resolve().parents[1] / "frontend" / "tasks.json"
    if not path.exists():
        return None
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return None
    # 確保至少有 common
    data.setdefault("common", [])
    return data

def list_transactions(
    user_name: str,
    limit: int = 100,
    db_path: Optional[str] = None,
) -> list[dict]:
    """回傳玩家的帳本明細，格式與前端 behaviorLogs 相容。"""
    conn = connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT t.delta, t.reason, t.created_at
            FROM transactions AS t
            JOIN users AS u ON u.id = t.user_id
            WHERE u.name = ?
            ORDER BY t.id DESC
            LIMIT ?
            """,
            (user_name.strip(), limit),
        ).fetchall()
        result = []
        for r in rows:
            reason = str(r["reason"])
            parts = reason.split(":", 2)
            action_type = parts[0] if len(parts) >= 1 else "unknown"
            task_name   = parts[2] if len(parts) >= 3 else reason
            ts_raw = str(r["created_at"])
            try:
                from datetime import datetime, timezone, timedelta
                dt = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                dt_local = dt.astimezone(timezone(timedelta(hours=8)))
                ts = dt_local.strftime("%Y/%m/%d %H:%M")
            except Exception:
                ts = ts_raw[:16]
            result.append({
                "timestamp":   ts,
                "task_name":   task_name,
                "action_type": action_type,
                "point_change": int(r["delta"]),
            })
        return result
    finally:
        conn.close()
