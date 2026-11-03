import json
import sqlite3

from flask import Blueprint, request, jsonify, g

from .authentication import (
    hash_password,
    verify_password,
    create_token,
    login_required,
)
from .database import get_db, TASK_STATUSES
from .handlers import HANDLERS, DEFAULT_TASK_TYPE

task_api = Blueprint("task_api", __name__, url_prefix="/api")

MAX_USERNAME_LENGTH = 50
MIN_PASSWORD_LENGTH = 6
MAX_TITLE_LENGTH = 200
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def error(message, status):
    return jsonify({"error": message}), status


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def is_int(value):
    # bool is a subclass of int in Python, so exclude it explicitly
    return isinstance(value, int) and not isinstance(value, bool)


def task_to_dict(row):
    task = dict(row)
    for field in ("payload", "result"):
        if task.get(field):
            try:
                task[field] = json.loads(task[field])
            except ValueError:
                pass
    return task


@task_api.route("/register", methods=["POST"])
def register():
    data = json_body()
    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return error("Username and password must be strings", 400)

    username = username.strip()

    if not username or len(username) > MAX_USERNAME_LENGTH:
        return error(
            f"Username must be 1-{MAX_USERNAME_LENGTH} characters", 400
        )
    if len(password) < MIN_PASSWORD_LENGTH:
        return error(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters", 400
        )

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hash_password(password)),
        )
        db.commit()
    except sqlite3.IntegrityError:
        # Only the UNIQUE constraint on username lands here.
        # Other errors are real bugs and should not be hidden.
        db.rollback()
        return error("Username already exists", 409)

    return jsonify({
        "message": "Registration successful",
        "user_id": cursor.lastrowid,
    }), 201


@task_api.route("/login", methods=["POST"])
def login():
    data = json_body()
    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return error("Invalid credentials", 401)

    user = get_db().execute(
        "SELECT id, password FROM users WHERE username = ?", (username,)
    ).fetchone()

    if user is None:
        # Do the same work as a real check so response time does not
        # reveal whether the username exists.
        hash_password(password)
        return error("Invalid credentials", 401)

    if not verify_password(password, user["password"]):
        return error("Invalid credentials", 401)

    return jsonify({
        "message": "Login successful",
        "token": create_token(user["id"]),
    })


@task_api.route("/tasks", methods=["POST"])
@login_required
def create_task():
    data = json_body()

    title = data.get("title")
    priority = data.get("priority", 1)
    payload = data.get("payload", {})

    if not isinstance(title, str) or not title.strip():
        return error("Task title is required", 400)
    title = title.strip()
    if len(title) > MAX_TITLE_LENGTH:
        return error(f"Title must be at most {MAX_TITLE_LENGTH} characters", 400)

    if not is_int(priority) or not 1 <= priority <= 10:
        return error("Priority must be an integer from 1 to 10", 400)

    if not isinstance(payload, dict):
        return error("Payload must be a JSON object", 400)

    task_type = payload.get("type", DEFAULT_TASK_TYPE)
    if task_type not in HANDLERS:
        return error(
            f"Unknown task type. Choose from: {', '.join(sorted(HANDLERS))}",
            400,
        )

    db = get_db()
    cursor = db.execute(
        "INSERT INTO tasks (user_id, title, priority, payload) "
        "VALUES (?, ?, ?, ?)",
        (g.user_id, title, priority, json.dumps(payload)),
    )
    db.commit()

    return jsonify({
        "message": "Task created successfully",
        "task_id": cursor.lastrowid,
    }), 201


@task_api.route("/tasks", methods=["GET"])
@login_required
def get_tasks():
    status = request.args.get("status")
    if status is not None and status not in TASK_STATUSES:
        return error(f"Status must be one of: {', '.join(TASK_STATUSES)}", 400)

    try:
        limit = int(request.args.get("limit", DEFAULT_PAGE_SIZE))
        offset = int(request.args.get("offset", 0))
    except ValueError:
        return error("limit and offset must be integers", 400)

    if not 1 <= limit <= MAX_PAGE_SIZE or offset < 0:
        return error(
            f"limit must be 1-{MAX_PAGE_SIZE} and offset must be 0 or more", 400
        )

    query = (
        "SELECT id, title, priority, status, result, attempts, "
        "created_at, finished_at FROM tasks WHERE user_id = ?"
    )
    params = [g.user_id]
    if status:
        query += " AND status = ?"
        params.append(status)
    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    rows = get_db().execute(query, params).fetchall()

    return jsonify({
        "tasks": [task_to_dict(row) for row in rows],
        "limit": limit,
        "offset": offset,
    })


@task_api.route("/tasks/<int:task_id>", methods=["GET"])
@login_required
def get_task(task_id):
    # user_id in the WHERE clause: users can never read each other's tasks
    task = get_db().execute(
        "SELECT * FROM tasks WHERE id = ? AND user_id = ?",
        (task_id, g.user_id),
    ).fetchone()

    if task is None:
        return error("Task not found", 404)

    return jsonify(task_to_dict(task))


@task_api.route("/tasks/<int:task_id>/cancel", methods=["POST"])
@login_required
def cancel_task(task_id):
    db = get_db()

    # Only queued tasks can be cancelled. The status check is part of the
    # UPDATE itself, so it cannot race with a worker claiming the task.
    cursor = db.execute(
        "UPDATE tasks SET status = 'cancelled', finished_at = CURRENT_TIMESTAMP "
        "WHERE id = ? AND user_id = ? AND status = 'queued'",
        (task_id, g.user_id),
    )
    db.commit()

    if cursor.rowcount == 0:
        return error("Task not found or cannot be cancelled", 404)

    return jsonify({"message": "Task cancelled successfully"})
