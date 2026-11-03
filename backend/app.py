import os
from flask import Flask, jsonify

from .database import init_db
from .task_manager import task_api
from .scheduler import start_scheduler


def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.environ.get(
        "SECRET_KEY", "development-secret-key"
    )

    app.config["DATABASE"] = os.environ.get(
        "DATABASE", "tasks.db"
    )

    init_db(app)

    app.register_blueprint(task_api)

    start_scheduler(app)

    @app.route("/")
    def home():
        return jsonify({
            "message": "Distributed Task Scheduling Portal is running"
        })

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy"})

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)


