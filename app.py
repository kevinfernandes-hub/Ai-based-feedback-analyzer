import sqlite3
import os
import json
import csv
import io
import uuid
import re
import logging
import secrets
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response
from datetime import datetime
from fpdf import FPDF
from textblob import TextBlob
from better_profanity import profanity
from werkzeug.middleware.proxy_fix import ProxyFix
try:
    from groq import Groq
except Exception:
    Groq = None

try:
    from google import genai
except Exception:
    genai = None

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)
APP_ENV = os.getenv("FLASK_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

_secret_key = os.getenv("FLASK_SECRET_KEY", "").strip()
if not _secret_key:
    if IS_PRODUCTION:
        raise RuntimeError("FLASK_SECRET_KEY must be set in production.")
    _secret_key = "dev-only-change-me"

app.secret_key = _secret_key
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

if IS_PRODUCTION:
    app.config.update(
        SESSION_COOKIE_SECURE=True,
        PREFERRED_URL_SCHEME="https",
    )

# Respect reverse-proxy headers in production deployments.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

logging.basicConfig(level=logging.INFO)
DB_PATH = os.path.join(app.instance_path, "feedback.db")
STUDENT_SUBMITTER_COOKIE = "student_submitter_id"


def get_db_connection(row_factory=False):
    conn = sqlite3.connect(DB_PATH, timeout=10)
    if row_factory:
        conn.row_factory = sqlite3.Row
    return conn


def ensure_submitter_cookie(response):
    token = (request.cookies.get(STUDENT_SUBMITTER_COOKIE) or "").strip()
    if token:
        return response

    response.set_cookie(
        STUDENT_SUBMITTER_COOKIE,
        secrets.token_hex(16),
        max_age=60 * 60 * 24 * 365,
        httponly=True,
        samesite="Lax",
        secure=IS_PRODUCTION,
    )
    return response


def get_submitter_key():
    token = (request.cookies.get(STUDENT_SUBMITTER_COOKIE) or "").strip()
    if token:
        return f"cookie:{token}"

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    ip = (forwarded_for.split(",")[0].strip() if forwarded_for else request.remote_addr) or "unknown"
    user_agent = (request.headers.get("User-Agent", "unknown") or "unknown")[:200]
    return f"fallback:{ip}|{user_agent}"


@app.after_request
def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if IS_PRODUCTION:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

BRAND_COLLEGE_NAME = os.getenv("BRAND_COLLEGE_NAME", "Department of Computer Science and Engineering")
BRAND_LOGO_URL = os.getenv("BRAND_LOGO_URL", "/static/img/logo.png")
BRAND_PRIMARY_COLOR = os.getenv("BRAND_PRIMARY_COLOR", "#0f172a")
BRAND_ACCENT_COLOR = os.getenv("BRAND_ACCENT_COLOR", "#0c4a6e")


def get_branding_context():
    return {
        "college_name": BRAND_COLLEGE_NAME,
        "logo_url": BRAND_LOGO_URL,
        "primary_color": BRAND_PRIMARY_COLOR,
        "accent_color": BRAND_ACCENT_COLOR,
    }

# --- AI CONFIGURATION ---
profanity.load_censor_words()

# API KEYS
# Retrieve from environment; never commit secrets directly.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama3-8b-8192")

GEMINI_FALLBACK_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-latest",
    "gemini-1.5-flash",
    "gemini-1.5-pro-latest",
    "gemini-1.5-pro"
]

ai_provider = None
gemini_model = None
gemini_client = None
groq_client = None
gemini_model_candidates = []

def load_gemini_candidates():
    if not genai or not gemini_client:
        return []

    discovered = []
    try:
        for m in gemini_client.models.list():
            model_name = getattr(m, 'name', '').replace('models/', '')
            if model_name and model_name.startswith('gemini'):
                discovered.append(model_name)
    except Exception:
        discovered = []

    preferred = [GEMINI_MODEL] + GEMINI_FALLBACK_MODELS
    ordered = []
    for name in preferred + discovered:
        if name and name not in ordered:
            ordered.append(name)
    return ordered

try:
    if GEMINI_API_KEY and genai:
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        gemini_model_candidates = load_gemini_candidates()
        initial_model = gemini_model_candidates[0] if gemini_model_candidates else GEMINI_MODEL
        gemini_model = initial_model
        ai_provider = "gemini"
        print(f"✅ AI Online: Connected to Gemini ({initial_model})")
    elif GROQ_API_KEY and Groq:
        groq_client = Groq(api_key=GROQ_API_KEY)
        ai_provider = "groq"
        print(f"✅ AI Online: Connected to Groq ({GROQ_MODEL})")
    else:
        print("⚠️ AI Offline")
except Exception as e:
    ai_provider = None

def ai_generate_text(system_prompt, user_prompt):
    if ai_provider == "gemini" and gemini_client:
        prompt = f"{system_prompt}\n\nUser Input:\n{user_prompt}"
        attempted = set()
        candidate_models = [gemini_model] + (gemini_model_candidates or ([GEMINI_MODEL] + GEMINI_FALLBACK_MODELS))
        last_error = None
        for model_name in candidate_models:
            if not model_name or model_name in attempted:
                continue
            attempted.add(model_name)
            try:
                response = gemini_client.models.generate_content(model=model_name, contents=prompt)
                globals()['gemini_model'] = model_name
                return (getattr(response, 'text', '') or '').strip()
            except Exception as e:
                last_error = e
                continue
        if last_error:
            raise last_error

    if ai_provider == "groq" and groq_client:
        completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=GROQ_MODEL
        )
        return (completion.choices[0].message.content or '').strip()

    return ""

# SYNCED TO THE UPLOADED COURSE LIST IMAGE
COURSE_DATA_DB = {
    "Theory of Computation": [
        "CO1: Design the Finite State Machine with mathematical representation.", 
        "CO2: Define regular expression for the given Finite State Machine and vice versa.", 
        "CO3: Represent context free grammar in various forms along with its properties.", 
        "CO4: Design Push Down Automaton and Turing Machine as FSM and its various representation.", 
        "CO5: Differentiate between decidable and undecidable problems."
    ],
    "Software Engineering and Project Management": [
        "CO1: Distinguish and apply software development techniques to the different kinds of project.", 
        "CO2: Understand role of software engineer, analyze project requirements and author a formal specification for a software system.", 
        "CO3: Apply design process, steps for effective UI design depending on the requirement of the project.", 
        "CO4: Design test cases, apply testing strategies and demonstrate the ability to plan, estimate project.", 
        "CO5: Demonstrate the ability to work on software project by taking into consideration software quality factors."
    ],
    "Software Engineering and Project Management Lab": [
        "CO1: Elicit and analyze project requirements, and author a formal specification for a software system.", 
        "CO2: Demonstrate the ability to plan, estimate and schedule project.", 
        "CO3: Apply design process depending on the requirement of the project.", 
        "CO4: Design test cases and apply testing strategies in software development."
    ],
    "Operating System": [
        "CO1: Understand the basics of how operating systems work.", 
        "CO2: Explain how processes and CPU scheduling function in an operating system.", 
        "CO3: Solve common process synchronization problems.", 
        "CO4: Describe memory management concepts, including virtual memory.", 
        "CO5: Comprehend disk management and the role of file systems in an operating system."
    ],
    "Operating System Lab": [
        "CO1: Understand and implement basic services and functionalities of the operating system using system calls.", 
        "CO2: Analyze and simulate CPU Scheduling Algorithms like FCFS, Round Robin, SJF, and Priority.", 
        "CO3: Implement memory management schemes and page replacement schemes.", 
        "CO4: Implement synchronization mechanisms to address concurrent access issues.", 
        "CO5: Understand the concepts of deadlock in operating systems and implement them in multi programming system."
    ],
    "Professional Elective-I": [
        "CO1: Demonstrate the working of line drawing and circle drawing algorithm", 
        "CO2: Demonstrate 2D transformations and polygon clipping algorithms.", 
        "CO3: Demonstrate 3D transformations and curves & surfaces.", 
        "CO4: Realize different color models", 
        "CO5: Demonstrate advanced algorithms based on hidden lines and surfaces."
    ],
    "Computer Lab - II": [
        "CO1: Explore and implement the competitive programming concepts of advanced programming.", 
        "CO2: Solve Industry placement problems based on competitive programming."
    ],
    "Open Elective - II": [
        "CO1: Analyze and think in terms of object oriented paradigm during development of application.", 
        "CO2: Apply the concept object initialization and destroy using constructors and destructors.", 
        "CO3: Develop application using the concept of inheritance and evaluate the usefulness.", 
        "CO4: Apply concept polymorphism to implement static and runtime binding.", 
        "CO5: Realize the concept of abstract class, use exception handling technique in program."
    ],
    "Technical Skill Development - II": [
        "CO1: Use compiler Java and eclipse or notepad to write and execute java program.", 
        "CO2: Understand and apply the concept of object-oriented features and Java concept.", 
        "CO3: Apply the concept of multithreaded and implement exception handling.", 
        "CO4: Develop an application using JDBC."
    ],
    "Introduction to Business Management": [
        "CO1: Understand the principles and functions of management.", 
        "CO2: Apply planning and organizing tools to real-world situations.", 
        "CO3: Analyze leadership styles and motivation theories in workplace contexts.", 
        "CO4: Demonstrate basic understanding of marketing, HR, and financial functions.", 
        "CO5: Evaluate the role of entrepreneurship and business environment in economic development."
    ],
    "Career Development - V": [
        "CO1: Engage in career development planning and assessment."
    ]
}

def init_db():
    os.makedirs(app.instance_path, exist_ok=True)
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS forms (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, course_name TEXT, structure TEXT, is_active BOOLEAN DEFAULT 1, created_at TEXT, start_at TEXT, end_at TEXT, public_token TEXT
    )''')
    try:
        c.execute("ALTER TABLE forms ADD COLUMN start_at TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE forms ADD COLUMN end_at TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE forms ADD COLUMN public_token TEXT")
    except sqlite3.OperationalError:
        pass

    c.execute("SELECT id, public_token FROM forms")
    rows = c.fetchall()
    seen_tokens = set()
    for form_id, token in rows:
        if token:
            seen_tokens.add(token)
            continue
        new_token = uuid.uuid4().hex[:12]
        while new_token in seen_tokens:
            new_token = uuid.uuid4().hex[:12]
        seen_tokens.add(new_token)
        c.execute("UPDATE forms SET public_token = ? WHERE id = ?", (new_token, form_id))

    c.execute('''CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, form_id INTEGER, form_title TEXT, student_name TEXT, attendance INTEGER, 
        answers_json TEXT, full_text_for_ai TEXT, sentiment_score REAL, sentiment_label TEXT, timestamp TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS submission_locks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        form_id INTEGER NOT NULL,
        submitter_key TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(form_id, submitter_key)
    )''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def landing(): return render_template('landing.html')
@app.route('/healthz')
def healthz(): return jsonify({"status": "ok"})
@app.route('/student')
def student():
    response = make_response(render_template('student.html', brand=get_branding_context()))
    return ensure_submitter_cookie(response)
@app.route('/f/<token>')
def published_form(token):
    response = make_response(render_template('student.html', published_token=token, brand=get_branding_context()))
    return ensure_submitter_cookie(response)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == ADMIN_USERNAME and request.form.get('password') == ADMIN_PASSWORD:
            session['user'] = 'admin'; return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html') if 'user' in session else redirect(url_for('login'))
@app.route('/logout')
def logout(): session.pop('user', None); return redirect(url_for('landing'))

# --- CORE API ---
@app.route('/api/create_form', methods=['POST'])
def create_form():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    questions = data.get('questions') or []
    for q in questions:
        if 'required' not in q:
            q['required'] = True

    form_token = uuid.uuid4().hex[:12]
    conn = get_db_connection(); c = conn.cursor()
    c.execute("INSERT INTO forms (title, course_name, structure, created_at, start_at, end_at, public_token) VALUES (?, ?, ?, ?, ?, ?, ?)", 
              (
                  data.get('title'),
                  data.get('course_name'),
                  json.dumps(questions),
                  datetime.now().strftime("%Y-%m-%d"),
                  data.get('start_at') or None,
                  data.get('end_at') or None,
                  form_token
              ))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/edit_form', methods=['POST'])
def edit_form():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    questions = data.get('questions') or []
    for q in questions:
        if 'required' not in q:
            q['required'] = True

    conn = get_db_connection(); c = conn.cursor()
    c.execute("UPDATE forms SET title=?, course_name=?, structure=?, start_at=?, end_at=? WHERE id=?", 
              (
                  data.get('title'),
                  data.get('course_name'),
                  json.dumps(questions),
                  data.get('start_at') or None,
                  data.get('end_at') or None,
                  data.get('form_id')
              ))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

def parse_datetime(value):
    if not value:
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None

def is_form_open(row):
    now = datetime.now()
    start_at = parse_datetime(row.get('start_at'))
    end_at = parse_datetime(row.get('end_at'))
    if start_at and now < start_at:
        return False
    if end_at and now > end_at:
        return False
    return bool(row.get('is_active'))

@app.route('/api/forms', methods=['GET'])
def get_forms():
    try:
        conn = get_db_connection(row_factory=True); c = conn.cursor()
        c.execute("SELECT * FROM forms ORDER BY id DESC")
        rows = c.fetchall(); conn.close()
        results = []
        for row in rows:
            r = dict(row)
            try: r['structure'] = json.loads(r['structure']) if r['structure'] else []
            except: r['structure'] = []
            r['is_open'] = is_form_open(r)
            r['public_url'] = url_for('published_form', token=r.get('public_token') or '', _external=True)

            if request.args.get('active_only') and not r['is_open']:
                continue
            results.append(r)
        return jsonify(results)
    except: return jsonify([]), 500

@app.route('/api/forms/published/<token>', methods=['GET'])
def get_published_form(token):
    conn = get_db_connection(row_factory=True); c = conn.cursor()
    c.execute("SELECT * FROM forms WHERE public_token = ?", (token,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Form not found."}), 404

    form_data = dict(row)
    if not is_form_open(form_data):
        return jsonify({"error": "This form is currently closed."}), 400

    try:
        form_data['structure'] = json.loads(form_data.get('structure') or "[]")
    except Exception:
        form_data['structure'] = []
    form_data['is_open'] = True
    form_data['public_url'] = url_for('published_form', token=form_data.get('public_token') or '', _external=True)
    return jsonify(form_data)

@app.route('/api/toggle_form', methods=['POST'])
def toggle_form():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    conn = get_db_connection(); c = conn.cursor()
    c.execute("UPDATE forms SET is_active = ? WHERE id = ?", (request.json.get('status'), request.json.get('id')))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.json
        answers = data.get('answers', [])
        submitter_key = get_submitter_key()

        conn = get_db_connection(row_factory=True); c = conn.cursor()
        c.execute("SELECT * FROM forms WHERE id = ?", (data.get('form_id'),))
        form_row = c.fetchone()
        if not form_row:
            conn.close()
            return jsonify({"status": "error", "message": "Form not found."}), 404

        form_data = dict(form_row)
        if not is_form_open(form_data):
            conn.close()
            return jsonify({"status": "error", "message": "Form is currently closed."}), 400

        form_structure = json.loads(form_data.get('structure') or "[]")
        required_map = {str(q.get('text', '')).strip(): bool(q.get('required', True)) for q in form_structure}

        for ans in answers:
            q_text = str(ans.get('question', '')).strip()
            required = required_map.get(q_text, True)
            val = ans.get('answer', '')
            if required and (val is None or str(val).strip() == '' or str(val).strip() == '0'):
                conn.close()
                return jsonify({"status": "error", "message": f"Required question missing: {q_text}"}), 400
        
        text_parts = []; rating_sum = 0; rating_count = 0
        for ans in answers:
            val = ans.get('answer', '')
            if ans.get('type') in ['rating_3', 'rating_5'] and val:
                try: rating_sum += int(val); rating_count += 1
                except: pass
            elif ans.get('type') == 'text' and str(val).strip() and str(val).strip().lower() != 'none':
                text_parts.append(str(val))

        full_text = ". ".join(text_parts)
        if profanity.contains_profanity(full_text):
            return jsonify({"status": "error", "message": "Toxic feedback detected. Please keep your feedback professional."}), 400

        text_score = TextBlob(full_text).sentiment.polarity if full_text else 0.0
        final_score = 0; label = "Neutral"
        if rating_count > 0:
            avg = rating_sum / rating_count
            if avg > (3 if any(a.get('type') == 'rating_5' for a in answers) else 2): label = "Positive"
            elif avg < (2.5 if any(a.get('type') == 'rating_5' for a in answers) else 1.5): label = "Negative"
        else:
            if text_score > 0.15: label = "Positive"
            elif text_score < -0.15: label = "Negative"

        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO submission_locks (form_id, submitter_key, created_at) VALUES (?, ?, ?)",
                (data.get('form_id'), submitter_key, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({"status": "error", "message": "Duplicate submission blocked: this form was already submitted from this device/browser."}), 409

        c.execute('''INSERT INTO responses (form_id, form_title, student_name, attendance, answers_json, full_text_for_ai, sentiment_score, sentiment_label, timestamp) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (data.get('form_id'), data.get('form_title'), data.get('student_name', 'Anonymous'), 100, json.dumps(answers), full_text, text_score, label, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit(); conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500

# --- AI ENDPOINTS ---
def normalize_question(text):
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = cleaned.lstrip("-•*0123456789. ")
    if not cleaned:
        return ""
    if not cleaned.endswith("?"):
        cleaned = f"{cleaned}?"
    return cleaned

def fallback_suggested_questions(course_name, event_title):
    context_label = course_name or event_title or "this course"
    suggestions = [
        f"How clearly were the concepts in {context_label} explained?",
        f"How effectively did {context_label} improve your understanding of key topics?",
        "How would you rate the pace and structure of teaching sessions?",
        "How useful were assignments and assessments for your learning?",
        "How satisfied are you with classroom and lab support for this subject?",
        "What is one thing that worked well and should be continued?",
        "What is one improvement that would most enhance your learning experience?"
    ]

    for co_text in COURSE_DATA_DB.get(course_name, [])[:2]:
        parts = co_text.split(":", 1)
        co_code = parts[0].strip() if parts else "CO"
        co_desc = parts[1].strip() if len(parts) > 1 else co_text
        suggestions.append(f"How well did this course help you achieve {co_code} ({co_desc})?")

    deduped = []
    seen = set()
    for item in suggestions:
        q = normalize_question(item)
        if q and q.lower() not in seen:
            deduped.append(q)
            seen.add(q.lower())
    return deduped[:8]

@app.route('/api/ai/suggest_questions', methods=['POST'])
def ai_suggest_questions():
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json or {}
    course_name = str(data.get('course_name', '')).strip()
    event_title = str(data.get('event_title', '')).strip()
    fallback = fallback_suggested_questions(course_name, event_title)

    if not ai_provider:
        return jsonify({"questions": fallback, "source": "fallback"})

    prompt = (
        "Generate 6 concise student feedback questions for a college feedback form. "
        "Return only plain lines, one question per line, no numbering, no markdown, max 18 words each. "
        "Include at least 2 outcome-focused questions.\n"
        f"Course: {course_name or 'N/A'}\n"
        f"Event: {event_title or 'N/A'}"
    )

    try:
        raw = ai_generate_text("You create clear, short feedback form questions.", prompt)
        candidates = [normalize_question(line) for line in raw.splitlines()]
        candidates = [q for q in candidates if q]

        deduped = []
        seen = set()
        for q in candidates:
            k = q.lower()
            if k not in seen:
                deduped.append(q)
                seen.add(k)

        return jsonify({"questions": (deduped[:8] or fallback), "source": "ai"})
    except Exception:
        return jsonify({"questions": fallback, "source": "fallback"})

@app.route('/api/ai/report', methods=['POST'])
def ai_report():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    if not ai_provider: return jsonify({"report": "<p>AI Offline. Set GEMINI_API_KEY or GROQ_API_KEY.</p>"})
    conn = get_db_connection(); c = conn.cursor()
    c.execute("SELECT full_text_for_ai FROM responses WHERE form_id = ?", (request.json.get('form_id'),))
    rows = c.fetchall(); conn.close()
    
    valid_texts = [r[0] for r in rows if r[0] and r[0].strip() and r[0].strip().lower() != 'none']
    text_data = "\n- ".join(valid_texts)
    
    if not text_data.strip(): return jsonify({"report": "<p>No written feedback available.</p>"})
    try:
        report = ai_generate_text(
            "Analyze the feedback. Generate an Executive Summary containing 'Top 3 Strengths' and 'Top 3 Actionable Improvements' using HTML tags (<h3>, <ul>, <li>). No markdown blocks.",
            text_data[:6000]
        )
        return jsonify({"report": report.replace('```html', '').replace('```', '')})
    except Exception as e: return jsonify({"error": str(e)}), 500

# --- ENGINE & EXPORTS ---
def sort_key(k):
    if k.startswith('CO'): return (0, int(k[2:]))
    elif k.startswith('PO'): return (1, int(k[2:]))
    elif k.startswith('PEO'): return (2, int(k[3:]))
    elif k.startswith('PSO'): return (3, int(k[3:]))
    return (4, 0)

def get_attainment_data(form_id):
    conn = get_db_connection(row_factory=True); c = conn.cursor()
    c.execute("SELECT * FROM responses WHERE form_id = ?", (form_id,))
    responses = c.fetchall()
    c.execute("SELECT * FROM forms WHERE id = ?", (form_id,))
    form_data = c.fetchone()
    conn.close()

    course_name = form_data['course_name'] if form_data else "Unknown"
    form_title = form_data['title'] if form_data else "Unknown"
    structure = json.loads(form_data['structure']) if form_data and form_data['structure'] else []

    if not responses: 
        return {"stats": [], "question_stats": [], "sentiment": {}, "charts": {}, "total": 0, "course_name": course_name, "title": form_title, "responses": []}

    stats = {}
    for i in range(1, 7): stats[f"CO{i}"] = {"sum": 0, "max_sum": 0, "count": 0}
    for i in range(1, 13): stats[f"PO{i}"] = {"sum": 0, "max_sum": 0, "count": 0}
    for i in range(1, 4): stats[f"PEO{i}"] = {"sum": 0, "max_sum": 0, "count": 0}
    for i in range(1, 4): stats[f"PSO{i}"] = {"sum": 0, "max_sum": 0, "count": 0}
    
    question_stats = []
    for q in structure:
        question_stats.append({"text": q.get('text', ''), "type": q.get('type', 'text'), "mappings": q.get('mappings', []), "sum": 0, "max_sum": 0, "count": 0})

    pos = 0; neu = 0; neg = 0
    trend_data = []

    for r in responses:
        lbl = r['sentiment_label']
        if lbl == 'Positive': pos += 1
        elif lbl == 'Negative': neg += 1
        else: neu += 1

        answers = json.loads(r['answers_json'])
        r_sum = 0; r_cnt = 0
        for ans in answers:
            score = int(ans['answer']) if ans['answer'] and ans['type'] in ['rating_3', 'rating_5'] else 0
            max_q_score = 3 if ans['type'] == 'rating_3' else (5 if ans['type'] == 'rating_5' else 0)
            
            if max_q_score > 0:
                r_sum += (score / max_q_score) * 100
                r_cnt += 1

            if max_q_score > 0 and 'mappings' in ans:
                for key in ans['mappings']:
                    if key in stats:
                        stats[key]["sum"] += score; stats[key]["max_sum"] += max_q_score; stats[key]["count"] += 1
            
            for qs in question_stats:
                if qs['text'] == ans['question']:
                    if qs['type'] in ['rating_3', 'rating_5'] and ans['answer']:
                        qs['sum'] += score; qs['max_sum'] += max_q_score; qs['count'] += 1
                    elif qs['type'] == 'text' and str(ans['answer']).strip() and str(ans['answer']).strip().lower() != 'none':
                        qs['count'] += 1
        
        if r_cnt > 0:
            trend_data.append(round(r_sum / r_cnt, 1))

    report = []
    level_counts = {'High': 0, 'Moderate': 0, 'Low': 0}
    
    all_keys = sorted(stats.keys(), key=sort_key)
    for key in all_keys:
        data = stats[key]
        if data['count'] > 0 and data['max_sum'] > 0:
            percentage = (data['sum'] / data['max_sum']) * 100
            avg_score = round(data['sum'] / data['count'], 2)
            
            level = "L1 (Low)"; color = "text-red-600 bg-red-50"
            if percentage >= 70: 
                level = "L3 (High)"; color = "text-green-600 bg-green-50"; level_counts['High'] += 1
            elif percentage >= 60: 
                level = "L2 (Moderate)"; color = "text-yellow-600 bg-yellow-50"; level_counts['Moderate'] += 1
            else:
                level_counts['Low'] += 1

            report.append({"code": key, "avg": avg_score, "pct": round(percentage, 1), "level": level, "color": color, "student_count": data['count']})

    q_labels = []
    q_data = []
    for i, qs in enumerate(question_stats):
        qs['pct'] = round((qs['sum'] / qs['max_sum']) * 100, 1) if qs['max_sum'] > 0 else 0
        qs['avg'] = round(qs['sum'] / qs['count'], 2) if qs['count'] > 0 and qs['max_sum'] > 0 else 0
        if qs['type'] in ['rating_3', 'rating_5']:
            q_labels.append(f"Q{i+1}")
            q_data.append(qs['pct'])

    charts_data = {
        "pie": [level_counts['High'], level_counts['Moderate'], level_counts['Low']],
        "bar": {"labels": q_labels, "data": q_data},
        "line": trend_data
    }

    risk_score = 0
    weak_outcomes = [row for row in report if row.get('pct', 0) < 60]
    weak_pct = (len(weak_outcomes) / len(report) * 100) if report else 100
    risk_score += weak_pct * 0.7

    if trend_data:
        recent_window = trend_data[-3:] if len(trend_data) >= 3 else trend_data
        recent_avg = sum(recent_window) / len(recent_window)
        if recent_avg < 65:
            risk_score += 20
        elif recent_avg < 75:
            risk_score += 10

    if neg > pos:
        risk_score += 10

    risk_score = max(0, min(100, round(risk_score, 1)))
    risk_level = "Low"
    if risk_score >= 70:
        risk_level = "High"
    elif risk_score >= 40:
        risk_level = "Moderate"

    return {
        "stats": report, "question_stats": question_stats, "sentiment": {"pos": pos, "neu": neu, "neg": neg},
        "charts": charts_data,
        "total": len(responses),
        "course_name": course_name,
        "title": form_title,
        "responses": [dict(r) for r in responses],
        "risk": {
            "score": risk_score,
            "level": risk_level,
            "weak_outcomes": [w.get('code') for w in weak_outcomes[:5]]
        }
    }

@app.route('/api/attainment', methods=['GET'])
def get_attainment_api():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_attainment_data(request.args.get('form_id')))

@app.route('/api/export_pdf', methods=['GET'])
def export_pdf():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = get_attainment_data(request.args.get('form_id'))
    pdf = FPDF()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 15)
    pdf.cell(0, 8, txt="DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING", ln=True, align='C')
    pdf.set_font("Arial", 'I', 9)
    pdf.multi_cell(0, 5, txt="VISION: To develop globally competent computing community with the ability to make constructive contribution to society.", align='C')
    pdf.multi_cell(0, 5, txt="MISSION: To develop technocrats with capabilities to address the challenges in computer engineering by providing strong academics and wide industry exposure.", align='C')
    pdf.line(10, pdf.get_y()+2, 200, pdf.get_y()+2)
    pdf.ln(6)

    pdf.set_font("Arial", 'B', 11); pdf.cell(0, 6, txt="OBE ATTAINMENT REPORT", ln=True, align='C'); pdf.ln(5)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(35, 7, "Event Title:", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(0, 7, data['title'], 0, 1)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(35, 7, "Course Name:", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(0, 7, data['course_name'], 0, 1)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(35, 7, "Date:", 0, 0); pdf.set_font("Arial", '', 10); pdf.cell(0, 7, datetime.now().strftime('%Y-%m-%d %H:%M'), 0, 1)
    pdf.ln(3); pdf.set_fill_color(230, 240, 255); pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, f" Total Students Evaluated: {data['total']}", 1, 1, 'L', True); pdf.ln(8)
    
    pdf.set_font("Arial", 'B', 12); pdf.cell(0, 8, "PART 1: OBE Attainment (Multi-Mapped)", ln=True)
    pdf.set_fill_color(50, 50, 50); pdf.set_text_color(255, 255, 255); pdf.set_font("Arial", 'B', 9)
    pdf.cell(30, 8, 'Outcome', 1, 0, 'C', True); pdf.cell(35, 8, 'Eval Points', 1, 0, 'C', True); pdf.cell(35, 8, 'Avg Score', 1, 0, 'C', True); pdf.cell(40, 8, 'Attainment %', 1, 0, 'C', True); pdf.cell(50, 8, 'Level', 1, 1, 'C', True)
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 9)
    for row in data['stats']:
        pdf.cell(30, 8, row['code'], 1, 0, 'C'); pdf.cell(35, 8, str(row['student_count']), 1, 0, 'C'); pdf.cell(35, 8, str(row['avg']), 1, 0, 'C'); pdf.cell(40, 8, f"{row['pct']}%", 1, 0, 'C'); pdf.cell(50, 8, row['level'].upper(), 1, 1, 'C')
    
    pdf.ln(10); pdf.set_font("Arial", 'B', 12); pdf.cell(0, 8, "PART 2: Question Breakdown", ln=True)
    for i, qs in enumerate(data['question_stats']):
        pdf.set_fill_color(245, 245, 245); pdf.set_font("Arial", 'B', 9)
        pdf.multi_cell(0, 7, f"Q{i+1}: {qs['text'].encode('latin-1', 'replace').decode('latin-1')} [Mappings: {', '.join(qs['mappings'])}]", fill=True)
        pdf.set_font("Arial", '', 9)
        if qs['type'] in ['rating_3', 'rating_5']:
            pdf.cell(0, 6, f"Average Rating: {qs['avg']}  |  Attainment: {qs['pct']}% ({qs['count']} responses)", ln=True)
        else:
            pdf.cell(0, 6, f"Comments Received: {qs['count']}", ln=True)

    charts = data.get('charts', {})
    if sum(charts.get('pie', [0,0,0])) > 0:
        pdf.add_page(); pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, "PART 3: Visual Analytics", ln=True, align='C'); pdf.line(10, 20, 200, 20); pdf.ln(5)
        uid = str(uuid.uuid4()); pie_path = f"temp_pie_{uid}.png"; bar_path = f"temp_bar_{uid}.png"; line_path = f"temp_line_{uid}.png"
        try:
            plt.figure(figsize=(5, 4))
            plt.pie(charts['pie'], labels=['High (L3)', 'Moderate (L2)', 'Low (L1)'], colors=['#22c55e', '#eab308', '#ef4444'], autopct='%1.1f%%')
            plt.title('Outcome Attainment Level Distribution'); plt.savefig(pie_path, bbox_inches='tight'); plt.close()
            
            plt.figure(figsize=(5, 4))
            plt.bar(charts['bar']['labels'], charts['bar']['data'], color='#3b82f6')
            plt.title('Question-Wise Attainment (%)'); plt.ylim(0, 100); plt.savefig(bar_path, bbox_inches='tight'); plt.close()

            plt.figure(figsize=(8, 3))
            plt.plot(range(1, len(charts['line'])+1), charts['line'], color='#8b5cf6', marker='o')
            plt.title('Average Rating Trend (Chronological)'); plt.ylim(0, 100); plt.savefig(line_path, bbox_inches='tight'); plt.close()

            pdf.image(pie_path, x=10, y=pdf.get_y(), w=90); pdf.image(bar_path, x=110, y=pdf.get_y(), w=90)
            pdf.ln(75)
            pdf.image(line_path, x=20, y=pdf.get_y(), w=160)
        finally:
            if os.path.exists(pie_path): os.remove(pie_path)
            if os.path.exists(bar_path): os.remove(bar_path)
            if os.path.exists(line_path): os.remove(line_path)

    if data['course_name'] in COURSE_DATA_DB and len(COURSE_DATA_DB[data['course_name']]) > 0:
        pdf.ln(15) 
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, "Reference: Course Outcomes (CO) Syllabus Mapping", ln=True)
        pdf.set_font("Arial", '', 8)
        for co_text in COURSE_DATA_DB[data['course_name']]:
            pdf.multi_cell(0, 5, co_text.encode('latin-1', 'replace').decode('latin-1'))

    res = make_response(pdf.output(dest='S').encode('latin-1'))
    res.headers['Content-Type'] = 'application/pdf'
    res.headers['Content-Disposition'] = f"attachment; filename={data['course_name'].replace(' ', '_')}_Report.pdf"
    return res

@app.route('/api/export_csv', methods=['GET'])
def export_csv():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = get_attainment_data(request.args.get('form_id'))
    si = io.StringIO(); cw = csv.writer(si)
    cw.writerow(['COURSE OBE & FEEDBACK REPORT', data['course_name']])
    cw.writerow(['Event Title', data['title']])
    cw.writerow(['Total Students', data['total']])
    cw.writerow([])
    cw.writerow(['PART 1: OUTCOME ATTAINMENT'])
    cw.writerow(['Code', 'Eval Points', 'Average Score', 'Attainment %', 'NBA Level'])
    for row in data['stats']: cw.writerow([row['code'], row['student_count'], row['avg'], f"{row['pct']}%", row['level']])
    cw.writerow([])
    cw.writerow(['PART 2: RAW RESPONSES'])
    cw.writerow(['Student', 'Sentiment', 'Answers'])
    for r in data['responses']:
        ans = json.loads(r['answers_json'])
        qa = " | ".join([f"[{','.join(a.get('mappings', []))}] {a['answer']}" for a in ans])
        cw.writerow([r['student_name'], r['sentiment_label'], qa])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={data['course_name']}_Data.csv"
    output.headers["Content-type"] = "text/csv"
    return output

if __name__ == '__main__':
    app.logger.info("Starting app in %s mode", APP_ENV)
    run_port = int(os.getenv("PORT", "5050"))
    run_host = os.getenv("HOST", "127.0.0.1")
    if IS_PRODUCTION and run_host == "127.0.0.1":
        run_host = "0.0.0.0"
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1" and not IS_PRODUCTION
    app.run(debug=debug_mode, host=run_host, port=run_port)