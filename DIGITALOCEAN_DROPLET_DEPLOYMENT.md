# DigitalOcean Droplet Deployment Guide (Django Backend)

This guide deploys the Jamii Aide backend on a DigitalOcean **Droplet** (Ubuntu) using:

- Gunicorn (app server)
- Nginx (reverse proxy)
- systemd (process manager)
- PostgreSQL (recommended: DigitalOcean Managed PostgreSQL)

This is different from App Platform. Use this guide when you want full server control.

## 0. Prerequisites

- Ubuntu 22.04/24.04 Droplet
- Domain name pointed to droplet public IP (recommended)
- SSH access as a sudo user
- Repository access (GitHub)
- PostgreSQL connection string ready (or local PostgreSQL installed)

## 1. SSH into the Droplet

```bash
ssh root@YOUR_DROPLET_IP
```

If using a non-root sudo user:

```bash
ssh youruser@YOUR_DROPLET_IP
```

## 2. Install System Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git curl
```

Optional (if building some Python packages from source):

```bash
sudo apt install -y build-essential libpq-dev
```

## 3. Create Application Directory

```bash
sudo mkdir -p /opt/jamii-aide-backend
sudo chown -R $USER:$USER /opt/jamii-aide-backend
cd /opt/jamii-aide-backend
```

## 4. Pull the Code

```bash
git clone <YOUR_REPO_URL> .
```

If already cloned:

```bash
git pull origin main
```

## 5. Create and Activate Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements_django.txt
```

## 6. Create Production Environment File

Create `/opt/jamii-aide-backend/.env`:

```env
DEBUG=False
SECRET_KEY=<strong-random-secret-at-least-32-chars>
ALLOWED_HOSTS=<your-domain>,<www-your-domain>,<droplet-ip>

# Database selection
USE_SQLITE=False
DATABASE_URL=postgresql://<user>:<password>@<host>:5432/<db>?sslmode=require
DB_SSLMODE=require
DB_CONN_MAX_AGE=60

# CORS/CSRF
CORS_ORIGINS=https://<frontend-domain>
CSRF_TRUSTED_ORIGINS=https://<your-domain>,https://<frontend-domain>

# Security
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.yourprovider.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_smtp_username
EMAIL_HOST_PASSWORD=your_smtp_password
DEFAULT_FROM_EMAIL=notifications@jamiiaide.com

# Optional Google OAuth
GOOGLE_OAUTH_CLIENT_ID=<production-google-client-id>
GOOGLE_OAUTH_CLIENT_SECRET=<production-google-client-secret>
```

Notes:

- `DATABASE_URL` takes priority in this project.
- Do not use local development `.env` values in production.
- Keep `.env` permissions restricted.

```bash
chmod 600 /opt/jamii-aide-backend/.env
```

## 7. Run Django Setup Commands

```bash
cd /opt/jamii-aide-backend
source venv/bin/activate
python manage.py collectstatic --noinput
python manage.py migrate
python manage.py check --deploy
python manage.py createsuperuser
```

## 8. Configure Gunicorn as a systemd Service

Create `/etc/systemd/system/jamii-aide.service`:

```ini
[Unit]
Description=Jamii Aide Django Backend
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/jamii-aide-backend
Environment="PATH=/opt/jamii-aide-backend/venv/bin"
ExecStart=/opt/jamii-aide-backend/venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 3 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Set permissions and start service:

```bash
sudo chown -R www-data:www-data /opt/jamii-aide-backend
sudo systemctl daemon-reload
sudo systemctl enable jamii-aide
sudo systemctl start jamii-aide
sudo systemctl status jamii-aide
```

Check logs:

```bash
sudo journalctl -u jamii-aide -f
```

## 9. Configure Nginx Reverse Proxy

Create `/etc/nginx/sites-available/jamii-aide`:

```nginx
server {
    listen 80;
    server_name <your-domain> <www-your-domain>;

    client_max_body_size 25M;

    location /static/ {
        alias /opt/jamii-aide-backend/staticfiles/;
    }

    location /media/ {
        alias /opt/jamii-aide-backend/media/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
```

Enable and reload Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/jamii-aide /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## 10. Enable HTTPS with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <your-domain> -d <www-your-domain>
```

Verify auto-renewal:

```bash
sudo certbot renew --dry-run
```

## 11. Open Firewall (if UFW enabled)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

## 12. Verify Deployment

- API root: `https://<your-domain>/api/`
- Admin: `https://<your-domain>/admin/`
- Auth endpoint: `POST https://<your-domain>/api/auth/login/`

Useful checks:

```bash
sudo systemctl status jamii-aide
sudo systemctl status nginx
sudo journalctl -u jamii-aide -n 200 --no-pager
curl -I https://<your-domain>/api/
```

## 13. Updating the Backend

```bash
cd /opt/jamii-aide-backend
git pull origin main
source venv/bin/activate
pip install -r requirements_django.txt
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart jamii-aide
```

## 14. Common Issues

1. 502 Bad Gateway

- Gunicorn is down or wrong bind target.
- Check `sudo systemctl status jamii-aide` and `journalctl` logs.

2. CORS errors in browser

- Add frontend origin to `CORS_ORIGINS`.
- Restart service after `.env` changes.

3. CSRF failed

- Add HTTPS frontend/backend domains to `CSRF_TRUSTED_ORIGINS`.

4. Database connection errors

- Validate `DATABASE_URL` credentials and network allowlist.
- If using Managed PostgreSQL, ensure droplet IP is trusted.

5. No API logs visible

- This project logs API requests to console via app logging.
- Use `sudo journalctl -u jamii-aide -f` while making requests.

## 15. Recommended Production Hardening

- Disable password SSH, use SSH keys only.
- Disable root SSH login.
- Regularly patch OS packages (`apt update && apt upgrade`).
- Rotate secrets and DB credentials.
- Add monitoring/alerts (DigitalOcean Monitoring, uptime checks).
- Enable automated database backups.
