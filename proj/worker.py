"""Start a worker:  python worker.py

Run it in several terminals to process tasks in parallel.
"""
import logging
import signal
import threading

from backend.app import create_app
from backend.scheduler import run_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

stop_event = threading.Event()


def shutdown(signum, frame):
    # Finish the current task, then exit cleanly
    stop_event.set()


signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

if __name__ == "__main__":
    app = create_app()
    run_worker(
        app.config["DATABASE"],
        stop_event,
        poll_interval=app.config["POLL_INTERVAL"],
        task_timeout=app.config["TASK_TIMEOUT"],
    )
