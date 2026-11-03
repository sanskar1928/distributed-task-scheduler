import json

import pytest

from backend.app import create_app
from backend.authentication import create_token
from backend.database import connect
from backend.scheduler import (
    claim_next_task,
    process_one,
    recover_stuck_tasks,
)


@pytest.fixture
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "SECRET_KEY": "test-secret-key",
        "PBKDF2_ITERATIONS": 1000,  # fast hashing for tests
    })


@pytest.fixture
def client(app):
    with app.test_client() as client:
        yield client


@pytest.fixture
def db(app):
    """A worker-style connection (autocommit) to the test database."""
    conn = connect(app.config["DATABASE"], autocommit=True)
    yield conn
    conn.close()


def register_and_login(client, username="testuser"):
    client.post("/api/register", json={"username": username, "password": "password123"})
    response = client.post("/api/login", json={"username": username, "password": "password123"})
    return {"Authorization": f"Bearer {response.get_json()['token']}"}


def add_task(client, headers, title="Task", priority=5, payload=None):
    response = client.post(
        "/api/tasks",
        json={"title": title, "priority": priority, "payload": payload or {"type": "echo"}},
        headers=headers,
    )
    assert response.status_code == 201
    return response.get_json()["task_id"]


# ---------- basics and authentication ----------

def test_health(client):
    assert client.get("/health").status_code == 200


def test_unknown_route_returns_json_404(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.get_json() == {"error": "Not found"}


def test_register_and_login(client):
    assert client.post("/api/register", json={"username": "u1", "password": "password123"}).status_code == 201
    response = client.post("/api/login", json={"username": "u1", "password": "password123"})
    assert response.status_code == 200
    assert "token" in response.get_json()


def test_duplicate_username_returns_409(client):
    body = {"username": "dup", "password": "password123"}
    client.post("/api/register", json=body)
    assert client.post("/api/register", json=body).status_code == 409


@pytest.mark.parametrize("body", [
    {"username": "x", "password": "123"},       # password too short
    {"username": "", "password": "password123"},  # empty username
    {"username": 123, "password": "password123"},  # non-string username
    {},
])
def test_register_validation(client, body):
    assert client.post("/api/register", json=body).status_code == 400


def test_wrong_password_rejected(client):
    client.post("/api/register", json={"username": "u2", "password": "password123"})
    response = client.post("/api/login", json={"username": "u2", "password": "wrongpass"})
    assert response.status_code == 401


def test_authentication_required(client):
    assert client.get("/api/tasks").status_code == 401


def test_tampered_token_rejected(client):
    headers = register_and_login(client)
    bad = {"Authorization": headers["Authorization"] + "x"}
    assert client.get("/api/tasks", headers=bad).status_code == 401


def test_expired_token_rejected(client, app):
    with app.app_context():
        token = create_token(1, lifetime=-10)
    response = client.get("/api/tasks", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ---------- creating and reading tasks ----------

def test_create_task(client):
    headers = register_and_login(client)
    add_task(client, headers, "Database Backup", 8)


@pytest.mark.parametrize("priority", [0, 15, True, "high", 2.5])
def test_invalid_priority(client, priority):
    headers = register_and_login(client)
    response = client.post("/api/tasks", json={"title": "T", "priority": priority}, headers=headers)
    assert response.status_code == 400


def test_unknown_task_type_rejected(client):
    headers = register_and_login(client)
    response = client.post(
        "/api/tasks",
        json={"title": "T", "payload": {"type": "launch-rockets"}},
        headers=headers,
    )
    assert response.status_code == 400


def test_users_cannot_see_each_others_tasks(client):
    alice = register_and_login(client, "alice")
    bob = register_and_login(client, "bob")
    task_id = add_task(client, alice)

    assert client.get(f"/api/tasks/{task_id}", headers=alice).status_code == 200
    assert client.get(f"/api/tasks/{task_id}", headers=bob).status_code == 404
    assert client.post(f"/api/tasks/{task_id}/cancel", headers=bob).status_code == 404


def test_pagination_and_status_filter(client):
    headers = register_and_login(client)
    for i in range(5):
        add_task(client, headers, f"T{i}")

    page = client.get("/api/tasks?limit=2&offset=0", headers=headers).get_json()
    assert len(page["tasks"]) == 2
    assert page["tasks"][0]["title"] == "T4"  # newest first

    assert client.get("/api/tasks?limit=1000", headers=headers).status_code == 400
    assert client.get("/api/tasks?status=bogus", headers=headers).status_code == 400
    assert client.get("/api/tasks?status=queued", headers=headers).status_code == 200


def test_cancel_only_works_once(client):
    headers = register_and_login(client)
    task_id = add_task(client, headers)
    assert client.post(f"/api/tasks/{task_id}/cancel", headers=headers).status_code == 200
    assert client.post(f"/api/tasks/{task_id}/cancel", headers=headers).status_code == 404


# ---------- worker behaviour ----------

def test_highest_priority_runs_first(client, db):
    headers = register_and_login(client)
    low = add_task(client, headers, "low", 2)
    high = add_task(client, headers, "high", 9)
    mid = add_task(client, headers, "mid", 5)
    same_as_mid = add_task(client, headers, "mid-later", 5)

    order = [claim_next_task(db)["id"] for _ in range(4)]
    # highest priority first; ties broken by oldest id (FIFO)
    assert order == [high, mid, same_as_mid, low]


def test_task_is_claimed_only_once(client, app, db):
    headers = register_and_login(client)
    add_task(client, headers)

    second_worker = connect(app.config["DATABASE"], autocommit=True)
    try:
        first = claim_next_task(db)
        second = claim_next_task(second_worker)
    finally:
        second_worker.close()

    assert first is not None
    assert second is None


def test_successful_task_completes(client, db):
    headers = register_and_login(client)
    task_id = add_task(client, headers, payload={"type": "sum", "numbers": [1, 2, 3]})

    assert process_one(db) is True
    task = client.get(f"/api/tasks/{task_id}", headers=headers).get_json()

    assert task["status"] == "completed"
    assert task["result"] == {"sum": 6}
    assert process_one(db) is False  # queue is now empty


def test_failed_task_is_retried_then_fails(client, db):
    headers = register_and_login(client)
    # 'numbers' is missing, so the handler raises every time
    task_id = add_task(client, headers, payload={"type": "sum"})

    statuses = []
    for _ in range(3):
        process_one(db)
        task = client.get(f"/api/tasks/{task_id}", headers=headers).get_json()
        statuses.append(task["status"])

    assert statuses == ["queued", "queued", "failed"]
    assert task["attempts"] == 3
    assert "error" in task["result"]


def test_stuck_running_task_is_requeued(client, db):
    headers = register_and_login(client)
    task_id = add_task(client, headers)
    db.execute(
        "UPDATE tasks SET status='running', started_at=datetime('now','-1 hour') WHERE id=?",
        (task_id,),
    )

    assert recover_stuck_tasks(db, timeout_seconds=300) == 1
    task = client.get(f"/api/tasks/{task_id}", headers=headers).get_json()
    assert task["status"] == "queued"


def test_missing_secret_key_refuses_to_start(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app({"DATABASE": str(tmp_path / "x.db")})
