# Production Testing & Validation Guide

## Verification Steps

### 1. Health Endpoint
Verify database connectivity and app health:
```bash
curl http://127.0.0.1:5050/healthz
# Expected: {"status": "ok", "database": "connected"}
# HTTP 200 - Everything healthy
# HTTP 503 - Database connection failed
curl -v http://127.0.0.1:5050/healthz
# Check for headers: Content-Security-Policy, X-Frame-Options, Strict-Transport-Security
```

### 2. Metrics Endpoint (Internal Only)
Verify production metrics accessible only with internal key:
```bash
# Without key (should fail):
curl http://127.0.0.1:5050/metrics
# Response: {"error": "Unauthorized"}

# With valid session (admin must be logged in):
curl -b "session_cookie_here" http://127.0.0.1:5050/metrics

# With internal key:
curl -H "X-Internal-Key: YOUR_INTERNAL_KEY" http://127.0.0.1:5050/metrics
# Response: {"total_forms": 5, "total_responses": 42, "timestamp": "2026-04-04T13:35:51"}
```

### 3. Security Headers
Verify all required security headers are present:
```bash
curl -v http://127.0.0.1:5050/healthz 2>&1 | grep -i "< [^ ]*-"
# Look for:
# - Content-Security-Policy (CSP)
# - X-Frame-Options: DENY
# - X-Content-Type-Options: nosniff
# - X-XSS-Protection: 1; mode=block
# - Strict-Transport-Security (HSTS)
# - Cache-Control
```

### 4. Rate Limiting Tests
Test endpoint-specific rate limits:

#### Test 1: Create Form Rate Limit (10 per minute)
```bash
# Create a session first (manual login or use admin credentials)
for i in {1..15}; do
    curl -X POST http://127.0.0.1:5050/api/create_form \
         -H "Content-Type: application/json" \
         -d "{\"name\":\"Form $i\",\"subject\":\"Test\"}" &
    sleep 0.1
done | grep -c "429"  # Should see 429 responses after 10
# Expected: First 10 succeed, next 5 return 429 Too Many Requests
```

#### Test 2: Submit Feedback Rate Limit (30 per hour)
```bash
# Simulate 35 submissions in quick succession
for i in {1..35}; do
    curl -X POST "http://127.0.0.1:5050/api/submit_feedback/1" \
         -H "Content-Type: application/json" \
         -d '{"q1":"Good","q2":"Excellent"}' &
    sleep 0.05
done | grep -c "429"  # Should see 429 responses after 30
```

#### Test 3: Global Rate Limit (200 per day, 50 per hour)
```bash
# Make 25 requests just below hourly limit
for i in {1..25}; do
    curl http://127.0.0.1:5050/healthz &
done
wait
echo "All should succeed (25 < 50 per hour)"

# Make 30+ more requests to exceed hourly limit
for h in {1..60}; do
    curl http://127.0.0.1:5050/healthz > /dev/null 2>&1
    sleep 0.05
done
echo "Some should return 429"
```

### 5. Input Validation
Test endpoint input validation:

#### Test 1: Missing Required Fields
```bash
curl -X POST http://127.0.0.1:5050/api/create_form \
     -H "Content-Type: application/json" \
     -d '{}'
# Expected: 400 Bad Request with descriptive error
```

#### Test 2: Invalid Data Types
```bash
curl -X POST http://127.0.0.1:5050/api/create_form \
     -H "Content-Type: application/json" \
     -d '{"name": 123, "subject": ["array"]}'
# Expected: 400 Bad Request
```

#### Test 3: Oversized Inputs
```bash
LONG_STRING=$(python3 -c "print('x' * 100000)")
curl -X POST http://127.0.0.1:5050/api/create_form \
     -H "Content-Type: application/json" \
     -d "{\"name\":\"$LONG_STRING\",\"subject\":\"Test\"}"
# Expected: 400 Bad Request (exceeds length limit)
```

### 6. Error Handling & Logging
Verify errors are logged but not exposed to clients:

```bash
# Trigger an error (invalid form ID):
curl http://127.0.0.1:5050/api/attainment?form_id=999999

# Check that error is logged but response is safe:
tail -50 instance/logs/app.log | grep -i error
# Should show: [timestamp] | ERROR | module_name | message
# Should NOT show stack traces to client

# Verify JSON format of error responses:
curl http://127.0.0.1:5050/api/invalid_endpoint
# Expected: {"error": "Not Found"} with HTTP 404
```

### 7. Data Integrity & SQL Injection Prevention
Test SQL injection attempts:

```bash
# Attempt SQL injection on form name:
curl -X POST http://127.0.0.1:5050/api/create_form \
     -H "Content-Type: application/json" \
     -d '{"name":"'\'' OR 1=1 --","subject":"Test"}'
# Expected: 400 Bad Request or safely escaped input

# Attempt JSON injection:
curl -X POST http://127.0.0.1:5050/api/create_form \
     -H "Content-Type: application/json" \
     -d '{"name":"Test","subject":"Test","__proto__":{"isAdmin":true}}'
# Expected: Should not grant admin privileges
```

### 8. Session Security
Test session handling:

```bash
# Login as admin
curl -c cookies.txt -X POST http://127.0.0.1:5050/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=YOUR_PASSWORD"

# Verify session cookie has secure flags:
curl -b cookies.txt -v http://127.0.0.1:5050/dashboard 2>&1 | grep -i "set-cookie"
# Should have: Secure, HttpOnly, SameSite=Lax

# Test timeout - wait 1 hour or modify PERMANENT_SESSION_LIFETIME:
sleep 3600
curl -b cookies.txt http://127.0.0.1:5050/dashboard
# Expected: Redirect to login (session expired)
```

### 9. Public Form Access (No Auth Required)
Test unauthenticated form submission:

```bash
# Get a public token from a form
TOKEN="your-public-token"

# Access form without login:
curl http://127.0.0.1:5050/f/$TOKEN

# Submit feedback without login:
curl -X POST http://127.0.0.1:5050/api/submit_feedback/1 \
     -H "Content-Type: application/json" \
     -d '{"q1":"Great","q2":"Good"}'
# Expected: 200 OK (public submission allowed)
```

### 10. AI Integration
Test AI features with rate limiting:

```bash
# Generate questions from topic (requires admin session):
curl -X POST http://127.0.0.1:5050/api/generate_questions \
     -H "Content-Type: application/json" \
     -d '{"topic":"Database Design","count":5}'
# Expected: 200 OK with questions + NLP mappings
# If rate limited: 429 Too Many Requests

# Test with invalid API key:
export GEMINI_API_KEY=invalid_key
# Restart app and try:
curl http://127.0.0.1:5050/healthz
# Should still return healthy (API not required for health check)
# But AI features should fail gracefully
```

### 11. Performance & Load Testing
Simulate multiple concurrent users:

```bash
# Using Apache Bench (install: brew install httpd):
ab -n 100 -c 10 http://127.0.0.1:5050/healthz
# Expected: Most requests complete within 1s
# Typical output: Requests per second: 50-200 (depends on machine)

# Using wrk (brew install wrk):
wrk -t4 -c100 -d30s http://127.0.0.1:5050/healthz
# Shows: requests/sec, latencies (p50, p99, p99.9)
```

### 12. Logging Rotation & Size Management
Test logging doesn't consume excessive disk:

```bash
# Check current log size:
du -h instance/logs/

# Generate lots of traffic to test rotation:
for i in {1..1000}; do
    curl http://127.0.0.1:5050/healthz > /dev/null 2>&1 &
done
wait

# Verify log rotation occurred (should see backup files):
ls -la instance/logs/app.log*
# Expected: app.log + app.log.1, app.log.2, etc. (max 10 backups, 10MB each)
```

---

## Production Monitoring Checklist

- [ ] **Health Endpoint**: Responding with 200 and DB status
- [ ] **Security Headers**: All required headers present
- [ ] **Rate Limiting**: Activated and blocking excess requests with 429
- [ ] **Input Validation**: Rejecting invalid inputs with 400
- [ ] **Error Logging**: Errors logged without exposing internals
- [ ] **Session Security**: Cookies have Secure/HttpOnly/SameSite flags
- [ ] **AI Integration**: Working or gracefully degraded
- [ ] **Log Rotation**: Files rotating at 10MB without disk bloat
- [ ] **Performance**: Response times <1s for normal endpoints
- [ ] **No SQL Injection**: Input attempts safely handled
- [ ] **Public Forms**: Accessible without auth (if enabled)
- [ ] **Concurrent Users**: Handling 50+ simultaneous requests

---

## Automated Monitoring Script
Create `/opt/feedback-app/monitor.sh`:
```bash
#!/bin/bash

while true; do
    echo "[$(date)] Running health check..."
    
    # Health check
    HEALTH=$(curl -s -w "%{http_code}" http://127.0.0.1:5050/healthz)
    if [[ "$HEALTH" != *"200"* ]]; then
        echo "ALERT: Health check failed"
        systemctl restart feedback-app
    fi
    
    # Check disk space
    DISK=$(df /opt/feedback-app | awk '{print $5}' | tail -1 | sed 's/%//')
    if [ $DISK -gt 80 ]; then
        echo "ALERT: Disk usage at $DISK%"
    fi
    
    # Check process
    if ! pgrep -f gunicorn > /dev/null; then
        echo "ALERT: Gunicorn not running"
        systemctl restart feedback-app
    fi
    
    sleep 300  # Run every 5 minutes
done
```

Run with: `chmod +x monitor.sh && ./monitor.sh &`

---

## Incident Response

### App Won't Start
1. Check logs: `tail -100 instance/logs/app.log`
2. Verify .env file exists and has required keys
3. Check database: `sqlite3 instance/feedback.db ".tables"`
4. Restart: `systemctl restart feedback-app`

### High CPU/Memory
1. Check process: `ps aux | grep gunicorn`
2. Reduce workers: Edit `/etc/systemd/system/feedback-app.service`
3. Monitor: `top -p <pid>`

### Database Locked
1. Kill blocking processes: `lsof instance/feedback.db`
2. Manual VACUUM: `sqlite3 instance/feedback.db "VACUUM;"`
3. Consider PostgreSQL migration

### API Quota Exceeded
1. Check API key: `curl -H "Authorization: Bearer $GEMINI_API_KEY" https://api.example.com/quota`
2. Switch to fallback: Ensure GROQ_API_KEY is set
3. Implement caching layer

---

## Success Criteria
Application is production-ready when ALL of the following are true:
- ✅ Health endpoint returns 200 with DB connected
- ✅ Security headers present on all responses
- ✅ Rate limiting active (observed 429 responses)
- ✅ Input validation prevents injection attacks
- ✅ Errors logged but not exposed to clients
- ✅ Session cookies have security flags
- ✅ No critical vulnerabilities in dependencies (`pip audit`)
- ✅ Performance <1s for normal requests
- ✅ Log rotation active (no runaway disk usage)
- ✅ Backup strategy tested and working
- ✅ Monitoring alerts configured
