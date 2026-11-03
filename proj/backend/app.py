import os

from flask import Flask, jsonify

from .database import init_db, close_db
from .task_manager import task_api


def create_app(config=None):
    app = Flask(__name__)

    app.config.update(
        DATABASE=os.environ.get("DATABASE", "tasks.db"),
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        PBKDF2_ITERATIONS=600_000,
        POLL_INTERVAL=2,      # seconds a worker waits when the queue is empty
        TASK_TIMEOUT=300,     # seconds before a 'running' task is re-queued
    )
    if config:
        app.config.update(config)

    # No built-in default: a guessable secret would let anyone forge tokens.
    if not app.config["SECRET_KEY"]:
        raise RuntimeError(
            "SECRET_KEY is not set. Example: "
            "export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')"
        )

    init_db(app)
    app.teardown_appcontext(close_db)
    app.register_blueprint(task_api)

    @app.route("/")
    def home():
        return jsonify({"message": "Distributed Task Scheduling Portal is running"})

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy"})

    @app.errorhandler(404)
    def not_found(_):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(_):
        return jsonify({"error": "Method not allowed"}), 405

    @app.errorhandler(500)
    def server_error(_):
        return jsonify({"error": "Internal server error"}), 500

    return app
