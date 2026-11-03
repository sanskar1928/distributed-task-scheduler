import sqlite3

from flask import g, current_app

TASK_STATUSES = ("queued", "running", "completed", "failed", "cancelled")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 10),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','completed','failed','cancelled')),
    payload TEXT,
    result TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Used by the worker: "next queued task, highest priority first"
CREATE INDEX IF NOT EXISTS idx_task_queue
    ON tasks (status, priority DESC, id ASC);

-- Used by the API: "my tasks, newest first"
CREATE INDEX IF NOT EXISTS idx_task_user
    ON tasks (user_id, id DESC);
"""


def connect(path, autocommit=False):
    """Open a SQLite connection.

    autocommit=True is used by workers, which manage their own
    transactions explicitly (BEGIN IMMEDIATE ... COMMIT).
    """
    conn = sqlite3.connect(
        path,
        timeout=10,
        isolation_level=None if autocommit else "",
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets readers (API) and writers (workers) work at the same time
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    conn = connect(app.config["DATABASE"])
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
