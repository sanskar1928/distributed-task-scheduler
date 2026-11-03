import json
import threading
import time

from flask import current_app
from .database import get_db


def execute_task(payload):
    # Demonstration task execution
    return {
        "message": "Task executed successfully",
        "input": payload
    }


def worker(app):
    while True:
        with app.app_context():
            db = get_db()

            try:
                db.execute("BEGIN IMMEDIATE")

                task = db.execute("""
                    SELECT id, payload
                    FROM tasks
                    WHERE status = 'queued'
                    ORDER BY priority DESC, id ASC
                    LIMIT 1
                """).fetchone()

                if task is None:
                    db.commit()
                else:
                    cursor = db.execute("""
                        UPDATE tasks
                        SET status = 'running'
                        WHERE id = ? AND status = 'queued'
                    """, (task["id"],))

                    db.commit()

                    if cursor.rowcount == 1:
                        try:
                            payload = json.loads(task["payload"] or "{}")
                            result = execute_task(payload)

                            db.execute("""
                                UPDATE tasks
                                SET status = 'completed', result = ?
                                WHERE id = ?
                            """, (json.dumps(result), task["id"]))

                            db.commit()

                        except Exception as error:
                            db.execute("""
                                UPDATE tasks
                                SET status = 'failed', result = ?
                                WHERE id = ?
                            """, (str(error), task["id"]))

                            db.commit()

            except Exception:
                db.rollback()

            finally:
                db.close()

        time.sleep(2)


def start_scheduler(app):
    if app.config.get("TESTING"):
        return

    if app.config.get("SCHEDULER_STARTED"):
        return

    app.config["SCHEDULER_STARTED"] = True

    thread = threading.Thread(
        target=worker,
        args=(app,),
        daemon=True
    )

    thread.start()