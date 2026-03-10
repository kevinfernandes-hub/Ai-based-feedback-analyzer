import sqlite3
import os
import json
import csv
import io
import uuid
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, make_response
from datetime import datetime
from fpdf import FPDF
from textblob import TextBlob
import ollama


import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)
app.secret_key = "obe_nba_secret"

# DICTIONARY FOR PDF GENERATION
COURSE_DATA_DB = {
    "Theory of Computation": ["CO1: Design the Finite State Machine with mathematical representation.", "CO2: Define regular expression for the given Finite State Machine and vice versa.", "CO3: Represent context free grammar in various forms along with its properties.", "CO4: Design Push Down Automaton and Turing Machine as FSM and its various representation.", "CO5: Differentiate between decidable and undecidable problems."],
    "Software Engineering and Project Management": ["CO1: Distinguish and apply software development techniques to the different kinds of project.", "CO2: Understand role of software engineer, analyze project requirements and author a formal specification for a software system.", "CO3: Apply design process, steps for effective UI design depending on the requirement of the project.", "CO4: Design test cases, apply testing strategies and demonstrate the ability to plan, estimate project.", "CO5: Demonstrate the ability to work on software project by taking into consideration software quality factors."],
    "Software Engineering & Project Management Lab": ["CO1: Elicit and analyze project requirements, and author a formal specification for a software system.", "CO2: Demonstrate the ability to plan, estimate and schedule project.", "CO3: Apply design process depending on the requirement of the project.", "CO4: Design test cases and apply testing strategies in software development."],
    "Operating System": ["CO1: Understand the basics of how operating systems work.", "CO2: Explain how processes and CPU scheduling function in an operating system.", "CO3: Solve common process synchronization problems.", "CO4: Describe memory management concepts, including virtual memory.", "CO5: Comprehend disk management and the role of file systems in an operating system."],
    "Operating System Lab": ["CO1: Understand and implement basic services and functionalities of the operating system using system calls.", "CO2: Analyze and simulate CPU Scheduling Algorithms like FCFS, Round Robin, SJF, and Priority.", "CO3: Implement memory management schemes and page replacement schemes.", "CO4: Implement synchronization mechanisms to address concurrent access issues.", "CO5: Understand the concepts of deadlock in operating systems and implement them in multi programming system."],
    "Computer Graphics (PE-I)": ["CO1: Demonstrate the working of line drawing and circle drawing algorithm", "CO2: Demonstrate 2D transformations and polygon clipping algorithms.", "CO3: Demonstrate 3D transformations and curves & surfaces.", "CO4: Realize different color models", "CO5: Demonstrate advanced algorithms based on hidden lines and surfaces."],
    "PE-I Artificial Intelligence": ["CO1: Understand the AI and AI Problem.", "CO2: Analyze the data using predicate logic knowledge", "CO3: Solve the problem using Bayes and DST Probabilistic Reasoning", "CO4: Apply Natural Language Processing kit on given sentence", "CO5: Recall and understand the concept of Expert System."],
    "Computer Lab - II": ["CO1: Explore and implement the competitive programming concepts of advanced programming.", "CO2: Solve Industry placement problems based on competitive programming."],
    "OE-II Object Oriented Programming": ["CO1: Analyze and think in terms of object oriented paradigm during development of application.", "CO2: Apply the concept object initialization and destroy using constructors and destructors.", "CO3: Develop application using the concept of inheritance and evaluate the usefulness.", "CO4: Apply concept polymorphism to implement static and runtime binding.", "CO5: Realize the concept of abstract class, use exception handling technique in program."],
    "Technical Skill Development-II": ["CO1: Use compiler Java and eclipse or notepad to write and execute java program.", "CO2: Understand and apply the concept of object-oriented features and Java concept.", "CO3: Apply the concept of multithreaded and implement exception handling.", "CO4: Develop an application using JDBC."],
    "MDM-III Introduction to Business Management": ["CO1: Understand the principles and functions of management.", "CO2: Apply planning and organizing tools to real-world situations.", "CO3: Analyze leadership styles and motivation theories in workplace contexts.", "CO4: Demonstrate basic understanding of marketing, HR, and financial functions.", "CO5: Evaluate the role of entrepreneurship and business environment in economic development."]
}

def init_db():
    if not os.path.exists('instance'): os.makedirs('instance')
    conn = sqlite3.connect('instance/feedback.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS forms (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, course_name TEXT, structure TEXT, is_active BOOLEAN DEFAULT 1, created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, form_id INTEGER, form_title TEXT, student_name TEXT, attendance INTEGER, 
        answers_json TEXT, full_text_for_ai TEXT, sentiment_score REAL, sentiment_label TEXT, timestamp TEXT
    )''')
    
    # Robustly check for missing columns in existing table (Migration)
    c.execute("PRAGMA table_info(responses)")
    columns = [col[1] for col in c.fetchall()]
    if 'full_text_for_ai' not in columns:
        c.execute("ALTER TABLE responses ADD COLUMN full_text_for_ai TEXT")
    if 'sentiment_score' not in columns:
        c.execute("ALTER TABLE responses ADD COLUMN sentiment_score REAL")
    if 'sentiment_label' not in columns:
        c.execute("ALTER TABLE responses ADD COLUMN sentiment_label TEXT")
        
    conn.commit()
    conn.close()


init_db()

@app.route('/')
def landing(): return render_template('landing.html')
@app.route('/student')
def student(): return render_template('student.html')
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('username') == 'admin' and request.form.get('password') == 'admin123':
            session['user'] = 'admin'; return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid Credentials")
    return render_template('login.html')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html') if 'user' in session else redirect(url_for('login'))
@app.route('/logout')
def logout(): session.pop('user', None); return redirect(url_for('landing'))

# --- API ---
@app.route('/api/create_form', methods=['POST'])
def create_form():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    conn = sqlite3.connect('instance/feedback.db'); c = conn.cursor()
    c.execute("INSERT INTO forms (title, course_name, structure, created_at) VALUES (?, ?, ?, ?)", 
              (data.get('title'), data.get('course_name'), json.dumps(data.get('questions')), datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/forms', methods=['GET'])
def get_forms():
    try:
        conn = sqlite3.connect('instance/feedback.db'); conn.row_factory = sqlite3.Row; c = conn.cursor()
        active_only = request.args.get('active_only')
        if active_only: 
            c.execute("SELECT * FROM forms WHERE is_active = 1 ORDER BY id DESC")
        else: 
            c.execute("SELECT * FROM forms ORDER BY id DESC")
        rows = c.fetchall(); conn.close()
        results = []
        for row in rows:
            r = dict(row)
            try:
                r['structure'] = json.loads(r['structure']) if r['structure'] else []
                results.append(r)
            except Exception as e:
                print(f"ERROR parsing form structure for ID {r.get('id')}: {e}")
        return jsonify(results)
    except Exception as e:
        print(f"ERROR in get_forms: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/toggle_form', methods=['POST'])
def toggle_form():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    conn = sqlite3.connect('instance/feedback.db'); c = conn.cursor()
    c.execute("UPDATE forms SET is_active = ? WHERE id = ?", (request.json.get('status'), request.json.get('id')))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/update_form', methods=['POST'])
def update_form():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    conn = sqlite3.connect('instance/feedback.db'); c = conn.cursor()
    c.execute("UPDATE forms SET title = ?, course_name = ?, structure = ? WHERE id = ?",
              (data.get('title'), data.get('course_name'), json.dumps(data.get('questions', [])), data.get('id')))
    conn.commit(); conn.close()
    return jsonify({"status": "success"})

@app.route('/api/submit_feedback', methods=['POST'])
def submit_feedback():
    try:
        data = request.json
        answers = data.get('answers', [])
        
        rating_sum = 0; rating_count = 0; text_parts = []
        for ans in answers:
            val = ans.get('answer', '')
            if ans.get('type') in ['rating_3', 'rating_5'] and val:
                try: rating_sum += int(val); rating_count += 1
                except: pass
            elif ans.get('type') == 'text' and str(val).strip():
                text_parts.append(str(val))

        full_text = ". ".join(text_parts)
        text_score = TextBlob(full_text).sentiment.polarity if full_text else 0.0

        final_score = 0; label = "Neutral"
        if rating_count > 0:
            avg = rating_sum / rating_count
            if avg > (3 if any(a.get('type') == 'rating_5' for a in answers) else 2): label = "Positive"
            elif avg < (2.5 if any(a.get('type') == 'rating_5' for a in answers) else 1.5): label = "Negative"
            else: label = "Neutral"
        else:
            if text_score > 0.15: label = "Positive"
            elif text_score < -0.15: label = "Negative"

        conn = sqlite3.connect('instance/feedback.db'); c = conn.cursor()
        c.execute('''INSERT INTO responses (form_id, form_title, student_name, attendance, answers_json, full_text_for_ai, sentiment_score, sentiment_label, timestamp) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                  (data.get('form_id'), data.get('form_title'), data.get('student_name', 'Anonymous'), 100, json.dumps(answers), full_text, text_score, label, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit(); conn.close()
        return jsonify({"status": "success"})
    except Exception as e: 
        print(f"ERROR in submit_feedback: {str(e)}")
        return jsonify({"error": str(e)}), 500


# --- CORE ATTAINMENT ENGINE ---
def sort_key(k):
    if k.startswith('CO'): return (0, int(k[2:]))
    elif k.startswith('PO'): return (1, int(k[2:]))
    elif k.startswith('PEO'): return (2, int(k[3:]))
    elif k.startswith('PSO'): return (3, int(k[3:]))
    return (4, 0)

def get_attainment_data(form_id):
    try:
        conn = sqlite3.connect('instance/feedback.db'); conn.row_factory = sqlite3.Row; c = conn.cursor()
        c.execute("SELECT * FROM responses WHERE form_id = ?", (form_id,))
        responses = c.fetchall()
        c.execute("SELECT * FROM forms WHERE id = ?", (form_id,))
        form_data = c.fetchone()
        conn.close()
    except Exception as e:
        print(f"ERROR fetching data for form_id {form_id}: {e}")
        return {"error": str(e)}


    course_name = form_data['course_name'] if form_data else "Unknown"
    form_title = form_data['title'] if form_data else "Unknown"
    
    structure = []
    if form_data and form_data['structure']:
        try:
            structure = json.loads(form_data['structure'])
            if not isinstance(structure, list): structure = []
        except:
            structure = []

    if not responses: 
        return {"stats": [], "question_stats": [], "sentiment": {}, "total": 0, "course_name": course_name, "title": form_title, "responses": []}


    stats = {}
    for i in range(1, 7): stats[f"CO{i}"] = {"sum": 0, "max_sum": 0, "count": 0}
    for i in range(1, 13): stats[f"PO{i}"] = {"sum": 0, "max_sum": 0, "count": 0}
    for i in range(1, 4): stats[f"PEO{i}"] = {"sum": 0, "max_sum": 0, "count": 0}
    for i in range(1, 4): stats[f"PSO{i}"] = {"sum": 0, "max_sum": 0, "count": 0}
    
    question_stats = []
    for q in structure:
        question_stats.append({"text": q.get('text', ''), "type": q.get('type', 'text'), "mappings": q.get('mappings', []), "sum": 0, "max_sum": 0, "count": 0})

    pos = 0; neu = 0; neg = 0

    for r in responses:
        lbl = r['sentiment_label']
        if lbl == 'Positive': pos += 1
        elif lbl == 'Negative': neg += 1
        else: neu += 1

        answers = json.loads(r['answers_json'])
        for ans in answers:
            score = int(ans['answer']) if ans['answer'] and ans['type'] in ['rating_3', 'rating_5'] else 0
            max_q_score = 3 if ans['type'] == 'rating_3' else (5 if ans['type'] == 'rating_5' else 0)

            if max_q_score > 0 and 'mappings' in ans:
                for key in ans['mappings']:
                    if key in stats:
                        stats[key]["sum"] += score
                        stats[key]["max_sum"] += max_q_score
                        stats[key]["count"] += 1
            
            for qs in question_stats:
                ans_question = ans.get('question')
                if ans_question and qs['text'] == ans_question:
                    if qs['type'] in ['rating_3', 'rating_5'] and ans.get('answer'):
                        qs['sum'] += score
                        qs['max_sum'] += max_q_score
                        qs['count'] += 1
                    elif qs['type'] == 'text' and str(ans.get('answer', '')).strip():
                        qs['count'] += 1

    report = []
    all_keys = sorted(stats.keys(), key=sort_key)
    for key in all_keys:
        data = stats[key]
        if data['count'] > 0 and data['max_sum'] > 0:
            percentage = (data['sum'] / data['max_sum']) * 100
            avg_score = round(data['sum'] / data['count'], 2)
            level = "L1 (Low)"; color = "text-red-600 bg-red-50"
            if percentage >= 70: level = "L3 (High)"; color = "text-green-600 bg-green-50"
            elif percentage >= 60: level = "L2 (Moderate)"; color = "text-yellow-600 bg-yellow-50"
            report.append({"code": key, "avg": avg_score, "pct": round(percentage, 1), "level": level, "color": color, "student_count": data['count']})

    for qs in question_stats:
        qs['pct'] = round((qs['sum'] / qs['max_sum']) * 100, 1) if qs['max_sum'] > 0 else 0
        qs['avg'] = round(qs['sum'] / qs['count'], 2) if qs['count'] > 0 and qs['max_sum'] > 0 else 0

    total_students = len(responses)

    return {
        "stats": report, "question_stats": question_stats, "sentiment": {"pos": pos, "neu": neu, "neg": neg},
        "total": total_students, "course_name": course_name, "title": form_title, "responses": [dict(r) for r in responses]
    }

@app.route('/api/attainment', methods=['GET'])
def get_attainment_api():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    return jsonify(get_attainment_data(request.args.get('form_id')))

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
    cw.writerow(['Code', 'Eval Points (Students x Mappings)', 'Average Score', 'Attainment %', 'NBA Level'])
    for row in data['stats']: cw.writerow([row['code'], row['student_count'], row['avg'], f"{row['pct']}%", row['level']])
    cw.writerow([])
    cw.writerow(['PART 2: RAW RESPONSES & SENTIMENT'])
    cw.writerow(['Student', 'Sentiment', 'Answers'])
    for r in data['responses']:
        ans = json.loads(r['answers_json'])
        qa = " | ".join([f"[{','.join(a.get('mappings', []))}] {a['answer']}" for a in ans])
        cw.writerow([r['student_name'], r['sentiment_label'], qa])
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={data['course_name']}_Data.csv"
    output.headers["Content-type"] = "text/csv"
    return output

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

    # ADD THE COLLEGE SPECIFIC CO SYLLABUS LEGEND IF IT EXISTS
    if data['course_name'] in COURSE_DATA_DB and len(COURSE_DATA_DB[data['course_name']]) > 0:
        pdf.ln(10)
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 6, "Reference: Course Outcomes (CO) Syllabus Mapping", ln=True)
        pdf.set_font("Arial", '', 8)
        for co_text in COURSE_DATA_DB[data['course_name']]:
            pdf.multi_cell(0, 5, co_text.encode('latin-1', 'replace').decode('latin-1'))

    res = make_response(pdf.output(dest='S').encode('latin-1'))
    res.headers['Content-Type'] = 'application/pdf'
    res.headers['Content-Disposition'] = f"attachment; filename={data['course_name'].replace(' ', '_')}_Report.pdf"
    return res

@app.route('/api/ai_summary', methods=['GET'])
def ai_summary():
    if 'user' not in session: return jsonify({"error": "Unauthorized"}), 401
    form_id = request.args.get('form_id')
    if not form_id: return jsonify({"error": "Form ID required"}), 400
    
    conn = sqlite3.connect('instance/feedback.db')
    c = conn.cursor()
    c.execute("SELECT full_text_for_ai FROM responses WHERE form_id = ?", (form_id,))
    rows = c.fetchall()
    conn.close()
    
    feedbacks = [row[0] for row in rows if row[0] and row[0].strip()]
    if not feedbacks:
        return jsonify({"summary": "No text feedback available to summarize."})
        
    combined_text = "\n".join(feedbacks)
    
    prompt = f"""
    You are an expert academic analyst. Summarize the following student feedback for an engineering course.
    Highlight the specific strengths, major weaknesses, and actionable suggestions for the faculty.
    Keep the summary professional, concise (max 150 words), and formatted as a few bullet points.

    STUDENT FEEDBACK:
    \"\"\"{combined_text}\"\"\"
    """
    
    try:
        response = ollama.chat(model='llama3.2', messages=[{'role': 'user', 'content': prompt}])
        summary = response['message']['content'].strip()
        return jsonify({"summary": summary})
    except Exception as e:
        return jsonify({"error": f"AI Error: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True)