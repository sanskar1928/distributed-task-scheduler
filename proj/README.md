# Distributed Task Scheduler

A task scheduling service built with Flask and SQLite. Users register, log in,
and submit prioritized tasks. Separate worker processes pick up the
highest-priority task first and run it.

## Architecture

```
Client --HTTP--> Flask API (run.py) --writes--> SQLite <--claims-- Worker(s) (worker.py)
```

- **API** (`run.py`): registration, login, create/list/get/cancel tasks.
- **Workers** (`worker.py`): run as separate processes; start as many as you like.
- **Atomic claiming**: a worker takes a task with `BEGIN IMMEDIATE` (write lock)
  and marks it `running` in the same transaction, so no task is run twice.
- **Priority queue**: `ORDER BY priority DESC, id ASC` (10 = highest, ties are FIFO),
  backed by the index `(status, priority DESC, id ASC)`.
- **Reliability**: failed tasks are retried up to 3 times; tasks stuck in
  `running` (e.g. worker crashed) are re-queued after `TASK_TIMEOUT` seconds.
- **Security**: salted PBKDF2-SHA256 (600,000 iterations), HMAC-signed tokens
  with 1-hour expiry, parameterized SQL, per-user access checks.

Limitation: SQLite means all workers must share one machine. Moving to
PostgreSQL (with `SELECT ... FOR UPDATE SKIP LOCKED`) would allow workers on
different machines.

## Setup

```bash
pip install -r requirements.txt
export SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))')

python run.py        # terminal 1: API on http://127.0.0.1:5000
python worker.py     # terminal 2: worker (start more if you want)
```

Use the same `SECRET_KEY` and `DATABASE` (default `tasks.db`) in every terminal.
If you have an old `tasks.db` from the previous version, delete it: the schema changed.

## API

| Method | Path | Description |
|---|---|---|
| POST | `/api/register` | `{"username", "password"}` |
| POST | `/api/login` | returns a token |
| POST | `/api/tasks` | `{"title", "priority": 1-10, "payload": {"type": ...}}` |
| GET | `/api/tasks?status=&limit=&offset=` | your tasks, newest first |
| GET | `/api/tasks/<id>` | one task |
| POST | `/api/tasks/<id>/cancel` | only while `queued` |

Task types (`payload.type`): `echo` (default), `sum` (`numbers`: list), `sleep` (`seconds`: 0-10).
Add your own in `backend/handlers.py`.

```bash
curl -X POST localhost:5000/api/register -H "Content-Type: application/json" \
  -d '{"username":"sam","password":"secret123"}'
TOKEN=$(curl -s -X POST localhost:5000/api/login -H "Content-Type: application/json" \
  -d '{"username":"sam","password":"secret123"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -X POST localhost:5000/api/tasks -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Add numbers","priority":8,"payload":{"type":"sum","numbers":[1,2,3]}}'
curl localhost:5000/api/tasks -H "Authorization: Bearer $TOKEN"
```

## Tests

```bash
pytest
```

## `cpp/`

A standalone C++ demo of a priority queue (`std::priority_queue`), the same idea
the scheduler implements in SQL. It is not connected to the Python service.
