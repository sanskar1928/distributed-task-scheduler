"""Worker logic: claim the highest-priority queued task, run it, record the result.

Workers are separate processes (see worker.py). You can start several against
the same database. Claiming is atomic, so a task is never run twice at once.
"""
import json
import logging
import sqlite3

from .database import connect
from .handlers import execute_task

log = logging.getLogger("scheduler")


def claim_next_task(db):
    """Atomically take the next task and mark it 'running'.

    `db` must be a connection opened with autocommit=True.
    BEGIN IMMEDIATE takes the write lock up front, so two workers cannot
    both read the same 'queued' row before one of them updates it.
    """
    db.execute("BEGIN IMMEDIATE")
    try:
        task = db.execute(
            "SELECT id, payload, attempts, max_attempts FROM tasks "
            "WHERE status = 'queued' "
            "ORDER BY priority DESC, id ASC LIMIT 1"
        ).fetchone()

        if task is None:
            db.execute("COMMIT")
            return None

        db.execute(
            "UPDATE tasks SET status = 'running', attempts = attempts + 1, "
            "started_at = CURRENT_TIMESTAMP WHERE id = ?",
            (task["id"],),
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

    return {
        "id": task["id"],
        "payload": task["payload"],
        "attempts": task["attempts"] + 1,
        "max_attempts": task["max_attempts"],
    }


def finish_task(db, task, result=None, error=None):
    if error is None:
        db.execute(
            "UPDATE tasks SET status = 'completed', result = ?, "
            "finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(result), task["id"]),
        )
    elif task["attempts"] < task["max_attempts"]:
        # Retry: put it back in the queue and remember the last error
        db.execute(
            "UPDATE tasks SET status = 'queued', started_at = NULL, "
            "result = ? WHERE id = ?",
            (json.dumps({"last_error": error}), task["id"]),
        )
    else:
        db.execute(
            "UPDATE tasks SET status = 'failed', result = ?, "
            "finished_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps({"error": error}), task["id"]),
        )


def process_one(db):
    """Run one task. Returns True if a task was processed, False if idle."""
    task = claim_next_task(db)
    if task is None:
        return False

    try:
        payload = json.loads(task["payload"] or "{}")
        result = execute_task(payload)
    except Exception as exc:
        log.warning("Task %s failed (attempt %s): %s",
                    task["id"], task["attempts"], exc)
        finish_task(db, task, error=str(exc))
    else:
        finish_task(db, task, result=result)

    return True


def recover_stuck_tasks(db, timeout_seconds):
    """Re-queue tasks stuck in 'running', e.g. because a worker crashed."""
    cursor = db.execute(
        "UPDATE tasks SET status = 'queued', started_at = NULL "
        "WHERE status = 'running' AND started_at < datetime('now', ?)",
        (f"-{int(timeout_seconds)} seconds",),
    )
    return cursor.rowcount


def run_worker(db_path, stop_event, poll_interval=2, task_timeout=300):
    """Main worker loop. Sleeps only when there is nothing to do."""
    db = connect(db_path, autocommit=True)
    log.info("Worker started")
    try:
        while not stop_event.is_set():
            try:
                recover_stuck_tasks(db, task_timeout)
                busy = process_one(db)
            except sqlite3.Error:
                log.exception("Database error in worker loop")
                busy = False

            if not busy:
                stop_event.wait(poll_interval)
    finally:
        db.close()
        log.info("Worker stopped")
