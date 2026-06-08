# AWS Deployment Guide

This backend is ready for deployment on AWS App Runner with PostgreSQL on Amazon RDS.

## Architecture

- App: Django served by Gunicorn
- Static files: WhiteNoise
- Database: Amazon RDS PostgreSQL
- Local development: SQLite by default

## Local vs production database behavior

Local development defaults to SQLite:

```env
USE_SQLITE=True
DATABASE_URL=
```

Production should use PostgreSQL through `DATABASE_URL`:

```env
DATABASE_URL=postgresql://<user>:<password>@<rds-endpoint>:5432/<database>?sslmode=require
```

`DATABASE_URL` always overrides the SQLite settings.

## Required production environment variables

Set these in AWS App Runner:

```env
DEBUG=False
SECRET_KEY=<strong-random-secret-at-least-32-chars>
ALLOWED_HOSTS=<apprunner-domain>,<custom-domain>
DATABASE_URL=postgresql://<user>:<password>@<rds-endpoint>:5432/<database>?sslmode=require
DB_SSLMODE=require
CORS_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<apprunner-domain>,https://<custom-domain>,https://<frontend-domain>
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.yourprovider.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_smtp_username
EMAIL_HOST_PASSWORD=your_smtp_password
DEFAULT_FROM_EMAIL=notifications@jamiiaide.com
```

If Google sign-in is enabled:

```env
GOOGLE_OAUTH_CLIENT_ID=<production-google-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<production-google-client-secret>
```

## Create the RDS database

Provision an Amazon RDS PostgreSQL instance and capture:

1. Database name
2. Username
3. Password
4. Endpoint
5. Port

Make sure the RDS security group allows inbound access from the App Runner service.

## Create the App Runner service

1. Push this repo to GitHub.
2. In AWS App Runner, create a service from the repository.
3. Use these commands.

Build command:

```bash
pip install -r requirements_django.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

Start command:

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8000
```

Port:

```text
8000
```

The [Procfile](/c:/Users/hp/Desktop/jamii-aide-backend/Procfile) already matches the expected Gunicorn entrypoint.

## Authentication and frontend deployment notes

- Public API registration always creates a `user` role.
- `nurse` and `admin` roles must be assigned by an admin.
- Frontend auth routes now include Django-rendered pages at `/signup/`, `/login/`, and `/dashboard/`.
- API auth endpoints remain:
  - `POST /api/auth/register/`
  - `POST /api/auth/login/`
  - `POST /api/auth/google/`
  - `POST /api/auth/refresh/`
  - `GET /api/auth/me/`

## Production validation

Before going live, run:

```bash
python manage.py check --deploy
```

## Notes

- Do not use SQLite in AWS production.
- Do not reuse the local `.env` file in production.
- The local database has already been reconciled and the migration chain is now healthy end-to-end.
