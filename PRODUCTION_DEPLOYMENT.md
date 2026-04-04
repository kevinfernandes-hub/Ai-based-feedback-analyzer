# Production Deployment Guide

## Pre-Deployment Checklist

- [ ] Environment variables are set securely (not in git)
- [ ] Database backups are configured
- [ ] HTTPS/TLS certificates obtained (e.g., Let's Encrypt)
- [ ] API keys rotated (Gemini/Groq)
- [ ] Admin password changed from default
- [ ] `FLASK_SECRET_KEY` is a strong random value (min 32 chars)
- [ ] Rate limiting configured for your expected load
- [ ] Monitoring/logging aggregation set up
- [ ] Health check endpoint is accessible
- [ ] Reverse proxy (nginx) configured
- [ ] Systemd service created and tested
- [ ] Database migrations run
- [ ] Static files collected/minified
- [ ] Error pages customized (404, 500)

## Production Environment Setup

### 1. System Requirements
- Ubuntu 20.04 LTS+ or CentOS 8+
- Python 3.9+
- PostgreSQL 12+ (recommended) or SQLite with daily backups
- Nginx 1.18+
- SSL Certificate (Let's Encrypt recommended)

### 2. Create App User
```bash
sudo useradd -r -m -d /opt/feedback-app feedback-app
sudo chown -R feedback-app:feedback-app /opt/feedback-app
```

### 3. Clone & Setup App
```bash
cd /opt/feedback-app
git clone https://github.com/your-org/feedback-app.git .
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Production Environment Variables
Create `/opt/feedback-app/.env`:
```
FLASK_ENV=production
PORT=5050
HOST=127.0.0.1
FLASK_SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<strong-random-password>

GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-1.5-flash
GROQ_API_KEY=<your-key>
GROQ_MODEL=llama3-8b-8192

BRAND_COLLEGE_NAME=Your College Name
BRAND_LOGO_URL=/static/img/logo.png

INTERNAL_METRICS_KEY=<random-key-for-monitoring>
```

**Important:** Never commit `.env` to git. Add to `.gitignore`.

### 5. Database Setup
Initialize database:
```bash
export FLASK_ENV=production
export FLASK_SECRET_KEY="your-strong-key"
python3 -c "from app import init_db; init_db()"
```

For PostgreSQL migration (recommended for production):
```bash
# Configure app.py to use PostgreSQL:
# conn = psycopg2.connect(os.getenv('DATABASE_URL'))
pip install psycopg2-binary
```

### 6. Systemd Service
Create `/etc/systemd/system/feedback-app.service`:
```ini
[Unit]
Description=AI Feedback Analyzer
After=network.target

[Service]
User=feedback-app
WorkingDirectory=/opt/feedback-app
Environment="PATH=/opt/feedback-app/venv/bin"
Environment="FLASK_ENV=production"
EnvironmentFile=/opt/feedback-app/.env
ExecStart=/opt/feedback-app/venv/bin/gunicorn -w 4 -b 127.0.0.1:5050 --timeout 120 --access-logfile /var/log/feedback-app/access.log --error-logfile /var/log/feedback-app/error.log wsgi:app
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable feedback-app
sudo systemctl start feedback-app
sudo systemctl status feedback-app
```

### 7. Nginx Reverse Proxy
Create `/etc/nginx/sites-available/feedback-app`:
```nginx
upstream feedback_app {
    server 127.0.0.1:5050;
}

server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 10M;

    location / {
        proxy_pass http://feedback_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /static/ {
        alias /opt/feedback-app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /healthz {
        proxy_pass http://feedback_app;
        access_log off;
    }
}
```

Enable:
```bash
sudo ln -s /etc/nginx/sites-available/feedback-app /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 8. SSL Certificate (Let's Encrypt)
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot certonly --nginx -d your-domain.com
```

### 9. Database Backups
Daily backup cron:
```bash
0 2 * * * backup_user: /opt/feedback-app/backup.sh
```

Create `/opt/feedback-app/backup.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/backups/feedback-app"
mkdir -p $BACKUP_DIR
sqlite3 /opt/feedback-app/instance/feedback.db ".backup $BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).db"
find $BACKUP_DIR -mtime +30 -delete
```

### 10. Monitoring & Logging
Health check endpoint:
```bash
curl https://your-domain.com/healthz
# Should return: {"status": "ok", "database": "connected"}
```

View logs:
```bash
sudo tail -f /var/log/feedback-app/error.log
sudo journalctl -u feedback-app -f
```

Metrics endpoint (internal only):
```bash
curl -H "X-Internal-Key: YOUR_INTERNAL_METRICS_KEY" https://your-domain.com/metrics
```

### 11. Security Hardening
- [ ] Set `SECRET_KEY` to strong random value
- [ ] Run behind reverse proxy (nginx)
- [ ] Enable HTTPS with HSTS
- [ ] Set `SESSION_COOKIE_SECURE=True` in production
- [ ] Use strong admin passwords
- [ ] Rotate API keys quarterly
- [ ] Keep dependencies updated: `pip install --upgrade pip && pip install -r requirements.txt --upgrade`
- [ ] Monitor logs for suspicious activity
- [ ] Set up fail2ban for rate limiting

```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

### 12. Performance Tuning
- Gunicorn workers: `2 + (2 * CPU_count)` → for 4 cores: `-w 10`
- Database connection pooling: enabled by default
- Cache static files: 30+ days
- Gzip compression in nginx

### 13. Scaling (Future)
- Database: Migrate from SQLite to PostgreSQL
- Cache layer: Add Redis for sessions
- Load balancer: Use HAProxy or AWS ALB
- CDN: CloudFlare or AWS CloudFront for static assets
- Monitoring: ELK Stack or DataDog

## Troubleshooting

**502 Bad Gateway:**
```bash
sudo systemctl status feedback-app
sudo tail -f /var/log/feedback-app/error.log
```

**Database locked (SQLite):**
- Switch to PostgreSQL for multi-worker deployments

**High memory usage:**
- Reduce Gunicorn workers
- Clear old sessions/logs

**Slow form submissions:**
- Check database performance: `sqlite3 instance/feedback.db "ANALYZE;"`
- Monitor network round-trips
- Consider async task queue (Celery) for AI operations

## Support & Updates
- Check logs regularly
- Subscribe to dependency security alerts
- Run `pip audit` monthly
- Test updates in staging first
