import json

from flask import Blueprint, request, jsonify, g

from .database import get_db
from .authentication import (
    hash_password,
    verify_password,
    create_token,
    login_required
)


task_api = Blueprint("task_api", __name__, url_prefix="/api")


@task_api.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or len(password) < 6:
        return jsonify({
            "error": "Username and password of at least 6 characters required"
        }), 400

    db = get_db()

    try:
        cursor = db.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hash_password(password))
        )
        db.commit()

        return jsonify({
            "message": "Registration successful",
            "user_id": cursor.lastrowid
        }), 201

    except Exception:
        db.rollback()
        return jsonify({"error": "Username already exists"}), 409


@task_api.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    username = data.get("username", "")
    password = data.get("password", "")

    db = get_db()

    user = db.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    ).fetchone()

    if user is None or not verify_password(
        password, user["password"]
    ):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_token(user["id"])

    return jsonify({
        "message": "Login successful",
        "token": token
    })


@task_api.route("/tasks", methods=["POST"])
@login_required
def create_task():
    data = request.get_json(silent=True) or {}

    title = data.get("title", "").strip()
    priority = data.get("priority", 1)
    payload = data.get("payload", {})

    if not title:
        return jsonify({"error": "Task title is required"}), 400

    if isinstance(priority, bool) or not isinstance(priority, int) or not 1 <= priority <= 10:
        return jsonify({
            "error": "Priority must be an integer from 1 to 10"
        }), 400

    if not isinstance(payload, dict):
        return jsonify({"error": "Payload must be a JSON object"}), 400

    db = get_db()

    cursor = db.execute("""
        INSERT INTO tasks (user_id, title, priority, payload)
        VALUES (?, ?, ?, ?)
    """, (
        g.user_id,
        title,
        priority,
        json.dumps(payload)
    ))

    db.commit()

    return jsonify({
        "message": "Task created successfully",
        "task_id": cursor.lastrowid
    }), 201


@task_api.route("/tasks", methods=["GET"])
@login_required
def get_tasks():
    db = get_db()

    tasks = db.execute("""
        SELECT id, title, priority, status, result, created_at
        FROM tasks
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (g.user_id,)).fetchall()

    return jsonify([dict(task) for task in tasks])


@task_api.route("/tasks/<int:task_id>", methods=["GET"])
@login_required
def get_task(task_id):
    db = get_db()

    task = db.execute("""
        SELECT * FROM tasks
        WHERE id = ? AND user_id = ?
    """, (task_id, g.user_id)).fetchone()

    if task is None:
        return jsonify({"error": "Task not found"}), 404

    return jsonify(dict(task))


@task_api.route("/tasks/<int:task_id>/cancel", methods=["POST"])
@login_required
def cancel_task(task_id):
    db = get_db()

    cursor = db.execute("""
        UPDATE tasks
        SET status = 'cancelled'
        WHERE id = ? AND user_id = ? AND status = 'queued'
    """, (task_id, g.user_id))

    db.commit()

    if cursor.rowcount == 0:
        return jsonify({
            "error": "Task not found or cannot be cancelled"
        }), 404

    return jsonify({"message": "Task cancelled successfully"})