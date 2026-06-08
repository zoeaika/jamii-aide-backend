# DigitalOcean Deployment Guide

This backend is configured for rapid deployment on **DigitalOcean App Platform** with a Managed PostgreSQL Database.

## Architecture

- **App Platform:** Django served by Gunicorn
- **Static files:** WhiteNoise (served directly by the app)
- **Database:** DigitalOcean Managed PostgreSQL
- **Local development:** SQLite by default

## 1. Create the Database

1. In the DigitalOcean Control Panel, create a new **Managed Database** (PostgreSQL 12+).
2. Once provisioned, copy the **Connection String** (URI) from the connection details panel.
3. Ensure you check the "Trusted Sources" setting to allow your App Platform app to connect securely once it is created.

## 2. Required Production Environment Variables

When setting up your App in the DigitalOcean App Platform dashboard, add the following environment variables. DigitalOcean supports a Bulk Editor for easy pasting.

```env
DEBUG=False
SECRET_KEY=<strong-random-secret-at-least-32-chars>
ALLOWED_HOSTS=${APP_DOMAIN},<your-custom-domain>
DATABASE_URL=<your-digitalocean-postgres-connection-string>
DB_SSLMODE=require
CORS_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://${APP_DOMAIN},https://<custom-domain>,https://<frontend-domain>
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True
```

*(Note: `${APP_DOMAIN}` is automatically populated by DigitalOcean).*

If Google sign-in is enabled:

```env
GOOGLE_OAUTH_CLIENT_ID=<production-google-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<production-google-client-secret>
```

## 3. Create the DigitalOcean App

1. Push your repository to GitHub.
2. In DigitalOcean, go to **Apps** -> **Create App**.
3. Connect your GitHub repository.
4. DO will automatically detect a Python environment. Configure the component as a **Web Service**.

### Commands

Update the configuration with these commands if they aren't automatically parsed from your `Procfile`:

**Build Command:**

```bash
pip install -r requirements_django.txt && python manage.py collectstatic --noinput && python manage.py migrate
```

**Start/Run Command:**

```bash
gunicorn config.wsgi:application --bind 0.0.0.0:8080
```

**HTTP Port:** `8080` (or `8000` depending on your binding).

## 4. Production Validation

Once the deployment is live, you can access the App Platform Console (terminal) directly from the DigitalOcean dashboard to run:

```bash
python manage.py check --deploy
python manage.py createsuperuser
```

This will allow you to create your initial admin account to assign `nurse` and `admin` roles via the `/admin/` portal.
