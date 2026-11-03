import pytest

from backend.app import create_app


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "test.db"

    app = create_app()

    app.config.update({
        "TESTING": True,
        "DATABASE": str(db_path),
        "SECRET_KEY": "test-secret-key",
        "SCHEDULER_STARTED": True
    })

    from backend.database import init_db
    init_db(app)

    with app.test_client() as client:
        yield client


def register_and_login(client):
    client.post("/api/register", json={
        "username": "testuser",
        "password": "password123"
    })

    response = client.post("/api/login", json={
        "username": "testuser",
        "password": "password123"
    })

    return response.get_json()["token"]


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200


def test_register_and_login(client):
    response = client.post("/api/register", json={
        "username": "user1",
        "password": "password123"
    })

    assert response.status_code == 201

    response = client.post("/api/login", json={
        "username": "user1",
        "password": "password123"
    })

    assert response.status_code == 200
    assert "token" in response.get_json()


def test_create_task(client):
    token = register_and_login(client)

    response = client.post(
        "/api/tasks",
        json={
            "title": "Database Backup",
            "priority": 8,
            "payload": {"type": "backup"}
        },
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 201


def test_authentication_required(client):
    response = client.get("/api/tasks")

    assert response.status_code == 401


def test_invalid_priority(client):
    token = register_and_login(client)

    response = client.post(
        "/api/tasks",
        json={
            "title": "Invalid Task",
            "priority": 15
        },
        headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 400