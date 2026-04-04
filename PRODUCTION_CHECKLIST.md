# Production Readiness Checklist

## Pre-Deployment (Week Before)

### Infrastructure & Security
- [ ] **Domain Name**: Registered and DNS records configured
- [ ] **SSL Certificate**: Ordered (Let's Encrypt recommended)
- [ ] **Server**: Provisioned (Ubuntu 20.04 LTS+, 2+ CPU cores, 2GB+ RAM, 50GB+ disk)
- [ ] **Network**: Firewall configured (80, 443 open; 5050 closed externally)
- [ ] **SSH**: Key-based authentication configured, root login disabled
- [ ] **Updates**: `sudo apt update && sudo apt upgrade -y`
- [ ] **Settings**: NTP synced for accurate timestamps
- [ ] **Monitoring**: Tools installed (htop, nethogs, fail2ban)

### Database & Backups
- [ ] **Database**: Initialized and migrated
- [ ] **Backup Strategy**: Script created and tested
- [ ] **Backup Location**: Off-server storage configured
- [ ] **Restore Test**: Verified restore works (critical!)
- [ ] **Retention Policy**: Determined (recommend 30+ days)

### Application & Dependencies
- [ ] **Git**: Repository cloned (no uncommitted changes)
- [ ] **Python**: Version verified (3.9+)
- [ ] **Virtual Environment**: Created at `/opt/feedback-app/venv`
- [ ] **Dependencies**: Installed via `pip install -r requirements.txt`
- [ ] **Dependencies Audit**: `pip audit` shows no critical vulnerabilities
- [ ] **Tests**: All unit tests pass (`pytest` or equivalent)
- [ ] **Linting**: Code passes pylint/flake8 (optional but recommended)

### Configuration & Secrets
- [ ] **Environment File**: `.env` created with production values
  - [ ] `FLASK_SECRET_KEY`: Strong random value (32+ characters)
  - [ ] `ADMIN_USERNAME` & `ADMIN_PASSWORD`: Changed from default
  - [ ] `GEMINI_API_KEY` or `GROQ_API_KEY`: Valid and tested
  - [ ] `INTERNAL_METRICS_KEY`: Unique random value
- [ ] **No Secrets in Git**: `.env` added to `.gitignore`
- [ ] **Environment File Secured**: `chmod 600 /opt/feedback-app/.env`
- [ ] **Secrets Rotation**: Plan documented

### Application Features
- [ ] **Admin Login**: Tested with production credentials
- [ ] **Student Form**: Tested with public token
- [ ] **AI Features**: Tested (question generation, mapping suggestions)
- [ ] **Export/Reports**: Tested (PDF generation working)
- [ ] **Error Handling**: Graceful errors on missing API keys
- [ ] **Session Management**: Admin logout and re-login working

### Performance & Load
- [ ] **Health Check**: `/healthz` endpoint returns 200
- [ ] **Metrics Endpoint**: `/metrics` accessible with correct key
- [ ] **Database Performance**: `ANALYZE` run on SQLite
- [ ] **Static Files**: Optimized (CSS/JS minified, images compressed - optional)
- [ ] **Response Times**: Logged and within acceptable range (<2s for normal routes)
- [ ] **Rate Limiting**: Verified with load test (use Apache Bench or similar)

### Security & Hardening
- [ ] **SECRET_KEY**: Set to strong random value
- [ ] **Session Cookies**: `SECURE`, `HTTPONLY`, `SAMESITE` set
- [ ] **CORS**: Configured if needed
- [ ] **SQL Injection**: Input validation present on all endpoints
- [ ] **XSS Prevention**: Output escaped in templates
- [ ] **CSRF Protection**: Enabled (Flask default)
- [ ] **Headers**: Content-Security-Policy, X-Frame-Options, HSTS set
- [ ] **Dependencies**: No known vulnerabilities (`pip audit`)
- [ ] **Code Review**: Security-critical code reviewed by peer

---

## Deployment Day (Step-by-Step)

### 1. System Preparation
```bash
sudo useradd -r -m -d /opt/feedback-app feedback-app
sudo chown -R feedback-app:feedback-app /opt/feedback-app
sudo mkdir -p /var/log/feedback-app
sudo chown feedback-app:feedback-app /var/log/feedback-app
sudo chmod 755 /var/log/feedback-app
```
- [ ] App user created
- [ ] Directories owned by correct user

### 2. Application Deployment
```bash
cd /opt/feedback-app
git clone https://github.com/your-org/feedback-app.git .
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```
- [ ] Git clone successful
- [ ] Virtual environment created
- [ ] Dependencies installed

### 3. Configuration
```bash
cp .env.template .env
# Edit .env with production values
chmod 600 /opt/feedback-app/.env
```
- [ ] `.env` created with all required values
- [ ] Permissions set to `600` (user-read/write only)

### 4. Database Initialization
```bash
export FLASK_ENV=production
export FLASK_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
# If custom startup needed:
# python3 -c "from app import init_db; init_db()"
```
- [ ] Database initialized

### 5. Systemd Service Setup
```bash
sudo cp systemd-service.template /etc/systemd/system/feedback-app.service
# Edit paths if needed
sudo systemctl daemon-reload
sudo systemctl enable feedback-app
sudo systemctl start feedback-app
sudo systemctl status feedback-app
```
- [ ] Systemd service created
- [ ] Service enabled on boot
- [ ] Service started successfully

### 6. Verify Application
```bash
curl http://127.0.0.1:5050/healthz
# Should return: {"status": "ok", "database": "connected"}
```
- [ ] Health endpoint responds with 200

### 7. Nginx Setup
```bash
sudo cp nginx-config.template /etc/nginx/sites-available/feedback-app
# Edit domain names
sudo ln -s /etc/nginx/sites-available/feedback-app /etc/nginx/sites-enabled/
sudo nginx -t  # Verify syntax
sudo systemctl reload nginx
```
- [ ] Nginx config validated
- [ ] Nginx reloaded
- [ ] DNS propagated (check `nslookup your-domain.com`)

### 8. SSL Certificate (Let's Encrypt)
```bash
sudo certbot certonly --nginx -d your-domain.com
# Verify certificate renewal:
sudo certbot renew --dry-run
```
- [ ] Certificate obtained
- [ ] Auto-renewal configured

### 9. Firewall Configuration (if applicable)
```bash
sudo ufw allow 22/tcp  # SSH
sudo ufw allow 80/tcp  # HTTP
sudo ufw allow 443/tcp # HTTPS
sudo ufw enable
```
- [ ] Firewall rules correct
- [ ] SSH still accessible
- [ ] App ports open to web only

### 10. First Connection Test
```bash
curl https://your-domain.com
# Should return admin login page
curl https://your-domain.com/healthz
# Should return JSON health status
```
- [ ] HTTP redirects to HTTPS
- [ ] HTTPS works
- [ ] Health endpoint responds

### 11. Admin Login Verification
- [ ] Navigate to https://your-domain.com
- [ ] Login with admin user
- [ ] Create test form
- [ ] Verify form renders
- [ ] Logout and verify redirect

### 12. Public Form Test
- [ ] Create form as admin
- [ ] Copy public link or QR code
- [ ] Open in incognito/private browser
- [ ] Submit test feedback
- [ ] Verify submission recorded

### 13. Logging & Monitoring Setup
```bash
sudo tail -f /var/log/feedback-app/app.log
sudo journalctl -u feedback-app -f
curl -H "X-Internal-Key: YOUR_KEY" https://your-domain.com/metrics
```
- [ ] Logs accessible
- [ ] Metrics endpoint responds
- [ ] No errors in logs

---

## Post-Deployment (Day 1-7)

### Monitoring
- [ ] **Error Logs**: Checked for any ERRORs (at least daily first week)
- [ ] **Performance**: Response times normal, no timeouts
- [ ] **API Keys**: All working (Gemini/Groq accessible)
- [ ] **Database**: Backups running automatically
- [ ] **Disk Space**: Monitored (alerts if >80% full)

### Backups
- [ ] **First Backup**: Manually triggered and verified
- [ ] **Restore Test**: Confirmed backup is restorable
- [ ] **Cron Job**: Automatic backups scheduled and running

### Security
- [ ] **SSL Test**: Qualys SSL Labs test (grade A+ goal)
- [ ] **Security Headers**: Verified via https://securityheaders.com
- [ ] **OWASP**: Top 10 checked (SQL injection, XSS, CSRF, etc.)
- [ ] **API Keys**: No keys in logs or errors exposed to users

### User Connectivity
- [ ] **Desktop**: Admin login and form creation tested
- [ ] **Mobile**: Form submission on phone tested
- [ ] **Network**: VPN and non-VPN access tested
- [ ] **Slow Network**: Tested on 3G connection (if needed)

### Optimization (if needed)
- [ ] **Response Times**: Average <500ms (target)
- [ ] **Asset Loading**: Static resources cached, <100ms
- [ ] **Database Queries**: No N+1 queries (profile in DEBUG if needed)
- [ ] **Gunicorn Workers**: Increased if CPU-bound, decreased if memory-constrained

---

## Ongoing Maintenance (Weekly)

- [ ] **Logs**: Reviewed for errors or warnings
- [ ] **Security**: Dependency updates via `pip list --outdated`
- [ ] **Performance**: Load average, disk space, database size
- [ ] **Backups**: Confirmed running and restorable
- [ ] **Monitoring**: Alerts set up and functioning

### Monthly
- [ ] **Security Audit**: Check for new CVEs in dependencies
- [ ] **Log Cleanup**: Rotate logs, archive old entries
- [ ] **Performance Analysis**: Identify slow endpoints
- [ ] **Dependency Updates**: Review and test updates

### Quarterly
- [ ] **Full Backup Restore**: Test disaster recovery procedure
- [ ] **Security Penetration Test**: Consider hiring penetration tester
- [ ] **Architecture Review**: Assess scaling needs
- [ ] **API Key Rotation**: Regenerate Gemini/Groq keys if needed

---

## Troubleshooting Commands

**Cannot Connect:**
```bash
curl -I https://your-domain.com
curl -v https://your-domain.com  # Verbose for SSL debugging
```

**Application Error (502):**
```bash
sudo systemctl status feedback-app
sudo tail -30 /var/log/feedback-app/app.log
sudo journalctl -u feedback-app -n 50
```

**High CPU/Memory:**
```bash
ps aux | grep gunicorn
top -p <gunicorn-pid>
sudo systemctl restart feedback-app
```

**Database Issues:**
```bash
sqlite3 /opt/feedback-app/instance/feedback.db ".tables"
sqlite3 /opt/feedback-app/instance/feedback.db ".schema"
sqlite3 /opt/feedback-app/instance/feedback.db "VACUUM;"
```

**Slow Performance:**
```bash
time curl https://your-domain.com  # Measure endpoint response time
sudo systemctl restart feedback-app
# If still slow, check database: ANALYZE; INDEX maintenance
```

**SSL Certificate Renewal Failed:**
```bash
sudo certbot renew --verbose
sudo certbot certificates  # Check expiration
```

---

## Support Contacts

- **Hosting Provider**: [Support URL/Phone]
- **Domain Registrar**: [Support URL]
- **Let's Encrypt**: https://letsencrypt.org/support/
- **Python/Flask Issues**: https://stackoverflow.com/questions/tagged/flask
- **Nginx Issues**: https://nginx.org/en/support.html

---

## Sign-Off

- [ ] **Infrastructure Owner**: Confirmed production setup
- [ ] **Application Owner**: Confirmed functionality
- [ ] **Security Lead**: Approved security configuration
- [ ] **Go-Live Approved**: By project lead

**Go-Live Date**: [Date]
**Backup Restore Test Date**: [Date]
**First 48-Hour Monitoring**: [Who]
