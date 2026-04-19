# TaskFlow API

Task management backend built with FastAPI.

## Setup

```bash
cd examples/taskflow-api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn src.main:app --reload --port 9001
```

API docs: http://localhost:9001/docs

## Modules

- `/auth` — JWT login, registration, password reset, RBAC permissions
- `/tasks` — CRUD, assignment, status transitions, comments
- `/notifications` — In-app notifications, email/push queue, preferences
- `/billing` — Plans, subscriptions, invoices, usage tracking

## Test Users

Use the `/auth/register` endpoint to create accounts, or seed via:

```bash
curl -X POST http://localhost:9001/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@test.com","password":"pass1234","full_name":"Alice Kim"}'
```
