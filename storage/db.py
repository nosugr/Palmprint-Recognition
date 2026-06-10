"""SQLite 连接与建表。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS templates (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code            BLOB NOT NULL,
    mask            BLOB NOT NULL,
    height          INTEGER NOT NULL,
    width           INTEGER NOT NULL,
    bits_per_pixel  INTEGER NOT NULL,
    version         TEXT NOT NULL,
    hand_side       TEXT DEFAULT '',
    quality         REAL DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    matched     INTEGER NOT NULL,
    distance    REAL NOT NULL,
    threshold   REAL NOT NULL,
    image_path  TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path if db_path is not None else config.DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    # 旧数据库迁移：添加新列（已存在则忽略）
    for col_def in [
        "ALTER TABLE templates ADD COLUMN hand_side TEXT DEFAULT ''",
        "ALTER TABLE templates ADD COLUMN quality REAL DEFAULT 0",
    ]:
        try:
            conn.execute(col_def)
        except sqlite3.OperationalError:
            pass  # 列已存在
    conn.commit()
