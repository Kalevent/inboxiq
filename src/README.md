# InboxIQ Thin Slice (Auth/Users/Health)

## Prereqs
- Python 3.11, virtualenv, Docker running
- Env: `export FLASK_APP=src.manage:app`
- Local DB: Postgres 15 via compose (`docker compose -f src/docker-compose.yml up -d db`)

## Local run (no Docker)
```bash
source .venv-inboxiq/bin/activate
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/inboxiq
export FLASK_APP=src.manage:app
# install minimal deps
pip install -r src/requirements-inboxiq.lock.txt
# first time only
flask db migrate -d src/migrations -m "init accounts and users"
flask db upgrade -d src/migrations
python src/manage.py
```
Test: `GET /health` → 200, `POST /users` with `{"email":"test@example.com"}`, `POST /auth/login` with `{"email":"test@example.com"}`.
Cache test: `GET /cached-status` (should be cached for 60s when Redis is configured).

## Lockfile refresh
If dependencies change, regenerate the lockfile using the InboxIQ venv:
```bash
source .venv-inboxiq/bin/activate
pip install -r src/requirements-inboxiq.txt
pip freeze > src/requirements-inboxiq.lock.txt
```

### Account + user creation (JSON)
- Create account: `POST /accounts` `{"name":"Acme","seats_limit":3}`
- Create user: `POST /users` `{"email":"a@acme.com","password":"pass","account_id":<account_id>}`
- Login: `POST /auth/login` `{"email":"a@acme.com","password":"pass"}`

## Docker (image)
```bash
docker build -f src/Dockerfile.inboxiq -t inboxiq:latest .
docker run --env-file .env -p 8000:8000 inboxiq:latest
```

## Docker (compose app + db)
```bash
docker compose -f src/docker-compose.yml up -d db
docker build -f src/Dockerfile.inboxiq -t inboxiq:latest .
docker compose -f src/docker-compose.yml up -d app
```

## Deployment checklist
- `DATABASE_URL` set per environment (no SQLite).
- Run `flask db upgrade -d src/migrations` via CI/CD per env (not during image build).
- Image entrypoint: gunicorn `src.app:create_app()` (see `src/Dockerfile.inboxiq`).

## Messaging reminder (specialties / keywords)
- AI customer support
- Email triage
- Ticketing automation
- Sentiment analysis
- SLA routing
- Support analytics
- Gmail/Outlook integration
- Customer experience
