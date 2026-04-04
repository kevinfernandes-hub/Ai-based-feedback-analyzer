# Quick Start: Production Deployment

## TL;DR - Deploy in 10 Minutes (Staging)

```bash
# 1. Prepare server
sudo apt update && sudo apt install -y python3.11 python3.11-venv supervisor nginx certbot python3-certbot-nginx

# 2. Clone and setup
cd /opt
sudo git clone https://github.com/your-org/feedback-app.git
cd feedback-app
sudo python3.11 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt

# 3. Configure environment
sudo cp .env.template .env
sudo nano .env  # Edit with your keys

# 4. Create app user
sudo useradd -r -m feedback-app

# 5. Setup systemd
sudo cp systemd-service.template /etc/systemd/system/feedback-app.service
sudo systemctl daemon-reload
sudo systemctl enable feedback-app
sudo systemctl start feedback-app

# 6. Setup reverse proxy
sudo cp nginx-config.template /etc/nginx/sites-available/feedback-app
sudo nano /etc/nginx/sites-available/feedback-app  # Edit domain
sudo ln -s /etc/nginx/sites-available/feedback-app /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 7. Setup SSL
sudo certbot certonly --nginx -d your-domain.com

# 8. Verify
curl https://your-domain.com/healthz
echo "✅ Deployed!"
```

---

## Full 1-Hour Production Setup

### Prerequisites Check (5 min)
- [ ] Ubuntu 20.04 LTS+ server (2+ CPU, 2GB+ RAM)
- [ ] Domain name with DNS configured
- [ ] SSH access with key-based auth
- [ ] Sudo privileges
- [ ] API keys: GEMINI_API_KEY and/or GROQ_API_KEY

### System Preparation (10 min)

```bash
# Update system
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv supervisor nginx certbot \
    python3-certbot-nginx build-essential curl git

# Create app directory
sudo mkdir -p /opt/feedback-app
sudo chown $USER:$USER /opt/feedback-app

# Create app user
sudo useradd -r -m -d /opt/feedback-app feedback-app

# Create log directory
sudo mkdir -p /var/log/feedback-app
sudo chown feedback-app:feedback-app /var/log/feedback-app
sudo chmod 755 /var/log/feedback-app
```

### Application Setup (15 min)

```bash
# Clone repository
cd /opt/feedback-app
git clone https://github.com/your-org/feedback-app.git .

# Setup Python environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.template .env

# Generate secure secret key
python3 -c "import secrets; print(secrets.token_hex(32))" > SECRET_KEY.txt

# Edit .env with production values
nano .env  # Add:
# FLASK_SECRET_KEY=<content from SECRET_KEY.txt>
# ADMIN_USERNAME=admin
# ADMIN_PASSWORD=<strong-password>
# GEMINI_API_KEY=<your-key>
# BRAND_COLLEGE_NAME=Your College

# Secure the env file
chmod 600 .env

# Initialize database
export FLASK_ENV=production
python3 -c "from app import init_db; init_db()"
```

### Service Setup (10 min)

```bash
# Setup systemd service
sudo cp systemd-service.template /etc/systemd/system/feedback-app.service
sudo chmod 644 /etc/systemd/system/feedback-app.service

# Edit paths if different (optional):
sudo nano /etc/systemd/system/feedback-app.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable feedback-app
sudo systemctl start feedback-app

# Verify running
sudo systemctl status feedback-app

# Check health
curl -I http://127.0.0.1:5050/healthz
# Should see: HTTP/1.1 200 OK
```

### Web Server Setup (10 min)

```bash
# Setup Nginx reverse proxy
sudo cp nginx-config.template /etc/nginx/sites-available/feedback-app

# Edit domain names
sudo nano /etc/nginx/sites-available/feedback-app
# Replace: your-domain.com with actual domain

# Enable site
sudo ln -s /etc/nginx/sites-available/feedback-app /etc/nginx/sites-enabled/

# Remove default site
sudo rm /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test configuration
sudo nginx -t
# Should show: "test is successful"

# Reload Nginx
sudo systemctl reload nginx
```

### SSL Certificate (10 min)

```bash
# Get certificate from Let's Encrypt
sudo certbot certonly --nginx -d your-domain.com

# Verify renewal works
sudo certbot renew --dry-run

# Certificate auto-renews via systemd timer
sudo systemctl list-timers certbot
```

### Verification (10 min)

```bash
# Test HTTP → HTTPS redirect
curl -I http://your-domain.com
# Should redirect to https

# Test HTTPS endpoint
curl -I https://your-domain.com
# Should return: HTTP/1.1 200 OK

# Test health check
curl https://your-domain.com/healthz | python3 -m json.tool
# Should show: {"status": "ok", "database": "connected"}

# Check security headers
curl -I https://your-domain.com | grep -i "strict-transport-security"
# Should show HSTS header

# Test admin login
# Visit: https://your-domain.com
# Login with credentials from .env
# Create test form to verify everything works
```

---

## Post-Deployment Checklist

### Day 1
- [ ] Verify app logs: `sudo tail -f /var/log/feedback-app/app.log`
- [ ] Test admin login and form creation
- [ ] Test public form submission
- [ ] Check health endpoint daily: `curl https://your-domain.com/healthz`
- [ ] Monitor disk space: `df -h`

### Day 3-7
- [ ] No errors in log files (check daily)
- [ ] Performance metrics stable (check via `/metrics` endpoint)
- [ ] Database backups automated
- [ ] SSL certificate verified valid

### Weekly
- [ ] Dependency security check: `pip audit`
- [ ] Log file rotation working (check `ls -la /var/log/feedback-app/`)
- [ ] Monitoring alerts configured (if using Grafana/DataDog)

### Monthly
- [ ] Security audit (check OWASP Top 10)
- [ ] Full backup restore test
- [ ] Update dependencies (`pip install --upgrade -r requirements.txt`)

---

## Emergency Procedures

### App Won't Start
```bash
sudo journalctl -u feedback-app -n 50
# Check error message
# Likely causes: .env missing, API key invalid, database corrupted

# Restart
sudo systemctl restart feedback-app
sudo systemctl status feedback-app
```

### High CPU/Memory
```bash
ps aux | grep gunicorn
top -p <PID>

# Reduce workers in systemd service:
sudo nano /etc/systemd/system/feedback-app.service
# Change: ExecStart=... --workers=2 (reduce from 4)

sudo systemctl daemon-reload
sudo systemctl restart feedback-app
```

### Port 5050 Already in Use
```bash
sudo lsof -i :5050
sudo kill -9 <PID>
sudo systemctl restart feedback-app
```

### Database Locked
```bash
# Use PostgreSQL instead (see PRODUCTION_DEPLOYMENT.md)
# Or for SQLite:
sudo -u feedback-app sqlite3 /opt/feedback-app/instance/feedback.db "VACUUM;"
```

---

## Production URLs

After deployment:
- Main app: `https://your-domain.com`
- Admin dashboard: `https://your-domain.com/dashboard`
- Health check: `https://your-domain.com/healthz`
- Public form: `https://your-domain.com/f/<public-token>`
- Metrics: `https://your-domain.com/metrics` (requires auth)

---

## Monitoring

### View Logs
```bash
# Real-time logs
sudo tail -f /var/log/feedback-app/app.log

# Last 100 lines
sudo tail -100 /var/log/feedback-app/app.log

# Search for errors
sudo grep ERROR /var/log/feedback-app/app.log

# Count requests per hour
sudo awk '{print $4}' /var/log/feedback-app/app.log | cut -d: -f1-2 | sort | uniq -c
```

### Health Monitoring Script
```bash
#!/bin/bash
# Save as: /opt/feedback-app/health_check.sh

while true; do
    STATUS=$(curl -s -w "%{http_code}" -o /dev/null https://your-domain.com/healthz)
    if [ "$STATUS" != "200" ]; then
        echo "⚠️ Health check failed: HTTP $STATUS"
        sudo systemctl restart feedback-app
    else
        echo "✅ $(date): Health check passed"
    fi
    sleep 300  # Every 5 minutes
done
```

Run with: `nohup bash health_check.sh > health_check.log 2>&1 &`

---

## Scaling for Growth

### 100-1000 students
✅ Current setup sufficient  
- Increase Gunicorn workers: `--workers=4`
- Enable database query caching

### 1000-5000 students
⚠️ Consider:
- Migrate database to PostgreSQL
- Add Redis for sessions/caching
- Enable CDN for static assets

### 5000+ students
🔴 Implement:
- Multi-server load balancing (HAProxy/AWS ALB)
- Database read replicas
- Separate API and background workers (Celery)
- Log aggregation (ELK Stack)
- Application metrics (Prometheus)

---

## Support Resources

- **Deployment Documentation**: [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md)
- **Testing Guide**: [PRODUCTION_TESTING.md](PRODUCTION_TESTING.md)
- **Checklist**: [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md)
- **Hardening Summary**: [PRODUCTION_HARDENING_SUMMARY.md](PRODUCTION_HARDENING_SUMMARY.md)

---

## Contact & Troubleshooting

**Issues?** Check:
1. Logs: `sudo tail -100 /var/log/feedback-app/app.log`
2. Service status: `sudo systemctl status feedback-app`
3. Network connectivity: `curl -I https://your-domain.com`
4. SSL validity: `sudo certbot certificates`

**Still stuck?** Try:
- Restart: `sudo systemctl restart feedback-app`
- Check disk space: `df -h`
- Verify .env loaded: `cat /proc/<PID>/environ | tr '\0' '\n' | grep FLASK`
