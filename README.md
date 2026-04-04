## AI-based Feedback Analyzer

This is a Flask application for collecting student feedback, generating OBE attainment analytics, and exporting reports.

## Production Readiness Changes

- Enforced secret key requirement in production
- Added secure session defaults and security headers
- Added health endpoint: `/healthz`
- Added WSGI entrypoint: `wsgi.py`
- Added Gunicorn dependency for production serving
- Added environment template: `.env.example`
- Migrated Gemini integration to `google-genai` SDK

## Local Development

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app in development mode:

```bash
FLASK_ENV=development FLASK_DEBUG=1 python app.py
```

App runs at `http://127.0.0.1:5050` by default.

## Production Run (Gunicorn)

1. Copy environment template and set real values:

```bash
cp .env.example .env
```

2. Export environment variables from `.env` (or set in your platform secrets manager).
3. Start with Gunicorn:

```bash
gunicorn -c gunicorn.conf.py wsgi:app
```

Or use the included `Procfile` on platforms like Render/Railway/Heroku.

## Required Environment Variables

- `FLASK_ENV=production`
- `FLASK_SECRET_KEY` (must be set and strong in production)
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`

## Optional Environment Variables

- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `GROQ_API_KEY`, `GROQ_MODEL`
- `PORT`, `HOST`
- `WEB_CONCURRENCY`, `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`, `GUNICORN_LOG_LEVEL`

## Health Check

Use `GET /healthz` for container/lb health checks.

## Publish Form Link (Google Form Style)

Each created form now gets a public tokenized URL.

- Admin dashboard includes `Copy Link` actions.
- Shared links follow this pattern: `/f/<public_token>`.
- Only open forms are available through public links.

Example:

```text
https://your-domain.com/f/abcd1234ef56
```

Students can submit directly from that link without selecting from the dropdown list.

## Production Release Checklist

- Set a strong `FLASK_SECRET_KEY` and real admin password.
- Keep `.env` private and rotate any exposed API keys.
- Configure one hosted LLM provider key (`GEMINI_API_KEY` or `GROQ_API_KEY`).
- Run the app with Gunicorn (`wsgi:app`) behind HTTPS.
- Verify `/healthz` in your deployment health checks.
- Test admin login, form creation, share link (`/f/<token>`), and submission flow.


