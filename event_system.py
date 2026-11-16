"""
================================================================================
College Event Management System (CEMS) - All-In-One Standalone File
================================================================================
A complete, responsive web application for managing college events across three
user roles: Student, Event Organizer, and Admin.

Contains:
1. Backend RESTful API (Flask)
2. Dual-mode Database Layer (SQLite zero-config fallback + MySQL ready)
3. Schema setup & realistic sample seed data
4. Complete Frontend Single-Page Application (HTML5, Tailwind CSS, FontAwesome, Chart.js)
5. Dynamic HTML5 Canvas Certificate Engine (High-Res PNG & Print/PDF download)
6. Real-time Attendance Tracker & Registration Approvals

How to Run:
    pip install flask pymysql werkzeug
    python college_event_system.py
Then open http://localhost:5000 in your browser.
================================================================================
"""

import os
import sys
import io
import csv
import json
import random
import string
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, render_template_string, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash

# Try importing pymysql for MySQL support (falls back gracefully if not installed)
try:
    import pymysql
    import pymysql.cursors
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

# ==============================================================================
# CONFIGURATION & DATABASE MANAGER
# ==============================================================================

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'college_event_management_system_secure_key_2026')
    DB_TYPE = os.environ.get('DB_TYPE', 'sqlite').lower()
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', 3306))
    MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'college_events_db')
    SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'college_events.db')

class Database:
    _engine = None

    @classmethod
    def get_engine(cls):
        if cls._engine is None:
            if Config.DB_TYPE == 'mysql' and HAS_PYMYSQL:
                try:
                    conn = pymysql.connect(
                        host=Config.MYSQL_HOST,
                        port=Config.MYSQL_PORT,
                        user=Config.MYSQL_USER,
                        password=Config.MYSQL_PASSWORD,
                        database=Config.MYSQL_DB,
                        cursorclass=pymysql.cursors.DictCursor,
                        autocommit=True
                    )
                    conn.close()
                    cls._engine = 'mysql'
                except Exception:
                    cls._engine = 'sqlite'
            else:
                cls._engine = 'sqlite'
        return cls._engine

    @classmethod
    def get_connection(cls):
        engine = cls.get_engine()
        if engine == 'mysql':
            return pymysql.connect(
                host=Config.MYSQL_HOST,
                port=Config.MYSQL_PORT,
                user=Config.MYSQL_USER,
                password=Config.MYSQL_PASSWORD,
                database=Config.MYSQL_DB,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True
            )
        else:
            conn = sqlite3.connect(Config.SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            return conn

def _format_sql(sql, engine):
    if engine == 'mysql':
        return sql.replace('?', '%s')
    return sql

def db_query(sql, params=None):
    engine = Database.get_engine()
    formatted = _format_sql(sql, engine)
    conn = Database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(formatted, params or ())
        rows = cur.fetchall()
        if engine == 'sqlite':
            return [dict(r) for r in rows]
        return rows
    finally:
        conn.close()

def db_query_one(sql, params=None):
    rows = db_query(sql, params)
    return rows[0] if rows else None

def db_execute(sql, params=None):
    engine = Database.get_engine()
    formatted = _format_sql(sql, engine)
    conn = Database.get_connection()
    try:
        cur = conn.cursor()
        cur.execute(formatted, params or ())
        if engine == 'sqlite':
            conn.commit()
        return cur.lastrowid
    finally:
        conn.close()

def db_execute_script(script):
    engine = Database.get_engine()
    conn = Database.get_connection()
    try:
        if engine == 'sqlite':
            conn.executescript(script)
            conn.commit()
        else:
            cur = conn.cursor()
            for stmt in script.split(';'):
                s = stmt.strip()
                if s:
                    cur.execute(s)
    finally:
        conn.close()

# ==============================================================================
# DATABASE SCHEMA SETUP & SAMPLE DATA SEEDER
# ==============================================================================

def init_db(force=False):
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('student', 'organizer', 'admin')),
        full_name TEXT NOT NULL,
        phone TEXT,
        department TEXT,
        roll_number TEXT,
        year_of_study TEXT,
        organization_unit TEXT,
        status TEXT DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        organizer_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT NOT NULL,
        eligibility TEXT DEFAULT 'Open to all students',
        venue TEXT NOT NULL,
        event_date DATE NOT NULL,
        start_time TEXT NOT NULL,
        end_time TEXT NOT NULL,
        registration_deadline DATETIME NOT NULL,
        max_participants INTEGER NOT NULL DEFAULT 100,
        image_url TEXT,
        status TEXT DEFAULT 'upcoming' CHECK(status IN ('upcoming', 'ongoing', 'completed', 'cancelled')),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (organizer_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS registrations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected', 'attended')),
        registration_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        admin_notes TEXT,
        UNIQUE(event_id, student_id),
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        status TEXT DEFAULT 'present' CHECK(status IN ('present', 'absent')),
        marked_by INTEGER NOT NULL,
        marked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(event_id, student_id),
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (marked_by) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS certificates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        certificate_code TEXT NOT NULL UNIQUE,
        event_id INTEGER NOT NULL,
        student_id INTEGER NOT NULL,
        certificate_type TEXT DEFAULT 'Participation',
        issue_date DATE NOT NULL,
        issuer_name TEXT NOT NULL,
        remarks TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
        FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action_type TEXT NOT NULL,
        description TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """
    db_execute_script(schema)
    admin = db_query_one("SELECT id FROM users WHERE username = ?", ("admin",))
    if not admin or force:
        seed_data()

def seed_data():
    now = datetime.now()
    
    # 1. Users
    users_data = [
        ("admin", "admin@college.edu", generate_password_hash("admin123"), "admin", "System Administrator", "+1 (555) 019-2831", "Administration", None, None, "Campus Affairs", "active"),
        ("organizer", "sarah.jenkins@college.edu", generate_password_hash("org123"), "organizer", "Prof. Sarah Jenkins", "+1 (555) 432-1098", "Computer Science & Eng", None, None, "ACM Student Chapter & CS Club", "active"),
        ("organizer2", "david.reynolds@college.edu", generate_password_hash("org123"), "organizer", "David Reynolds", "+1 (555) 765-4321", "Arts & Media", None, None, "Cultural Affairs & Arts Society", "active"),
        ("organizer3", "marcus.vance@college.edu", generate_password_hash("org123"), "organizer", "Coach Marcus Vance", "+1 (555) 987-6543", "Physical Education", None, None, "Athletics & Sports Board", "active"),
        ("student", "alex.morgan@college.edu", generate_password_hash("student123"), "student", "Alex Morgan", "+1 (555) 123-4567", "Computer Science", "CS-2024-042", "3rd Year", None, "active"),
        ("student2", "priya.sharma@college.edu", generate_password_hash("student123"), "student", "Priya Sharma", "+1 (555) 234-5678", "Information Technology", "IT-2024-019", "2nd Year", None, "active"),
        ("student3", "ethan.clark@college.edu", generate_password_hash("student123"), "student", "Ethan Clark", "+1 (555) 345-6789", "Electronics & Comm", "EC-2023-088", "4th Year", None, "active"),
        ("student4", "emma.watson@college.edu", generate_password_hash("student123"), "student", "Emma Watson", "+1 (555) 567-8901", "Mechanical Eng", "ME-2025-012", "1st Year", None, "active")
    ]
    u_map = {}
    for u in users_data:
        try:
            uid = db_execute(
                "INSERT INTO users (username, email, password_hash, role, full_name, phone, department, roll_number, year_of_study, organization_unit, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                u
            )
            u_map[u[0]] = uid
        except Exception:
            existing = db_query_one("SELECT id FROM users WHERE username = ?", (u[0],))
            if existing:
                u_map[u[0]] = existing['id']

    # 2. Events
    events_data = [
        (u_map.get("organizer", 2), "National Hackathon: CodeSprint 2026", "Hackathon", "A 36-hour non-stop premier coding competition bringing together student innovators to build cutting-edge solutions in AI and FinTech. $10,000 cash prize pool.", "Undergrad & Graduate engineering students.", "Turing Auditorium & Innovation Hub", (now + timedelta(days=12)).strftime('%Y-%m-%d'), "09:00 AM", "06:00 PM", (now + timedelta(days=10)).strftime('%Y-%m-%d 23:59:59'), 120, "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?auto=format&fit=crop&w=800&q=80", "upcoming"),
        (u_map.get("organizer", 2), "AI & Machine Learning Bootcamp", "Workshop", "Comprehensive hands-on deep dive into Transformer architectures, PyTorch, and fine-tuning open-source LLMs.", "All enrolled college students.", "Computer Science Hall C-201", (now - timedelta(days=15)).strftime('%Y-%m-%d'), "10:00 AM", "04:00 PM", (now - timedelta(days=18)).strftime('%Y-%m-%d 23:59:59'), 60, "https://images.unsplash.com/photo-1531482615713-2afd69097998?auto=format&fit=crop&w=800&q=80", "completed"),
        (u_map.get("organizer2", 3), "Annual Cultural Fest: Tarang 2026", "Cultural", "Celebration of performing arts, live band wars, dance battles, and theatre. Over 25 colleges participating.", "Open to all students.", "Main Campus Amphitheatre", (now + timedelta(days=20)).strftime('%Y-%m-%d'), "04:30 PM", "10:00 PM", (now + timedelta(days=18)).strftime('%Y-%m-%d 23:59:59'), 500, "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?auto=format&fit=crop&w=800&q=80", "upcoming"),
        (u_map.get("organizer3", 4), "Inter-College Football Championship", "Sports", "Annual university league tournament featuring 16 top collegiate teams competing for the Chancellor's Cup.", "Registered sports club members.", "University Sports Complex", (now + timedelta(days=7)).strftime('%Y-%m-%d'), "08:00 AM", "05:00 PM", (now + timedelta(days=5)).strftime('%Y-%m-%d 18:00:00'), 160, "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?auto=format&fit=crop&w=800&q=80", "upcoming"),
        (u_map.get("organizer", 2), "Cybersecurity & Ethical Hacking Seminar", "Seminar", "Live demonstration of penetration testing, network defense frameworks, and zero-day threat analysis.", "Open to all students.", "Sir C.V. Raman Seminar Hall", (now + timedelta(days=25)).strftime('%Y-%m-%d'), "02:00 PM", "05:30 PM", (now + timedelta(days=24)).strftime('%Y-%m-%d 12:00:00'), 150, "https://images.unsplash.com/photo-1550751827-4bd374c3f58b?auto=format&fit=crop&w=800&q=80", "upcoming"),
        (u_map.get("organizer", 2), "Modern Full-Stack Masterclass", "Workshop", "Hands-on project building a SaaS application using FastAPI, PostgreSQL, and React.", "CS/IT students.", "Advanced Software Lab 4", (now - timedelta(days=30)).strftime('%Y-%m-%d'), "09:30 AM", "04:30 PM", (now - timedelta(days=32)).strftime('%Y-%m-%d 23:59:59'), 50, "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?auto=format&fit=crop&w=800&q=80", "completed")
    ]
    for ev in events_data:
        try:
            db_execute("INSERT INTO events (organizer_id, title, category, description, eligibility, venue, event_date, start_time, end_time, registration_deadline, max_participants, image_url, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ev)
        except Exception:
            pass

    # Map events
    evs = db_query("SELECT id, title FROM events")
    ev_map = {e['title']: e['id'] for e in evs}
    alex = u_map.get("student")
    priya = u_map.get("student2")
    ethan = u_map.get("student3")

    # 3. Registrations
    regs = [
        (ev_map.get("National Hackathon: CodeSprint 2026"), alex, "approved", "Verified participant"),
        (ev_map.get("AI & Machine Learning Bootcamp"), alex, "attended", "Completed labs"),
        (ev_map.get("Modern Full-Stack Masterclass"), alex, "attended", "Submitted project"),
        (ev_map.get("Annual Cultural Fest: Tarang 2026"), alex, "pending", "Under review"),
        (ev_map.get("National Hackathon: CodeSprint 2026"), priya, "approved", "Fast-track approved"),
        (ev_map.get("AI & Machine Learning Bootcamp"), priya, "attended", "Attended sessions"),
        (ev_map.get("Inter-College Football Championship"), ethan, "approved", "Varsity player")
    ]
    for r in regs:
        if r[0] and r[1]:
            try:
                db_execute("INSERT OR IGNORE INTO registrations (event_id, student_id, status, admin_notes) VALUES (?, ?, ?, ?)", r)
            except Exception:
                pass

    # 4. Attendance
    bootcamp_id = ev_map.get("AI & Machine Learning Bootcamp")
    if bootcamp_id and alex:
        try:
            db_execute("INSERT OR IGNORE INTO attendance (event_id, student_id, status, marked_by) VALUES (?, ?, 'present', ?)", (bootcamp_id, alex, u_map.get("organizer", 2)))
            db_execute("INSERT OR IGNORE INTO attendance (event_id, student_id, status, marked_by) VALUES (?, ?, 'present', ?)", (bootcamp_id, priya, u_map.get("organizer", 2)))
        except Exception:
            pass

    # 5. Certificates
    if bootcamp_id and alex:
        try:
            db_execute(
                "INSERT OR IGNORE INTO certificates (certificate_code, event_id, student_id, certificate_type, issue_date, issuer_name, remarks) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("CEMS-2026-AIML-082", bootcamp_id, alex, "Merit & Excellence", (now - timedelta(days=12)).strftime('%Y-%m-%d'), "Prof. Sarah Jenkins", "Outstanding demonstration in Transformer models.")
            )
            db_execute(
                "INSERT OR IGNORE INTO certificates (certificate_code, event_id, student_id, certificate_type, issue_date, issuer_name, remarks) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("CEMS-2026-AIML-083", bootcamp_id, priya, "Participation", (now - timedelta(days=12)).strftime('%Y-%m-%d'), "Prof. Sarah Jenkins", "Active engagement in workshop.")
            )
        except Exception:
            pass

    # 6. Activity Logs
    db_execute("INSERT INTO activity_logs (action_type, description) VALUES ('SYSTEM', 'College Event Management System initialized with sample database records.')")

# ==============================================================================
# FLASK APPLICATION & REST API
# ==============================================================================

app = Flask(__name__)
app.config.from_object(Config)

# Auto initialize DB
try:
    init_db()
except Exception as e:
    print(f"[!] Init notice: {e}")

def log_activity(action_type, description, user_id=None):
    try:
        if user_id is None and 'user_id' in session:
            user_id = session['user_id']
        db_execute("INSERT INTO activity_logs (user_id, action_type, description) VALUES (?, ?, ?)", (user_id, action_type, description))
    except Exception:
        pass

def login_required(f):
    @wraps(f)
    def dec(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'message': 'Authentication required.'}), 401
        return f(*args, **kwargs)
    return dec

def role_required(roles):
    def decorator(f):
        @wraps(f)
        def dec(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': 'Authentication required.'}), 401
            if session.get('role') not in roles:
                return jsonify({'success': False, 'message': 'Unauthorized for your role.'}), 403
            return f(*args, **kwargs)
        return dec
    return decorator

def generate_cert_code():
    chars = string.ascii_uppercase + string.digits
    rand = ''.join(random.choices(chars, k=6))
    return f"CEMS-2026-{rand}"

# --- AUTH ENDPOINTS ---

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    role = data.get('role', 'student').strip().lower()
    full_name = data.get('full_name', '').strip()
    phone = data.get('phone', '').strip()
    department = data.get('department', '').strip()
    roll_number = data.get('roll_number', '').strip()
    year_of_study = data.get('year_of_study', '').strip()
    org_unit = data.get('organization_unit', '').strip()

    if not username or not email or not password or not full_name:
        return jsonify({'success': False, 'message': 'All required fields must be filled.'}), 400

    existing = db_query_one("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
    if existing:
        return jsonify({'success': False, 'message': 'Username or Email is already taken.'}), 409

    pwd_hash = generate_password_hash(password)
    try:
        uid = db_execute(
            "INSERT INTO users (username, email, password_hash, role, full_name, phone, department, roll_number, year_of_study, organization_unit, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            (username, email, pwd_hash, role, full_name, phone, department, roll_number or None, year_of_study or None, org_unit or None)
        )
        session['user_id'] = uid
        session['username'] = username
        session['role'] = role
        session['full_name'] = full_name
        log_activity('REGISTER', f"New {role} registered: {full_name}", uid)
        user = db_query_one("SELECT id, username, email, role, full_name, phone, department, roll_number, year_of_study, organization_unit FROM users WHERE id = ?", (uid,))
        return jsonify({'success': True, 'message': 'Registration successful!', 'user': user})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    data = request.get_json() or {}
    ident = data.get('username_or_email', '').strip()
    pwd = data.get('password', '')
    user = db_query_one("SELECT * FROM users WHERE (username = ? OR email = ?)", (ident, ident.lower()))
    if not user or not check_password_hash(user['password_hash'], pwd):
        return jsonify({'success': False, 'message': 'Invalid username/email or password.'}), 401
    if user['status'] != 'active':
        return jsonify({'success': False, 'message': 'Account is inactive. Contact admin.'}), 403

    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['full_name'] = user['full_name']
    log_activity('LOGIN', f"User logged in: {user['full_name']}", user['id'])

    user_info = {k: user[k] for k in ['id', 'username', 'email', 'role', 'full_name', 'phone', 'department', 'roll_number', 'year_of_study', 'organization_unit']}
    return jsonify({'success': True, 'message': f"Welcome back, {user['full_name']}!", 'user': user_info})

@app.route('/api/auth/demo-login', methods=['POST'])
def auth_demo_login():
    role = (request.get_json() or {}).get('role', 'student').lower()
    user = db_query_one("SELECT * FROM users WHERE role = ? LIMIT 1", (role,))
    if not user:
        return jsonify({'success': False, 'message': 'Demo user not found.'}), 404
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    session['full_name'] = user['full_name']
    user_info = {k: user[k] for k in ['id', 'username', 'email', 'role', 'full_name', 'phone', 'department', 'roll_number', 'year_of_study', 'organization_unit']}
    return jsonify({'success': True, 'message': f"Switched to demo {role}.", 'user': user_info})

@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    if 'user_id' not in session:
        return jsonify({'success': False, 'user': None})
    user = db_query_one("SELECT id, username, email, role, full_name, phone, department, roll_number, year_of_study, organization_unit, status FROM users WHERE id = ?", (session['user_id'],))
    if not user or user['status'] != 'active':
        session.clear()
        return jsonify({'success': False, 'user': None})
    return jsonify({'success': True, 'user': user})

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully.'})

# --- EVENTS & OVERVIEW ---

@app.route('/api/events', methods=['GET'])
def get_events():
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '').strip()
    
    sql = """
        SELECT e.*, u.full_name as organizer_name, u.organization_unit,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('pending', 'approved', 'attended')) as total_registered
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        WHERE 1=1
    """
    params = []
    if category and category.lower() != 'all':
        sql += " AND e.category = ?"
        params.append(category)
    if search:
        sql += " AND (e.title LIKE ? OR e.description LIKE ? OR e.venue LIKE ?)"
        wc = f"%{search}%"
        params.extend([wc, wc, wc])
    sql += " ORDER BY e.event_date ASC, e.start_time ASC"

    events = db_query(sql, params)
    curr_uid = session.get('user_id')
    curr_role = session.get('role')

    for ev in events:
        ev['seats_left'] = max(0, ev['max_participants'] - ev['total_registered'])
        ev['is_full'] = ev['total_registered'] >= ev['max_participants']
        try:
            dl = datetime.strptime(str(ev['registration_deadline']), '%Y-%m-%d %H:%M:%S')
            ev['is_deadline_passed'] = datetime.now() > dl
        except Exception:
            ev['is_deadline_passed'] = False
        if curr_uid and curr_role == 'student':
            reg = db_query_one("SELECT id, status FROM registrations WHERE event_id = ? AND student_id = ?", (ev['id'], curr_uid))
            ev['my_registration'] = reg
        else:
            ev['my_registration'] = None

    return jsonify({'success': True, 'events': events})

@app.route('/api/events/<int:eid>', methods=['GET'])
def get_event_detail(eid):
    ev = db_query_one("""
        SELECT e.*, u.full_name as organizer_name, u.organization_unit,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id AND r.status IN ('pending', 'approved', 'attended')) as total_registered
        FROM events e
        JOIN users u ON e.organizer_id = u.id
        WHERE e.id = ?
    """, (eid,))
    if not ev:
        return jsonify({'success': False, 'message': 'Event not found.'}), 404

    ev['seats_left'] = max(0, ev['max_participants'] - ev['total_registered'])
    ev['is_full'] = ev['total_registered'] >= ev['max_participants']
    try:
        dl = datetime.strptime(str(ev['registration_deadline']), '%Y-%m-%d %H:%M:%S')
        ev['is_deadline_passed'] = datetime.now() > dl
    except Exception:
        ev['is_deadline_passed'] = False

    curr_uid = session.get('user_id')
    ev['my_registration'] = db_query_one("SELECT * FROM registrations WHERE event_id = ? AND student_id = ?", (eid, curr_uid)) if curr_uid else None
    return jsonify({'success': True, 'event': ev})

@app.route('/api/stats/overview', methods=['GET'])
def get_stats_overview():
    s_cnt = db_query_one("SELECT COUNT(*) as c FROM users WHERE role = 'student'")['c']
    e_cnt = db_query_one("SELECT COUNT(*) as c FROM events WHERE status = 'upcoming'")['c']
    r_cnt = db_query_one("SELECT COUNT(*) as c FROM registrations")['c']
    c_cnt = db_query_one("SELECT COUNT(*) as c FROM events WHERE status = 'completed'")['c']
    return jsonify({
        'success': True,
        'stats': {'total_students': s_cnt, 'upcoming_events': e_cnt, 'total_registrations': r_cnt, 'completed_events': c_cnt}
    })

# --- STUDENT MODULE ENDPOINTS ---

@app.route('/api/student/dashboard', methods=['GET'])
@role_required(['student'])
def student_dashboard():
    sid = session['user_id']
    tot_reg = db_query_one("SELECT COUNT(*) as c FROM registrations WHERE student_id = ?", (sid,))['c']
    app_reg = db_query_one("SELECT COUNT(*) as c FROM registrations WHERE student_id = ? AND status IN ('approved', 'attended')", (sid,))['c']
    att_cnt = db_query_one("SELECT COUNT(*) as c FROM attendance WHERE student_id = ? AND status = 'present'", (sid,))['c']
    crt_cnt = db_query_one("SELECT COUNT(*) as c FROM certificates WHERE student_id = ?", (sid,))['c']

    upcoming = db_query("""
        SELECT r.id as registration_id, r.status as registration_status,
               e.id as event_id, e.title, e.category, e.event_date, e.venue, e.image_url
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        WHERE r.student_id = ? AND e.status = 'upcoming'
        ORDER BY e.event_date ASC LIMIT 5
    """, (sid,))

    recent_certs = db_query("""
        SELECT c.*, e.title as event_title
        FROM certificates c
        JOIN events e ON c.event_id = e.id
        WHERE c.student_id = ?
        ORDER BY c.issue_date DESC LIMIT 4
    """, (sid,))

    return jsonify({
        'success': True,
        'stats': {'total_registered': tot_reg, 'approved_count': app_reg, 'attended_count': att_cnt, 'certificates_count': crt_cnt},
        'upcoming_events': upcoming,
        'recent_certificates': recent_certs
    })

@app.route('/api/student/register-event', methods=['POST'])
@role_required(['student'])
def student_register_event():
    eid = (request.get_json() or {}).get('event_id')
    sid = session['user_id']
    if not eid:
        return jsonify({'success': False, 'message': 'Event ID required.'}), 400

    ev = db_query_one("SELECT * FROM events WHERE id = ?", (eid,))
    if not ev or ev['status'] != 'upcoming':
        return jsonify({'success': False, 'message': 'Event not available for registration.'}), 400

    try:
        dl = datetime.strptime(str(ev['registration_deadline']), '%Y-%m-%d %H:%M:%S')
        if datetime.now() > dl:
            return jsonify({'success': False, 'message': 'Registration deadline has passed.'}), 400
    except Exception:
        pass

    existing = db_query_one("SELECT status FROM registrations WHERE event_id = ? AND student_id = ?", (eid, sid))
    if existing:
        return jsonify({'success': False, 'message': f"You already registered (Status: {existing['status']})."}), 409

    cur_cnt = db_query_one("SELECT COUNT(*) as c FROM registrations WHERE event_id = ? AND status IN ('pending', 'approved', 'attended')", (eid,))['c']
    if cur_cnt >= ev['max_participants']:
        return jsonify({'success': False, 'message': 'Event capacity limit reached.'}), 400

    rid = db_execute("INSERT INTO registrations (event_id, student_id, status) VALUES (?, ?, 'pending')", (eid, sid))
    log_activity('REGISTER', f"Registered for '{ev['title']}'", sid)
    return jsonify({'success': True, 'message': 'Registration submitted! It is pending approval.', 'registration_id': rid})

@app.route('/api/student/my-registrations', methods=['GET'])
@role_required(['student'])
def student_my_registrations():
    sid = session['user_id']
    regs = db_query("""
        SELECT r.id as registration_id, r.status as registration_status, r.registration_date,
               e.id as event_id, e.title as event_title, e.category, e.event_date, e.venue, e.status as event_status,
               u.full_name as organizer_name,
               c.id as certificate_id, c.certificate_code,
               a.status as attendance_status
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u ON e.organizer_id = u.id
        LEFT JOIN certificates c ON (c.event_id = e.id AND c.student_id = r.student_id)
        LEFT JOIN attendance a ON (a.event_id = e.id AND a.student_id = r.student_id)
        WHERE r.student_id = ?
        ORDER BY r.registration_date DESC
    """, (sid,))
    return jsonify({'success': True, 'registrations': regs})

@app.route('/api/student/cancel-registration', methods=['POST'])
@role_required(['student'])
def student_cancel_registration():
    rid = (request.get_json() or {}).get('registration_id')
    sid = session['user_id']
    reg = db_query_one("SELECT r.*, e.status as event_status FROM registrations r JOIN events e ON r.event_id = e.id WHERE r.id = ? AND r.student_id = ?", (rid, sid))
    if not reg or reg['event_status'] == 'completed':
        return jsonify({'success': False, 'message': 'Cannot cancel registration.'}), 400
    db_execute("DELETE FROM registrations WHERE id = ?", (rid,))
    return jsonify({'success': True, 'message': 'Registration cancelled.'})

@app.route('/api/student/my-certificates', methods=['GET'])
@role_required(['student'])
def student_my_certificates():
    sid = session['user_id']
    certs = db_query("""
        SELECT c.*, e.title as event_title, e.category, e.event_date, e.venue,
               u.full_name as student_name, u.roll_number, u.department
        FROM certificates c
        JOIN events e ON c.event_id = e.id
        JOIN users u ON c.student_id = u.id
        WHERE c.student_id = ?
        ORDER BY c.issue_date DESC
    """, (sid,))
    return jsonify({'success': True, 'certificates': certs})

@app.route('/api/student/profile', methods=['PUT'])
@role_required(['student'])
def student_update_profile():
    data = request.get_json() or {}
    sid = session['user_id']
    db_execute("UPDATE users SET full_name = ?, phone = ?, department = ?, year_of_study = ? WHERE id = ?",
               (data.get('full_name', '').strip(), data.get('phone', '').strip(), data.get('department', '').strip(), data.get('year_of_study', '').strip(), sid))
    session['full_name'] = data.get('full_name')
    return jsonify({'success': True, 'message': 'Profile updated successfully.'})

# --- ORGANIZER MODULE ENDPOINTS ---

@app.route('/api/organizer/dashboard', methods=['GET'])
@role_required(['organizer', 'admin'])
def organizer_dashboard():
    oid = session['user_id']
    is_admin = session.get('role') == 'admin'
    where = "" if is_admin else "WHERE organizer_id = ?"
    params = () if is_admin else (oid,)

    ev_cnt = db_query_one(f"SELECT COUNT(*) as c FROM events {where}", params)['c']
    reg_cnt = db_query_one(f"SELECT COUNT(r.id) as c FROM registrations r JOIN events e ON r.event_id = e.id {where}", params)['c']
    att_cnt = db_query_one(f"SELECT COUNT(a.id) as c FROM attendance a JOIN events e ON a.event_id = e.id {'WHERE a.status = \"present\"' if is_admin else 'WHERE a.status = \"present\" AND e.organizer_id = ?'}", params)['c']
    crt_cnt = db_query_one(f"SELECT COUNT(c.id) as c FROM certificates c JOIN events e ON c.event_id = e.id {where}", params)['c']

    events = db_query(f"""
        SELECT e.*,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.id) as total_registrations,
               (SELECT COUNT(*) FROM attendance a WHERE a.event_id = e.id AND a.status = 'present') as attended_count,
               (SELECT COUNT(*) FROM certificates c WHERE c.event_id = e.id) as certs_issued
        FROM events e {where} ORDER BY e.event_date DESC
    """, params)

    return jsonify({
        'success': True,
        'stats': {'events_count': ev_cnt, 'total_participants': reg_cnt, 'total_attended': att_cnt, 'certificates_issued': crt_cnt},
        'events': events
    })

@app.route('/api/organizer/events', methods=['POST'])
@role_required(['organizer', 'admin'])
def organizer_create_event():
    data = request.get_json() or {}
    oid = session['user_id']
    title = data.get('title', '').strip()
    venue = data.get('venue', '').strip()
    edate = data.get('event_date', '').strip()
    stime = data.get('start_time', '').strip()
    etime = data.get('end_time', '').strip()
    deadl = data.get('registration_deadline', '').strip()
    if not title or not venue or not edate:
        return jsonify({'success': False, 'message': 'Missing required fields.'}), 400

    img = data.get('image_url') or "https://images.unsplash.com/photo-1523240795612-9a054b0db644?auto=format&fit=crop&w=800&q=80"
    eid = db_execute("""
        INSERT INTO events (organizer_id, title, category, description, eligibility, venue, event_date, start_time, end_time, registration_deadline, max_participants, image_url, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (oid, title, data.get('category', 'Technical'), data.get('description', ''), data.get('eligibility', 'Open to all'), venue, edate, stime, etime, deadl, int(data.get('max_participants', 100)), img, data.get('status', 'upcoming')))
    log_activity('EVENT_CREATED', f"Created event '{title}'", oid)
    return jsonify({'success': True, 'message': 'Event created successfully!', 'event_id': eid})

@app.route('/api/organizer/events/<int:eid>', methods=['PUT', 'DELETE'])
@role_required(['organizer', 'admin'])
def organizer_single_event(eid):
    ev = db_query_one("SELECT * FROM events WHERE id = ?", (eid,))
    if not ev:
        return jsonify({'success': False, 'message': 'Event not found.'}), 404
    if session.get('role') != 'admin' and ev['organizer_id'] != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403

    if request.method == 'PUT':
        d = request.get_json() or {}
        db_execute("""
            UPDATE events SET title=?, category=?, description=?, eligibility=?, venue=?, event_date=?, start_time=?, end_time=?, registration_deadline=?, max_participants=?, image_url=?, status=?
            WHERE id=?
        """, (d.get('title', ev['title']), d.get('category', ev['category']), d.get('description', ev['description']), d.get('eligibility', ev['eligibility']), d.get('venue', ev['venue']), d.get('event_date', ev['event_date']), d.get('start_time', ev['start_time']), d.get('end_time', ev['end_time']), d.get('registration_deadline', ev['registration_deadline']), int(d.get('max_participants', ev['max_participants'])), d.get('image_url', ev['image_url']), d.get('status', ev['status']), eid))
        return jsonify({'success': True, 'message': 'Event updated.'})
    else:
        db_execute("DELETE FROM events WHERE id = ?", (eid,))
        return jsonify({'success': True, 'message': 'Event deleted.'})

@app.route('/api/organizer/events/<int:eid>/participants', methods=['GET'])
@role_required(['organizer', 'admin'])
def organizer_participants(eid):
    ev = db_query_one("SELECT * FROM events WHERE id = ?", (eid,))
    if not ev:
        return jsonify({'success': False, 'message': 'Event not found.'}), 404
    participants = db_query("""
        SELECT r.id as registration_id, r.status as registration_status, r.registration_date,
               u.id as student_id, u.full_name, u.email, u.phone, u.department, u.roll_number,
               a.status as attendance_status,
               c.id as certificate_id, c.certificate_code
        FROM registrations r
        JOIN users u ON r.student_id = u.id
        LEFT JOIN attendance a ON (a.event_id = r.event_id AND a.student_id = r.student_id)
        LEFT JOIN certificates c ON (c.event_id = r.event_id AND c.student_id = r.student_id)
        WHERE r.event_id = ?
        ORDER BY r.registration_date ASC
    """, (eid,))
    return jsonify({'success': True, 'event': ev, 'participants': participants})

@app.route('/api/organizer/attendance/mark', methods=['POST'])
@role_required(['organizer', 'admin'])
def organizer_mark_attendance():
    d = request.get_json() or {}
    eid = d.get('event_id')
    sid = d.get('student_id')
    status = d.get('status', 'present').lower()
    mid = session['user_id']
    if not eid or not sid:
        return jsonify({'success': False, 'message': 'Event & Student ID required.'}), 400

    ex = db_query_one("SELECT id FROM attendance WHERE event_id = ? AND student_id = ?", (eid, sid))
    if ex:
        db_execute("UPDATE attendance SET status = ?, marked_by = ?, marked_at = CURRENT_TIMESTAMP WHERE id = ?", (status, mid, ex['id']))
    else:
        db_execute("INSERT INTO attendance (event_id, student_id, status, marked_by) VALUES (?, ?, ?, ?)", (eid, sid, status, mid))

    db_execute("UPDATE registrations SET status = ? WHERE event_id = ? AND student_id = ?", ('attended' if status == 'present' else 'approved', eid, sid))
    return jsonify({'success': True, 'message': f'Attendance marked as {status}.'})

@app.route('/api/organizer/certificates/issue', methods=['POST'])
@role_required(['organizer', 'admin'])
def organizer_issue_certificate():
    d = request.get_json() or {}
    eid = d.get('event_id')
    sid = d.get('student_id')
    ctype = d.get('certificate_type', 'Participation')
    issuer = d.get('issuer_name', session.get('full_name', 'Event Coordinator'))

    ex = db_query_one("SELECT certificate_code FROM certificates WHERE event_id = ? AND student_id = ?", (eid, sid))
    if ex:
        return jsonify({'success': False, 'message': f"Certificate already issued ({ex['certificate_code']})."}), 409

    code = generate_cert_code()
    today = datetime.now().strftime('%Y-%m-%d')
    cid = db_execute("INSERT INTO certificates (certificate_code, event_id, student_id, certificate_type, issue_date, issuer_name, remarks) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (code, eid, sid, ctype, today, issuer, d.get('remarks', '')))
    return jsonify({'success': True, 'message': f'Certificate issued with code: {code}', 'certificate_code': code, 'certificate_id': cid})

@app.route('/api/organizer/certificates/bulk-issue', methods=['POST'])
@role_required(['organizer', 'admin'])
def organizer_bulk_issue():
    eid = (request.get_json() or {}).get('event_id')
    present = db_query("""
        SELECT a.student_id FROM attendance a
        LEFT JOIN certificates c ON (c.event_id = a.event_id AND c.student_id = a.student_id)
        WHERE a.event_id = ? AND a.status = 'present' AND c.id IS NULL
    """, (eid,))
    if not present:
        return jsonify({'success': False, 'message': 'No eligible present attendees without certificates.'}), 404

    today = datetime.now().strftime('%Y-%m-%d')
    issuer = session.get('full_name', 'Event Coordinator')
    for p in present:
        db_execute("INSERT INTO certificates (certificate_code, event_id, student_id, certificate_type, issue_date, issuer_name, remarks) VALUES (?, ?, ?, 'Participation', ?, ?, 'Bulk verified.')",
                   (generate_cert_code(), eid, p['student_id'], today, issuer))
    return jsonify({'success': True, 'message': f'Issued certificates to {len(present)} participants.'})

# --- ADMIN MODULE ENDPOINTS ---

@app.route('/api/admin/dashboard', methods=['GET'])
@role_required(['admin'])
def admin_dashboard():
    stats = {
        'total_students': db_query_one("SELECT COUNT(*) as c FROM users WHERE role = 'student'")['c'],
        'total_organizers': db_query_one("SELECT COUNT(*) as c FROM users WHERE role = 'organizer'")['c'],
        'total_events': db_query_one("SELECT COUNT(*) as c FROM events")['c'],
        'total_registrations': db_query_one("SELECT COUNT(*) as c FROM registrations")['c'],
        'pending_registrations': db_query_one("SELECT COUNT(*) as c FROM registrations WHERE status = 'pending'")['c'],
        'approved_registrations': db_query_one("SELECT COUNT(*) as c FROM registrations WHERE status = 'approved'")['c'],
        'attended_registrations': db_query_one("SELECT COUNT(*) as c FROM registrations WHERE status = 'attended'")['c'],
        'rejected_registrations': db_query_one("SELECT COUNT(*) as c FROM registrations WHERE status = 'rejected'")['c'],
        'certificates_issued': db_query_one("SELECT COUNT(*) as c FROM certificates")['c']
    }
    cat_stats = db_query("SELECT category, COUNT(*) as count FROM events GROUP BY category")
    activities = db_query("SELECT * FROM activity_logs ORDER BY created_at DESC LIMIT 10")
    return jsonify({'success': True, 'stats': stats, 'category_stats': cat_stats, 'recent_activities': activities})

@app.route('/api/admin/students', methods=['GET', 'POST'])
@role_required(['admin'])
def admin_students():
    if request.method == 'GET':
        students = db_query("""
            SELECT u.id, u.username, u.email, u.full_name, u.phone, u.department, u.roll_number, u.year_of_study, u.status,
                   (SELECT COUNT(*) FROM registrations r WHERE r.student_id = u.id) as registered_events_count,
                   (SELECT COUNT(*) FROM certificates c WHERE c.student_id = u.id) as certificates_count
            FROM users u WHERE u.role = 'student' ORDER BY u.created_at DESC
        """)
        return jsonify({'success': True, 'students': students})
    else:
        d = request.get_json() or {}
        sid = db_execute("INSERT INTO users (username, email, password_hash, role, full_name, phone, department, roll_number, year_of_study, status) VALUES (?, ?, ?, 'student', ?, ?, ?, ?, ?, 'active')",
                         (d.get('username'), d.get('email'), generate_password_hash(d.get('password', 'student123')), d.get('full_name'), d.get('phone'), d.get('department'), d.get('roll_number'), d.get('year_of_study')))
        return jsonify({'success': True, 'message': 'Student added.', 'student_id': sid})

@app.route('/api/admin/students/<int:sid>', methods=['PUT', 'DELETE'])
@role_required(['admin'])
def admin_single_student(sid):
    if request.method == 'PUT':
        d = request.get_json() or {}
        db_execute("UPDATE users SET full_name=?, phone=?, department=?, roll_number=?, year_of_study=?, status=? WHERE id=?",
                   (d.get('full_name'), d.get('phone'), d.get('department'), d.get('roll_number'), d.get('year_of_study'), d.get('status'), sid))
        return jsonify({'success': True, 'message': 'Student updated.'})
    else:
        db_execute("DELETE FROM users WHERE id = ?", (sid,))
        return jsonify({'success': True, 'message': 'Student deleted.'})

@app.route('/api/admin/organizers', methods=['GET', 'POST'])
@role_required(['admin'])
def admin_organizers():
    if request.method == 'GET':
        orgs = db_query("""
            SELECT u.id, u.username, u.email, u.full_name, u.phone, u.department, u.organization_unit, u.status,
                   (SELECT COUNT(*) FROM events e WHERE e.organizer_id = u.id) as events_count
            FROM users u WHERE u.role = 'organizer' ORDER BY u.created_at DESC
        """)
        return jsonify({'success': True, 'organizers': orgs})
    else:
        d = request.get_json() or {}
        oid = db_execute("INSERT INTO users (username, email, password_hash, role, full_name, phone, department, organization_unit, status) VALUES (?, ?, ?, 'organizer', ?, ?, ?, ?, 'active')",
                         (d.get('username'), d.get('email'), generate_password_hash(d.get('password', 'org123')), d.get('full_name'), d.get('phone'), d.get('department'), d.get('organization_unit')))
        return jsonify({'success': True, 'message': 'Organizer added.', 'organizer_id': oid})

@app.route('/api/admin/organizers/<int:oid>', methods=['DELETE'])
@role_required(['admin'])
def admin_delete_organizer(oid):
    db_execute("DELETE FROM users WHERE id = ?", (oid,))
    return jsonify({'success': True, 'message': 'Organizer deleted.'})

@app.route('/api/admin/registrations', methods=['GET'])
@role_required(['admin'])
def admin_registrations():
    status = request.args.get('status', '').strip()
    sql = """
        SELECT r.id, r.status, r.registration_date, r.admin_notes,
               e.title as event_title, u.full_name as student_name, u.roll_number, u.department
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u ON r.student_id = u.id
        WHERE 1=1
    """
    params = []
    if status and status != 'all':
        sql += " AND r.status = ?"
        params.append(status)
    sql += " ORDER BY r.registration_date DESC"
    return jsonify({'success': True, 'registrations': db_query(sql, params)})

@app.route('/api/admin/registrations/<int:rid>/status', methods=['PUT'])
@role_required(['admin'])
def admin_registration_status(rid):
    d = request.get_json() or {}
    db_execute("UPDATE registrations SET status = ?, admin_notes = ? WHERE id = ?", (d.get('status'), d.get('admin_notes', ''), rid))
    return jsonify({'success': True, 'message': 'Registration status updated.'})

@app.route('/api/admin/reports/summary', methods=['GET'])
@role_required(['admin', 'organizer'])
def admin_reports_summary():
    ev_rep = db_query("""
        SELECT e.id, e.title, e.category, e.event_date, e.max_participants,
               COUNT(r.id) as total_registered,
               SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) as present_count,
               (SELECT COUNT(*) FROM certificates c WHERE c.event_id = e.id) as certificates_issued
        FROM events e
        LEFT JOIN registrations r ON e.id = r.event_id
        LEFT JOIN attendance a ON (a.event_id = e.id AND a.student_id = r.student_id)
        GROUP BY e.id ORDER BY e.event_date DESC
    """)
    dept_rep = db_query("""
        SELECT u.department, COUNT(r.id) as registration_count, COUNT(DISTINCT u.id) as unique_students
        FROM users u LEFT JOIN registrations r ON u.id = r.student_id
        WHERE u.role = 'student' AND u.department IS NOT NULL AND u.department != ''
        GROUP BY u.department ORDER BY registration_count DESC
    """)
    return jsonify({'success': True, 'events_report': ev_rep, 'department_report': dept_rep})

@app.route('/api/admin/reports/export-csv', methods=['GET'])
@role_required(['admin', 'organizer'])
def admin_export_csv():
    rows = db_query("""
        SELECT e.title as event_name, e.category, e.event_date, e.venue,
               u.full_name as student_name, u.roll_number, u.department,
               r.status as reg_status, r.registration_date,
               COALESCE(a.status, 'Not Marked') as attendance,
               COALESCE(c.certificate_code, 'N/A') as certificate_code
        FROM registrations r
        JOIN events e ON r.event_id = e.id
        JOIN users u ON r.student_id = u.id
        LEFT JOIN attendance a ON (a.event_id = e.id AND a.student_id = r.student_id)
        LEFT JOIN certificates c ON (c.event_id = e.id AND c.student_id = r.student_id)
        ORDER BY e.event_date DESC
    """)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['Event', 'Category', 'Date', 'Venue', 'Student', 'Roll No', 'Dept', 'Reg Status', 'Reg Date', 'Attendance', 'Cert Code'])
    for r in rows:
        w.writerow([r['event_name'], r['category'], r['event_date'], r['venue'], r['student_name'], r['roll_number'], r['department'], r['reg_status'], r['registration_date'], r['attendance'], r['certificate_code']])
    resp = make_response(out.getvalue())
    resp.headers['Content-Disposition'] = 'attachment; filename=cems_participation_report.csv'
    resp.headers['Content-Type'] = 'text/csv'
    return resp

# --- CERTIFICATE DETAILS & VERIFICATION ---

@app.route('/api/certificates/<int:cid>', methods=['GET'])
def get_cert(cid):
    c = db_query_one("""
        SELECT c.*, e.title as event_title, e.category as event_category, e.event_date, e.venue,
               u.full_name as student_name, u.roll_number, u.department
        FROM certificates c
        JOIN events e ON c.event_id = e.id
        JOIN users u ON c.student_id = u.id
        WHERE c.id = ?
    """, (cid,))
    return jsonify({'success': bool(c), 'certificate': c}) if c else (jsonify({'success': False, 'message': 'Not found'}), 404)

@app.route('/api/certificates/verify/<string:code>', methods=['GET'])
def verify_cert(code):
    c = db_query_one("""
        SELECT c.*, e.title as event_title, e.event_date, u.full_name as student_name, u.roll_number, u.department
        FROM certificates c
        JOIN events e ON c.event_id = e.id
        JOIN users u ON c.student_id = u.id
        WHERE c.certificate_code = ?
    """, (code.strip().upper(),))
    return jsonify({'success': bool(c), 'verified': bool(c), 'certificate': c}) if c else (jsonify({'success': False, 'message': 'Invalid code.'}), 404)

# ==============================================================================
# EMBEDDED COMPLETE FRONTEND SPA (HTML, CSS, JS)
# ==============================================================================

@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>College Event Management System (CEMS)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=Playfair+Display:ital,wght@0,600;0,700;1,600&display=swap');
        body { font-family: 'Plus Jakarta Sans', sans-serif; }
        .glass-nav { background: rgba(255, 255, 255, 0.95); backdrop-filter: blur(12px); border-bottom: 1px solid rgba(226, 232, 240, 0.8); }
        .nav-link.active { background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%); color: #fff !important; font-weight: 600; box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25); }
        .nav-link.active i { color: #fff !important; }
        #toast-container { position: fixed; top: 20px; right: 20px; z-index: 99999; display: flex; flex-direction: column; gap: 10px; max-width: 380px; }
        .certificate-frame { background: #fff; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 12px solid #1e293b; outline: 4px solid #d97706; outline-offset: -8px; }
        @media print {
            body * { visibility: hidden; }
            #certificate-render-area, #certificate-render-area * { visibility: visible; }
            #certificate-render-area { position: absolute; left: 0; top: 0; width: 100%; border: none !important; }
            .no-print { display: none !important; }
        }
    </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen flex flex-col antialiased">
    <div id="toast-container"></div>

    <!-- NAVBAR -->
    <header id="public-navbar" class="sticky top-0 z-40 glass-nav">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between h-16">
            <div class="flex items-center gap-3 cursor-pointer" onclick="App.showView('public-home')">
                <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 flex items-center justify-center text-white shadow-md">
                    <i class="fa-solid fa-graduation-cap text-lg"></i>
                </div>
                <div>
                    <span class="font-extrabold text-lg text-slate-900 tracking-tight">CEMS <span class="text-xs px-2 py-0.5 rounded-md bg-indigo-100 text-indigo-700 font-bold uppercase">Campus Events</span></span>
                    <p class="text-[10px] text-slate-500 font-medium hidden sm:block">College Event Management System</p>
                </div>
            </div>

            <nav class="hidden md:flex items-center gap-6 text-sm font-semibold text-slate-600">
                <a href="javascript:void(0)" onclick="App.showView('public-home')" class="hover:text-indigo-600">Events</a>
                <a href="javascript:void(0)" onclick="App.openVerifyModal()" class="hover:text-indigo-600 flex items-center gap-1.5">
                    <i class="fa-solid fa-certificate text-amber-500"></i> Verify Certificate
                </a>
            </nav>

            <div class="flex items-center gap-2.5">
                <div class="hidden lg:flex items-center bg-slate-100 p-1 rounded-xl text-xs font-bold gap-1 border border-slate-200">
                    <span class="px-2 text-slate-400 font-medium text-[11px]"><i class="fa-solid fa-bolt text-amber-500 mr-1"></i>Demo:</span>
                    <button onclick="App.triggerDemoLogin('student')" class="px-2.5 py-1 bg-white hover:bg-slate-50 text-indigo-600 rounded-lg shadow-xs border">Student</button>
                    <button onclick="App.triggerDemoLogin('organizer')" class="px-2.5 py-1 bg-white hover:bg-slate-50 text-emerald-600 rounded-lg shadow-xs border">Organizer</button>
                    <button onclick="App.triggerDemoLogin('admin')" class="px-2.5 py-1 bg-white hover:bg-slate-50 text-rose-600 rounded-lg shadow-xs border">Admin</button>
                </div>

                <div id="public-auth-buttons" class="flex items-center gap-2">
                    <button onclick="App.showAuth('login', 'student')" class="px-4 py-2 text-xs font-bold text-slate-700 hover:text-indigo-600">Sign In</button>
                    <button onclick="App.showAuth('register', 'student')" class="px-4 py-2 text-xs font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm">Register</button>
                </div>

                <div id="public-user-dropdown" class="hidden flex items-center gap-2">
                    <button onclick="App.showRolePortal(API.user.role)" class="px-3 py-1.5 bg-indigo-50 border border-indigo-200 rounded-xl flex items-center gap-2">
                        <div class="w-6 h-6 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold"><i class="fa-solid fa-user"></i></div>
                        <div class="text-left">
                            <p id="public-user-name" class="text-xs font-bold text-slate-800 leading-tight">User</p>
                            <p id="public-user-role" class="text-[10px] font-bold text-indigo-600 uppercase">Role</p>
                        </div>
                    </button>
                    <button onclick="App.handleLogout()" class="p-2 text-slate-400 hover:text-rose-600"><i class="fa-solid fa-arrow-right-from-bracket"></i></button>
                </div>
            </div>
        </div>
    </header>

    <!-- VIEW 1: PUBLIC HOME -->
    <main id="view-public-home" class="flex-1">
        <section class="bg-gradient-to-b from-indigo-50/60 via-white to-slate-50 pt-12 pb-16 border-b border-slate-200/60">
            <div class="max-w-7xl mx-auto px-4 text-center max-w-3xl">
                <span class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800 mb-6 border border-indigo-200">
                    <i class="fa-solid fa-sparkles text-indigo-600"></i> Modern Campus Event System
                </span>
                <h1 class="text-4xl sm:text-5xl font-extrabold text-slate-900 tracking-tight leading-tight mb-4">
                    Discover, Participate & Excel in <span class="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">College Events</span>
                </h1>
                <p class="text-base text-slate-600 mb-8">Role-based platform for Students, Organizers, and Admin with event registration, attendance tracking, and verified certificates.</p>

                <div class="bg-white p-2.5 rounded-2xl shadow-xl border border-slate-200 flex flex-col sm:flex-row gap-2 max-w-2xl mx-auto">
                    <div class="flex-1 flex items-center px-3 gap-2">
                        <i class="fa-solid fa-magnifying-glass text-slate-400"></i>
                        <input id="public-search-input" type="text" placeholder="Search by title, keyword, or venue..." class="w-full text-xs sm:text-sm py-2 bg-transparent focus:outline-none">
                    </div>
                    <select id="public-category-select" class="text-xs sm:text-sm font-semibold bg-slate-50 px-3 py-2 rounded-xl border">
                        <option value="all">All Categories</option>
                        <option value="Hackathon">Hackathon</option>
                        <option value="Workshop">Workshop</option>
                        <option value="Cultural">Cultural</option>
                        <option value="Sports">Sports</option>
                        <option value="Seminar">Seminar</option>
                    </select>
                    <button onclick="App.loadPublicEvents(document.getElementById('public-category-select').value, document.getElementById('public-search-input').value)" class="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs sm:text-sm rounded-xl">Find Events</button>
                </div>
            </div>

            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mt-12 max-w-4xl mx-auto px-4">
                <div class="bg-white p-4 rounded-2xl border text-center"><p id="stat-students" class="text-3xl font-extrabold text-indigo-600">8+</p><p class="text-xs font-semibold text-slate-500 uppercase mt-1">Students</p></div>
                <div class="bg-white p-4 rounded-2xl border text-center"><p id="stat-events" class="text-3xl font-extrabold text-emerald-600">4+</p><p class="text-xs font-semibold text-slate-500 uppercase mt-1">Upcoming Events</p></div>
                <div class="bg-white p-4 rounded-2xl border text-center"><p id="stat-registrations" class="text-3xl font-extrabold text-violet-600">10+</p><p class="text-xs font-semibold text-slate-500 uppercase mt-1">Registrations</p></div>
                <div class="bg-white p-4 rounded-2xl border text-center"><p id="stat-completed" class="text-3xl font-extrabold text-amber-600">2+</p><p class="text-xs font-semibold text-slate-500 uppercase mt-1">Completed</p></div>
            </div>
        </section>

        <section class="max-w-7xl mx-auto px-4 py-12">
            <h2 class="text-2xl font-extrabold text-slate-900 tracking-tight mb-6">Upcoming & Featured Events</h2>
            <div id="public-event-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"></div>
        </section>
    </main>

    <!-- VIEW 2: AUTH VIEW -->
    <main id="view-auth-view" class="hidden flex-1 flex items-center justify-center py-12 px-4">
        <div class="w-full max-w-md bg-white rounded-3xl border border-slate-200 shadow-xl overflow-hidden">
            <div class="flex border-b border-slate-200 bg-slate-50">
                <button id="auth-tab-login" onclick="App.switchAuthTab('login')" class="flex-1 py-3 text-center font-bold text-sm text-indigo-600 border-b-2 border-indigo-600">Log In</button>
                <button id="auth-tab-register" onclick="App.switchAuthTab('register')" class="flex-1 py-3 text-center font-bold text-sm text-slate-500">New Registration</button>
            </div>
            <div class="p-6">
                <form id="auth-form-login" onsubmit="App.handleLoginSubmit(event)" class="space-y-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Username or Email</label>
                        <input id="login-identifier" type="text" required class="w-full text-xs py-2.5 px-3 rounded-xl border">
                    </div>
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Password</label>
                        <input id="login-password" type="password" required class="w-full text-xs py-2.5 px-3 rounded-xl border">
                    </div>
                    <button type="submit" class="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl shadow">Sign In</button>
                </form>

                <form id="auth-form-register" onsubmit="App.handleRegisterSubmit(event)" class="hidden space-y-3">
                    <div>
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Role</label>
                        <select id="reg-role" onchange="App.handleRoleChangeInRegister(this.value)" class="w-full text-xs py-2 px-3 rounded-xl border">
                            <option value="student">Student</option>
                            <option value="organizer">Event Organizer</option>
                        </select>
                    </div>
                    <div class="grid grid-cols-2 gap-2">
                        <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1">Username</label><input id="reg-username" type="text" required class="w-full text-xs py-2 px-3 rounded-xl border"></div>
                        <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1">Email</label><input id="reg-email" type="email" required class="w-full text-xs py-2 px-3 rounded-xl border"></div>
                    </div>
                    <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1">Full Name</label><input id="reg-fullname" type="text" required class="w-full text-xs py-2 px-3 rounded-xl border"></div>
                    <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1">Password</label><input id="reg-password" type="password" required class="w-full text-xs py-2 px-3 rounded-xl border"></div>
                    <div class="grid grid-cols-2 gap-2">
                        <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1">Department</label><input id="reg-dept" type="text" class="w-full text-xs py-2 px-3 rounded-xl border"></div>
                        <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1">Phone</label><input id="reg-phone" type="text" class="w-full text-xs py-2 px-3 rounded-xl border"></div>
                    </div>
                    <div id="reg-student-fields" class="grid grid-cols-2 gap-2">
                        <div><label class="block text-xs font-bold text-slate-700 uppercase mb-1">Roll Number</label><input id="reg-roll" type="text" class="w-full text-xs py-2 px-3 rounded-xl border"></div>
                        <div>
                            <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Year of Study</label>
                            <select id="reg-year" class="w-full text-xs py-2 px-3 rounded-xl border"><option value="1st Year">1st Year</option><option value="2nd Year">2nd Year</option><option value="3rd Year">3rd Year</option><option value="4th Year">4th Year</option></select>
                        </div>
                    </div>
                    <div id="reg-organizer-fields" class="hidden">
                        <label class="block text-xs font-bold text-slate-700 uppercase mb-1">Club / Organization Unit</label>
                        <input id="reg-orgunit" type="text" class="w-full text-xs py-2 px-3 rounded-xl border">
                    </div>
                    <button type="submit" class="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl shadow mt-2">Create Account</button>
                </form>
            </div>
        </div>
    </main>

    <!-- VIEW 3: STUDENT PORTAL -->
    <main id="view-student-portal" class="hidden flex-1 flex flex-col md:flex-row bg-slate-100">
        <aside class="w-full md:w-64 bg-white border-r border-slate-200 p-5 flex flex-col justify-between shrink-0">
            <div>
                <div class="p-3 bg-indigo-50 rounded-2xl border border-indigo-100 mb-6 flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center font-bold"><i class="fa-solid fa-graduation-cap"></i></div>
                    <div><h4 class="font-bold text-xs">Student Portal</h4><p class="text-[11px] text-indigo-700 font-semibold">Alex Morgan</p></div>
                </div>
                <nav class="space-y-1.5 text-xs font-semibold">
                    <button id="student-nav-dashboard" onclick="App.switchStudentSection('dashboard')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-chart-pie"></i> Dashboard</button>
                    <button id="student-nav-browse" onclick="App.switchStudentSection('browse')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-regular fa-calendar-check"></i> Browse Events</button>
                    <button id="student-nav-registrations" onclick="App.switchStudentSection('registrations')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-clock-rotate-left"></i> My Registrations</button>
                    <button id="student-nav-certificates" onclick="App.switchStudentSection('certificates')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-award"></i> My Certificates</button>
                    <button id="student-nav-profile" onclick="App.switchStudentSection('profile')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-regular fa-user"></i> My Profile</button>
                </nav>
            </div>
            <button onclick="App.handleLogout()" class="w-full px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50 rounded-xl flex items-center gap-2"><i class="fa-solid fa-arrow-right-from-bracket"></i> Sign Out</button>
        </aside>

        <section class="flex-1 p-6 lg:p-8 overflow-y-auto">
            <div id="student-sec-dashboard" class="space-y-6">
                <h2 class="text-2xl font-extrabold text-slate-900">Student Dashboard</h2>
                <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <div class="bg-white p-5 rounded-2xl border"><p class="text-xs font-bold text-slate-500 uppercase">Registered</p><p id="st-dash-total-reg" class="text-3xl font-extrabold text-indigo-600 mt-2">0</p></div>
                    <div class="bg-white p-5 rounded-2xl border"><p class="text-xs font-bold text-slate-500 uppercase">Approved</p><p id="st-dash-approved" class="text-3xl font-extrabold text-emerald-600 mt-2">0</p></div>
                    <div class="bg-white p-5 rounded-2xl border"><p class="text-xs font-bold text-slate-500 uppercase">Attended</p><p id="st-dash-attended" class="text-3xl font-extrabold text-purple-600 mt-2">0</p></div>
                    <div class="bg-white p-5 rounded-2xl border"><p class="text-xs font-bold text-slate-500 uppercase">Certificates</p><p id="st-dash-certs" class="text-3xl font-extrabold text-amber-500 mt-2">0</p></div>
                </div>
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="bg-white p-6 rounded-2xl border"><h3 class="font-bold text-sm mb-4">Upcoming Registered Events</h3><div id="st-dash-upcoming-list" class="space-y-3"></div></div>
                    <div class="bg-white p-6 rounded-2xl border"><h3 class="font-bold text-sm mb-4">Recent Certificates</h3><div id="st-dash-certs-list" class="space-y-3"></div></div>
                </div>
            </div>

            <div id="student-sec-browse" class="hidden space-y-6">
                <h2 class="text-2xl font-extrabold text-slate-900">Available College Events</h2>
                <div id="student-events-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"></div>
            </div>

            <div id="student-sec-registrations" class="hidden space-y-6">
                <h2 class="text-2xl font-extrabold text-slate-900">Registration History</h2>
                <div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-left text-xs"><tbody id="student-registrations-tbody"></tbody></table></div>
            </div>

            <div id="student-sec-certificates" class="hidden space-y-6">
                <h2 class="text-2xl font-extrabold text-slate-900">My Certificates</h2>
                <div id="student-certificates-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"></div>
            </div>

            <div id="student-sec-profile" class="hidden space-y-6">
                <div class="max-w-xl bg-white p-6 rounded-2xl border">
                    <h2 class="text-xl font-bold mb-4">Profile Details</h2>
                    <form onsubmit="App.handleStudentProfileUpdate(event)" class="space-y-4 text-xs">
                        <div><label class="block font-bold mb-1">Full Name</label><input id="st-prof-name" type="text" required class="w-full py-2 px-3 rounded-xl border"></div>
                        <div><label class="block font-bold mb-1">Department</label><input id="st-prof-dept" type="text" class="w-full py-2 px-3 rounded-xl border"></div>
                        <div><label class="block font-bold mb-1">Phone</label><input id="st-prof-phone" type="text" class="w-full py-2 px-3 rounded-xl border"></div>
                        <button type="submit" class="px-5 py-2.5 bg-indigo-600 text-white font-bold rounded-xl shadow">Save Profile</button>
                    </form>
                </div>
            </div>
        </section>
    </main>

    <!-- VIEW 4: ORGANIZER PORTAL -->
    <main id="view-organizer-portal" class="hidden flex-1 flex flex-col md:flex-row bg-slate-100">
        <aside class="w-full md:w-64 bg-white border-r border-slate-200 p-5 flex flex-col justify-between shrink-0">
            <div>
                <div class="p-3 bg-emerald-50 rounded-2xl border border-emerald-100 mb-6 flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-emerald-600 text-white flex items-center justify-center font-bold"><i class="fa-solid fa-calendar-check"></i></div>
                    <div><h4 class="font-bold text-xs">Organizer Desk</h4><p class="text-[11px] text-emerald-700 font-semibold">Prof. Sarah Jenkins</p></div>
                </div>
                <nav class="space-y-1.5 text-xs font-semibold">
                    <button id="org-nav-dashboard" onclick="App.switchOrganizerSection('dashboard')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-chart-line"></i> Dashboard</button>
                    <button id="org-nav-events" onclick="App.switchOrganizerSection('events')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-calendar-days"></i> Manage Events</button>
                    <button id="org-nav-participants" onclick="App.switchOrganizerSection('participants')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-clipboard-user"></i> Attendance & Certs</button>
                    <button id="org-nav-reports" onclick="App.switchOrganizerSection('reports')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-file-invoice"></i> Reports</button>
                </nav>
            </div>
            <button onclick="App.handleLogout()" class="w-full px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50 rounded-xl flex items-center gap-2"><i class="fa-solid fa-arrow-right-from-bracket"></i> Sign Out</button>
        </aside>

        <section class="flex-1 p-6 lg:p-8 overflow-y-auto">
            <div id="org-sec-dashboard" class="space-y-6">
                <div class="flex items-center justify-between">
                    <h2 class="text-2xl font-extrabold text-slate-900">Organizer Dashboard</h2>
                    <button onclick="App.openCreateEventModal()" class="px-4 py-2 bg-emerald-600 text-white font-bold text-xs rounded-xl shadow">+ Create Event</button>
                </div>
                <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
                    <div class="bg-white p-5 rounded-2xl border"><p class="text-xs font-bold text-slate-500 uppercase">Events</p><p id="org-stat-events" class="text-3xl font-extrabold text-emerald-600 mt-2">0</p></div>
                    <div class="bg-white p-5 rounded-2xl border"><p class="text-xs font-bold text-slate-500 uppercase">Participants</p><p id="org-stat-participants" class="text-3xl font-extrabold text-indigo-600 mt-2">0</p></div>
                    <div class="bg-white p-5 rounded-2xl border"><p class="text-xs font-bold text-slate-500 uppercase">Attended</p><p id="org-stat-attended" class="text-3xl font-extrabold text-purple-600 mt-2">0</p></div>
                    <div class="bg-white p-5 rounded-2xl border"><p class="text-xs font-bold text-slate-500 uppercase">Certs Issued</p><p id="org-stat-certs" class="text-3xl font-extrabold text-amber-500 mt-2">0</p></div>
                </div>
                <div class="bg-white p-6 rounded-2xl border"><h3 class="font-bold text-sm mb-4">Your Events</h3><table class="w-full text-left text-xs"><tbody id="org-dash-events-tbody"></tbody></table></div>
            </div>

            <div id="org-sec-events" class="hidden space-y-6">
                <div class="flex items-center justify-between">
                    <h2 class="text-2xl font-extrabold text-slate-900">Manage Events</h2>
                    <button onclick="App.openCreateEventModal()" class="px-4 py-2 bg-emerald-600 text-white font-bold text-xs rounded-xl shadow">+ Create Event</button>
                </div>
                <div id="org-events-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"></div>
            </div>

            <div id="org-sec-participants" class="hidden space-y-6">
                <div class="bg-white p-5 rounded-2xl border flex flex-col sm:flex-row justify-between items-center gap-4">
                    <div>
                        <label class="block text-xs font-bold text-slate-500 uppercase mb-1">Select Event</label>
                        <select id="org-part-event-select" onchange="App.openManageParticipants(parseInt(this.value))" class="text-xs font-bold py-2 px-3 rounded-xl border min-w-[280px]"></select>
                    </div>
                    <button onclick="App.bulkIssueCertificates()" class="px-4 py-2 bg-amber-500 text-white font-bold text-xs rounded-xl shadow"><i class="fa-solid fa-ribbon mr-1"></i> Bulk Issue Certs</button>
                </div>
                <div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-left text-xs"><tbody id="org-participants-tbody"></tbody></table></div>
            </div>

            <div id="org-sec-reports" class="hidden space-y-6">
                <h2 class="text-2xl font-extrabold text-slate-900">Reports</h2>
                <div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-left text-xs"><tbody id="org-reports-tbody"></tbody></table></div>
            </div>
        </section>
    </main>

    <!-- VIEW 5: ADMIN PORTAL -->
    <main id="view-admin-portal" class="hidden flex-1 flex flex-col md:flex-row bg-slate-100">
        <aside class="w-full md:w-64 bg-white border-r border-slate-200 p-5 flex flex-col justify-between shrink-0">
            <div>
                <div class="p-3 bg-rose-50 rounded-2xl border border-rose-100 mb-6 flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-rose-600 text-white flex items-center justify-center font-bold"><i class="fa-solid fa-shield-halved"></i></div>
                    <div><h4 class="font-bold text-xs">Admin Control</h4><p class="text-[11px] text-rose-700 font-semibold">Administrator</p></div>
                </div>
                <nav class="space-y-1.5 text-xs font-semibold">
                    <button id="admin-nav-dashboard" onclick="App.switchAdminSection('dashboard')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-chart-pie"></i> Analytics</button>
                    <button id="admin-nav-events" onclick="App.switchAdminSection('events')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-regular fa-calendar"></i> Events</button>
                    <button id="admin-nav-registrations" onclick="App.switchAdminSection('registrations')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-user-check"></i> Approvals</button>
                    <button id="admin-nav-students" onclick="App.switchAdminSection('students')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-user-graduate"></i> Students</button>
                    <button id="admin-nav-organizers" onclick="App.switchAdminSection('organizers')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-user-tie"></i> Organizers</button>
                    <button id="admin-nav-reports" onclick="App.switchAdminSection('reports')" class="nav-link w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-slate-600"><i class="fa-solid fa-chart-column"></i> Reports & CSV</button>
                </nav>
            </div>
            <button onclick="App.handleLogout()" class="w-full px-3 py-2 text-xs font-bold text-rose-600 hover:bg-rose-50 rounded-xl flex items-center gap-2"><i class="fa-solid fa-arrow-right-from-bracket"></i> Sign Out</button>
        </aside>

        <section class="flex-1 p-6 lg:p-8 overflow-y-auto">
            <div id="admin-sec-dashboard" class="space-y-6">
                <h2 class="text-2xl font-extrabold text-slate-900">System Analytics & Overview</h2>
                <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                    <div class="bg-white p-4 rounded-2xl border"><p class="text-[11px] font-bold text-slate-500 uppercase">Students</p><p id="adm-stat-students" class="text-2xl font-extrabold text-indigo-600">0</p></div>
                    <div class="bg-white p-4 rounded-2xl border"><p class="text-[11px] font-bold text-slate-500 uppercase">Events</p><p id="adm-stat-events" class="text-2xl font-extrabold text-emerald-600">0</p></div>
                    <div class="bg-white p-4 rounded-2xl border"><p class="text-[11px] font-bold text-slate-500 uppercase">Registrations</p><p id="adm-stat-registrations" class="text-2xl font-extrabold text-purple-600">0</p></div>
                    <div class="bg-white p-4 rounded-2xl border"><p class="text-[11px] font-bold text-slate-500 uppercase">Pending</p><p id="adm-stat-pending-regs" class="text-2xl font-extrabold text-amber-500">0</p></div>
                    <div class="bg-white p-4 rounded-2xl border"><p class="text-[11px] font-bold text-slate-500 uppercase">Approved</p><p id="adm-stat-approved-regs" class="text-2xl font-extrabold text-emerald-600">0</p></div>
                    <div class="bg-white p-4 rounded-2xl border"><p class="text-[11px] font-bold text-slate-500 uppercase">Certificates</p><p id="adm-stat-certs" class="text-2xl font-extrabold text-amber-600">0</p></div>
                </div>
                <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <div class="bg-white p-6 rounded-2xl border"><h3 class="font-bold text-sm mb-4">Events by Category</h3><div class="h-64"><canvas id="admin-chart-categories"></canvas></div></div>
                    <div class="bg-white p-6 rounded-2xl border"><h3 class="font-bold text-sm mb-4">Registrations by Status</h3><div class="h-64"><canvas id="admin-chart-registrations"></canvas></div></div>
                </div>
                <div class="bg-white p-6 rounded-2xl border"><h3 class="font-bold text-sm mb-4">Recent Audit Activity</h3><div id="adm-dash-activities" class="space-y-2"></div></div>
            </div>

            <div id="admin-sec-events" class="hidden space-y-6">
                <div class="flex items-center justify-between">
                    <h2 class="text-2xl font-extrabold text-slate-900">All Events</h2>
                    <button onclick="App.openCreateEventModal()" class="px-4 py-2 bg-indigo-600 text-white font-bold text-xs rounded-xl shadow">+ Create Event</button>
                </div>
                <div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-left text-xs"><tbody id="admin-events-tbody"></tbody></table></div>
            </div>

            <div id="admin-sec-registrations" class="hidden space-y-6">
                <h2 class="text-2xl font-extrabold text-slate-900">Registration Approvals</h2>
                <div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-left text-xs"><tbody id="admin-registrations-tbody"></tbody></table></div>
            </div>

            <div id="admin-sec-students" class="hidden space-y-6">
                <div class="flex items-center justify-between">
                    <h2 class="text-2xl font-extrabold text-slate-900">Student Accounts</h2>
                    <button onclick="App.openAddStudentModal()" class="px-4 py-2 bg-indigo-600 text-white font-bold text-xs rounded-xl shadow">+ Add Student</button>
                </div>
                <div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-left text-xs"><tbody id="admin-students-tbody"></tbody></table></div>
            </div>

            <div id="admin-sec-organizers" class="hidden space-y-6">
                <div class="flex items-center justify-between">
                    <h2 class="text-2xl font-extrabold text-slate-900">Event Organizers</h2>
                    <button onclick="App.openAddOrganizerModal()" class="px-4 py-2 bg-emerald-600 text-white font-bold text-xs rounded-xl shadow">+ Add Organizer</button>
                </div>
                <div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-left text-xs"><tbody id="admin-organizers-tbody"></tbody></table></div>
            </div>

            <div id="admin-sec-reports" class="hidden space-y-6">
                <div class="flex items-center justify-between">
                    <h2 class="text-2xl font-extrabold text-slate-900">System Reports</h2>
                    <a href="/api/admin/reports/export-csv" class="px-4 py-2 bg-indigo-600 text-white font-bold text-xs rounded-xl shadow flex items-center gap-1.5"><i class="fa-solid fa-file-csv"></i> Download Master CSV</a>
                </div>
                <div class="bg-white rounded-2xl border overflow-hidden"><table class="w-full text-left text-xs"><tbody id="admin-reports-tbody"></tbody></table></div>
            </div>
        </section>
    </main>

    <!-- MODALS -->
    <!-- 1. Event Detail Modal -->
    <div id="event-detail-modal" class="fixed inset-0 z-50 hidden bg-slate-950/60 backdrop-blur-xs items-center justify-center p-4">
        <div class="bg-white rounded-3xl max-w-xl w-full max-h-[90vh] overflow-hidden flex flex-col shadow-2xl">
            <div class="relative h-48 bg-slate-100">
                <img id="modal-ev-img" src="" class="w-full h-full object-cover">
                <button onclick="App.closeEventModal()" class="absolute top-4 right-4 w-8 h-8 rounded-full bg-slate-900/70 text-white flex items-center justify-center"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <div class="p-6 overflow-y-auto space-y-4 text-xs">
                <h2 id="modal-ev-title" class="text-xl font-bold text-slate-900"></h2>
                <div class="p-3 bg-slate-50 rounded-xl space-y-1">
                    <div><span class="text-slate-400">Date:</span> <span id="modal-ev-date" class="font-bold"></span> | <span id="modal-ev-time"></span></div>
                    <div><span class="text-slate-400">Venue:</span> <span id="modal-ev-venue" class="font-bold"></span></div>
                    <div><span class="text-slate-400">Host:</span> <span id="modal-ev-organizer" class="font-bold"></span></div>
                    <div><span class="text-slate-400">Capacity:</span> <span id="modal-ev-capacity" class="font-bold"></span></div>
                </div>
                <p id="modal-ev-desc" class="text-slate-600 leading-relaxed"></p>
                <div id="modal-ev-action-container" class="pt-4 border-t"></div>
            </div>
        </div>
    </div>

    <!-- 2. Create Event Modal -->
    <div id="create-event-modal" class="fixed inset-0 z-50 hidden bg-slate-950/60 backdrop-blur-xs items-center justify-center p-4">
        <div class="bg-white rounded-3xl max-w-lg w-full p-6 shadow-2xl">
            <h3 class="font-bold text-base mb-4">Create / Edit Event</h3>
            <form onsubmit="App.handleSaveEvent(event)" class="space-y-3 text-xs">
                <input id="event-modal-id" type="hidden">
                <div><label class="block font-bold mb-1">Title</label><input id="event-form-title" type="text" required class="w-full py-2 px-3 rounded-xl border"></div>
                <div class="grid grid-cols-2 gap-2">
                    <div><label class="block font-bold mb-1">Category</label><select id="event-form-category" class="w-full py-2 px-3 rounded-xl border"><option value="Technical">Technical</option><option value="Hackathon">Hackathon</option><option value="Workshop">Workshop</option><option value="Cultural">Cultural</option><option value="Sports">Sports</option><option value="Seminar">Seminar</option></select></div>
                    <div><label class="block font-bold mb-1">Max Capacity</label><input id="event-form-capacity" type="number" value="100" class="w-full py-2 px-3 rounded-xl border"></div>
                </div>
                <div class="grid grid-cols-3 gap-2">
                    <div><label class="block font-bold mb-1">Date</label><input id="event-form-date" type="date" required class="w-full py-2 px-2 rounded-xl border"></div>
                    <div><label class="block font-bold mb-1">Start Time</label><input id="event-form-start" type="text" placeholder="10:00 AM" required class="w-full py-2 px-2 rounded-xl border"></div>
                    <div><label class="block font-bold mb-1">End Time</label><input id="event-form-end" type="text" placeholder="04:00 PM" required class="w-full py-2 px-2 rounded-xl border"></div>
                </div>
                <div class="grid grid-cols-2 gap-2">
                    <div><label class="block font-bold mb-1">Venue</label><input id="event-form-venue" type="text" required class="w-full py-2 px-3 rounded-xl border"></div>
                    <div><label class="block font-bold mb-1">Deadline</label><input id="event-form-deadline" type="datetime-local" required class="w-full py-2 px-3 rounded-xl border"></div>
                </div>
                <div><label class="block font-bold mb-1">Description</label><textarea id="event-form-desc" rows="2" required class="w-full py-2 px-3 rounded-xl border"></textarea></div>
                <div class="pt-3 border-t flex justify-end gap-2">
                    <button type="button" onclick="App.closeCreateEventModal()" class="px-4 py-2 bg-slate-100 font-bold rounded-xl">Cancel</button>
                    <button type="submit" class="px-5 py-2 bg-indigo-600 text-white font-bold rounded-xl shadow">Save & Publish</button>
                </div>
            </form>
        </div>
    </div>

    <!-- 3. Add Student Modal -->
    <div id="student-manage-modal" class="fixed inset-0 z-50 hidden bg-slate-950/60 backdrop-blur-xs items-center justify-center p-4">
        <div class="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl">
            <h3 class="font-bold text-base mb-4">Add Student Account</h3>
            <form onsubmit="App.handleSaveStudent(event)" class="space-y-3 text-xs">
                <div><label class="block font-bold mb-1">Username</label><input id="stm-username" type="text" required class="w-full py-2 px-3 rounded-xl border"></div>
                <div><label class="block font-bold mb-1">Email</label><input id="stm-email" type="email" required class="w-full py-2 px-3 rounded-xl border"></div>
                <div><label class="block font-bold mb-1">Full Name</label><input id="stm-name" type="text" required class="w-full py-2 px-3 rounded-xl border"></div>
                <div class="grid grid-cols-2 gap-2">
                    <div><label class="block font-bold mb-1">Roll Number</label><input id="stm-roll" type="text" class="w-full py-2 px-3 rounded-xl border"></div>
                    <div><label class="block font-bold mb-1">Department</label><input id="stm-dept" type="text" class="w-full py-2 px-3 rounded-xl border"></div>
                </div>
                <div class="pt-3 border-t flex justify-end gap-2">
                    <button type="button" onclick="App.closeStudentManageModal()" class="px-4 py-2 bg-slate-100 font-bold rounded-xl">Cancel</button>
                    <button type="submit" class="px-5 py-2 bg-indigo-600 text-white font-bold rounded-xl shadow">Save</button>
                </div>
            </form>
        </div>
    </div>

    <!-- 4. Add Organizer Modal -->
    <div id="organizer-manage-modal" class="fixed inset-0 z-50 hidden bg-slate-950/60 backdrop-blur-xs items-center justify-center p-4">
        <div class="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl">
            <h3 class="font-bold text-base mb-4">Add Event Organizer</h3>
            <form onsubmit="App.handleSaveOrganizer(event)" class="space-y-3 text-xs">
                <div><label class="block font-bold mb-1">Username</label><input id="ogm-username" type="text" required class="w-full py-2 px-3 rounded-xl border"></div>
                <div><label class="block font-bold mb-1">Email</label><input id="ogm-email" type="email" required class="w-full py-2 px-3 rounded-xl border"></div>
                <div><label class="block font-bold mb-1">Full Name</label><input id="ogm-name" type="text" required class="w-full py-2 px-3 rounded-xl border"></div>
                <div><label class="block font-bold mb-1">Club / Organization Unit</label><input id="ogm-orgunit" type="text" class="w-full py-2 px-3 rounded-xl border"></div>
                <div class="pt-3 border-t flex justify-end gap-2">
                    <button type="button" onclick="App.closeOrganizerManageModal()" class="px-4 py-2 bg-slate-100 font-bold rounded-xl">Cancel</button>
                    <button type="submit" class="px-5 py-2 bg-emerald-600 text-white font-bold rounded-xl shadow">Save</button>
                </div>
            </form>
        </div>
    </div>

    <!-- 5. Certificate Preview & Download Modal -->
    <div id="certificate-modal" class="fixed inset-0 z-50 hidden bg-slate-950/80 backdrop-blur-sm items-center justify-center p-4 overflow-y-auto">
        <div class="bg-white rounded-3xl max-w-4xl w-full p-6 shadow-2xl flex flex-col space-y-4 my-auto">
            <div class="flex items-center justify-between border-b pb-3 no-print">
                <div class="flex items-center gap-2">
                    <div class="w-8 h-8 rounded-full bg-amber-500 text-white flex items-center justify-center font-bold"><i class="fa-solid fa-ribbon"></i></div>
                    <h3 class="font-bold text-sm">Official Verified Digital Certificate</h3>
                </div>
                <button onclick="CertificateEngine.closeModal()" class="text-slate-400 hover:text-slate-600"><i class="fa-solid fa-xmark text-lg"></i></button>
            </div>
            <div id="certificate-render-area" class="flex justify-center bg-slate-100 p-2 sm:p-4 rounded-2xl overflow-hidden border">
                <canvas id="cert-canvas" class="max-w-full h-auto rounded-lg shadow-xl certificate-frame"></canvas>
            </div>
            <div class="flex flex-col sm:flex-row items-center justify-between gap-3 pt-2 no-print">
                <div class="text-xs text-slate-500 font-mono">ID: <span id="cert-modal-code" class="font-bold text-indigo-700"></span></div>
                <div class="flex items-center gap-2">
                    <button onclick="window.print()" class="px-4 py-2 bg-slate-100 text-slate-700 font-bold text-xs rounded-xl shadow-xs"><i class="fa-solid fa-print mr-1"></i> Print / PDF</button>
                    <button onclick="CertificateEngine.downloadAsPNG()" class="px-5 py-2 bg-amber-600 text-white font-bold text-xs rounded-xl shadow"><i class="fa-solid fa-download mr-1"></i> Download PNG</button>
                </div>
            </div>
        </div>
    </div>

    <!-- 6. Certificate Verification Modal -->
    <div id="verify-cert-modal" class="fixed inset-0 z-50 hidden bg-slate-950/60 backdrop-blur-xs items-center justify-center p-4">
        <div class="bg-white rounded-3xl max-w-md w-full p-6 shadow-2xl space-y-4">
            <div class="flex items-center justify-between">
                <h3 class="font-bold text-sm"><i class="fa-solid fa-shield-halved text-indigo-600 mr-2"></i>Verify Certificate Authenticity</h3>
                <button onclick="App.closeVerifyModal()" class="text-slate-400"><i class="fa-solid fa-xmark"></i></button>
            </div>
            <form onsubmit="App.handleVerifyCertificate(event)" class="flex gap-2">
                <input id="verify-code-input" type="text" placeholder="e.g. CEMS-2026-AIML-082" required class="flex-1 text-xs py-2 px-3 rounded-xl border uppercase font-mono">
                <button type="submit" class="px-4 py-2 bg-indigo-600 text-white font-bold text-xs rounded-xl shadow">Verify</button>
            </form>
            <div id="verify-cert-result" class="hidden"></div>
        </div>
    </div>

    <!-- EMBEDDED JAVASCRIPT APPLICATION -->
    <script>
        const API = {
            user: null,
            toast(msg, type = 'info', title = '') {
                const c = document.getElementById('toast-container');
                if (!c) return;
                const t = document.createElement('div');
                t.className = `p-4 rounded-xl shadow-lg border flex items-start gap-3 bg-white text-slate-800 ${type === 'success' ? 'border-emerald-200' : type === 'error' ? 'border-rose-200' : 'border-indigo-200'}`;
                t.innerHTML = `<i class="fa-solid ${type === 'success' ? 'fa-circle-check text-emerald-500' : type === 'error' ? 'fa-circle-xmark text-rose-500' : 'fa-circle-info text-indigo-500'} text-xl mt-0.5"></i><div class="flex-1"><p class="font-bold text-xs">${title || type.toUpperCase()}</p><p class="text-xs text-slate-600 mt-0.5">${msg}</p></div>`;
                c.appendChild(t);
                setTimeout(() => t.remove(), 4000);
            },
            async req(url, opt = {}) {
                opt.headers = opt.headers || {};
                if (opt.body && typeof opt.body === 'object') {
                    opt.headers['Content-Type'] = 'application/json';
                    opt.body = JSON.stringify(opt.body);
                }
                const res = await fetch(url, opt);
                const data = await res.json();
                if (!res.ok) throw new Error(data.message || 'Request failed');
                return data;
            },
            get(u) { return this.req(u, { method: 'GET' }); },
            post(u, b) { return this.req(u, { method: 'POST', body: b }); },
            put(u, b) { return this.req(u, { method: 'PUT', body: b }); },
            delete(u) { return this.req(u, { method: 'DELETE' }); },
            async checkSession() {
                try {
                    const r = await this.get('/api/auth/me');
                    if (r.success) this.user = r.user;
                } catch (e) { this.user = null; }
                return this.user;
            },
            async login(u, p) {
                const r = await this.post('/api/auth/login', { username_or_email: u, password: p });
                if (r.success) this.user = r.user;
                return r;
            },
            async demoLogin(role) {
                const r = await this.post('/api/auth/demo-login', { role });
                if (r.success) this.user = r.user;
                return r;
            },
            async logout() {
                await this.post('/api/auth/logout');
                this.user = null;
            }
        };

        const CertificateEngine = {
            currentCert: null,
            renderToCanvas(canvas, cert) {
                const ctx = canvas.getContext('2d');
                const w = 1200, h = 850;
                canvas.width = w; canvas.height = h;
                ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, w, h);
                ctx.strokeStyle = '#1e293b'; ctx.lineWidth = 14; ctx.strokeRect(20, 20, w - 40, h - 40);
                ctx.strokeStyle = '#d97706'; ctx.lineWidth = 4; ctx.strokeRect(34, 34, w - 68, h - 68);

                ctx.fillStyle = '#0f172a'; ctx.font = 'bold 22px sans-serif'; ctx.textAlign = 'center';
                ctx.fillText('METROPOLITAN UNIVERSITY OF TECHNOLOGY & SCIENCE', w/2, 95);
                ctx.fillStyle = '#64748b'; ctx.font = '13px sans-serif';
                ctx.fillText('ACCREDITED AUTONOMOUS INSTITUTION • OFFICE OF STUDENT AFFAIRS', w/2, 120);

                ctx.fillStyle = '#b45309'; ctx.font = 'italic bold 36px Georgia, serif';
                ctx.fillText(`CERTIFICATE OF ${(cert.certificate_type || 'Participation').toUpperCase()}`, w/2, 195);
                ctx.fillStyle = '#475569'; ctx.font = '16px sans-serif';
                ctx.fillText('THIS IS PROUDLY PRESENTED TO', w/2, 240);
                ctx.fillStyle = '#1e1b4b'; ctx.font = 'bold 44px Georgia, serif';
                ctx.fillText(cert.student_name || 'Alex Morgan', w/2, 310);

                ctx.fillStyle = '#334155'; ctx.font = '18px sans-serif';
                ctx.fillText('for successfully demonstrating engagement and achievement during', w/2, 400);
                ctx.fillStyle = '#4338ca'; ctx.font = 'bold 28px sans-serif';
                ctx.fillText(`"${cert.event_title}"`, w/2, 450);

                ctx.fillStyle = '#64748b'; ctx.font = '14px sans-serif';
                ctx.fillText(`Conducted on ${cert.issue_date || cert.event_date || '2026'} at ${cert.venue || 'University Main Campus'}`, w/2, 530);

                // Signatures
                ctx.strokeStyle = '#312e81'; ctx.lineWidth = 1.5; ctx.beginPath();
                ctx.moveTo(220 - 70, 700); ctx.bezierCurveTo(220 - 30, 680, 220, 710, 220 + 70, 700); ctx.stroke();
                ctx.fillStyle = '#0f172a'; ctx.font = 'bold 14px sans-serif';
                ctx.fillText(cert.issuer_name || 'Prof. Sarah Jenkins', 220, 725);
                ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif';
                ctx.fillText('Program Coordinator', 220, 742);

                ctx.beginPath(); ctx.moveTo(w - 220 - 70, 700); ctx.bezierCurveTo(w - 220 - 30, 680, w - 220, 710, w - 220 + 70, 700); ctx.stroke();
                ctx.fillStyle = '#0f172a'; ctx.font = 'bold 14px sans-serif';
                ctx.fillText('Dr. Arthur Campbell', w - 220, 725);
                ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif';
                ctx.fillText('Dean of Student Affairs', w - 220, 742);

                ctx.fillStyle = '#94a3b8'; ctx.font = '12px monospace'; ctx.textAlign = 'left';
                ctx.fillText(`Verification ID: ${cert.certificate_code || 'CEMS-2026-VERIFIED'}`, 55, h - 48);
            },
            async openPreview(cid) {
                const res = await API.get(`/api/certificates/${cid}`);
                if (!res.success) return;
                this.currentCert = res.certificate;
                const modal = document.getElementById('certificate-modal');
                const canvas = document.getElementById('cert-canvas');
                modal.classList.remove('hidden'); modal.classList.add('flex');
                document.getElementById('cert-modal-code').textContent = res.certificate.certificate_code;
                this.renderToCanvas(canvas, res.certificate);
            },
            closeModal() {
                const m = document.getElementById('certificate-modal');
                m.classList.add('hidden'); m.classList.remove('flex');
            },
            downloadAsPNG() {
                const canvas = document.getElementById('cert-canvas');
                const link = document.createElement('a');
                link.download = `Certificate_${(this.currentCert.student_name || 'Student').replace(/\\s+/g, '_')}.png`;
                link.href = canvas.toDataURL('image/png', 1.0);
                link.click();
            }
        };

        const App = {
            charts: {},
            async init() {
                const user = await API.checkSession();
                this.updateHeaderUI();
                if (user) this.showRolePortal(user.role);
                else this.showView('public-home');
                await this.loadPublicEvents();
                await this.loadStats();
            },
            showView(view) {
                ['public-home', 'auth-view', 'student-portal', 'organizer-portal', 'admin-portal'].forEach(v => {
                    const el = document.getElementById(`view-${v}`);
                    if (el) el.classList.toggle('hidden', v !== view);
                });
                const pNav = document.getElementById('public-navbar');
                if (pNav) pNav.classList.toggle('hidden', view !== 'public-home' && view !== 'auth-view');
            },
            showRolePortal(role, sec = 'dashboard') {
                if (!API.user) { this.showAuth('login', role); return; }
                if (role === 'admin') { this.showView('admin-portal'); this.switchAdminSection(sec); }
                else if (role === 'organizer') { this.showView('organizer-portal'); this.switchOrganizerSection(sec); }
                else { this.showView('student-portal'); this.switchStudentSection(sec); }
            },
            updateHeaderUI() {
                const ab = document.getElementById('public-auth-buttons');
                const ud = document.getElementById('public-user-dropdown');
                if (API.user) {
                    ab.classList.add('hidden'); ud.classList.remove('hidden');
                    document.getElementById('public-user-name').textContent = API.user.full_name;
                    document.getElementById('public-user-role').textContent = API.user.role.toUpperCase();
                } else {
                    ab.classList.remove('hidden'); ud.classList.add('hidden');
                }
            },
            async loadStats() {
                const res = await API.get('/api/stats/overview');
                if (res.success) {
                    document.getElementById('stat-students').textContent = res.stats.total_students;
                    document.getElementById('stat-events').textContent = res.stats.upcoming_events;
                    document.getElementById('stat-registrations').textContent = res.stats.total_registrations;
                    document.getElementById('stat-completed').textContent = res.stats.completed_events;
                }
            },
            async loadPublicEvents(cat = 'all', search = '') {
                const res = await API.get(`/api/events?category=${encodeURIComponent(cat)}&search=${encodeURIComponent(search)}`);
                if (res.success) {
                    const c = document.getElementById('public-event-grid');
                    c.innerHTML = res.events.map(ev => `
                        <div class="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm flex flex-col justify-between">
                            <div class="h-44 relative bg-slate-100">
                                <img src="${ev.image_url}" class="w-full h-full object-cover">
                                <span class="absolute top-3 left-3 px-2.5 py-1 text-xs font-bold rounded-full bg-white/90 text-indigo-700">${ev.category}</span>
                            </div>
                            <div class="p-5 flex-1 flex flex-col justify-between">
                                <div>
                                    <p class="text-xs text-slate-500 font-semibold mb-1"><i class="fa-regular fa-calendar text-indigo-500 mr-1"></i> ${ev.event_date} • ${ev.venue}</p>
                                    <h3 class="font-bold text-slate-900 text-base mb-2">${ev.title}</h3>
                                    <p class="text-xs text-slate-600 line-clamp-2 mb-4">${ev.description}</p>
                                </div>
                                <div class="pt-3 border-t flex items-center justify-between">
                                    <span class="text-xs font-bold text-slate-600">${ev.total_registered} / ${ev.max_participants} registered</span>
                                    <button onclick="App.openEventModal(${ev.id})" class="px-4 py-2 bg-indigo-600 text-white font-bold text-xs rounded-xl shadow">View Details</button>
                                </div>
                            </div>
                        </div>
                    `).join('');
                }
            },
            async openEventModal(eid) {
                const res = await API.get(`/api/events/${eid}`);
                if (!res.success) return;
                const ev = res.event;
                document.getElementById('modal-ev-img').src = ev.image_url;
                document.getElementById('modal-ev-title').textContent = ev.title;
                document.getElementById('modal-ev-date').textContent = ev.event_date;
                document.getElementById('modal-ev-time').textContent = `${ev.start_time} - ${ev.end_time}`;
                document.getElementById('modal-ev-venue').textContent = ev.venue;
                document.getElementById('modal-ev-organizer').textContent = ev.organizer_name;
                document.getElementById('modal-ev-capacity').textContent = `${ev.total_registered} / ${ev.max_participants} registered (${ev.seats_left} seats left)`;
                document.getElementById('modal-ev-desc').textContent = ev.description;

                const act = document.getElementById('modal-ev-action-container');
                if (!API.user) {
                    act.innerHTML = `<button onclick="App.closeEventModal(); App.showAuth('login', 'student')" class="w-full py-2.5 bg-indigo-600 text-white font-bold rounded-xl">Sign in to Register</button>`;
                } else if (API.user.role === 'student') {
                    if (ev.my_registration) act.innerHTML = `<span class="text-xs font-bold text-emerald-600">Registered (Status: ${ev.my_registration.status.toUpperCase()})</span>`;
                    else act.innerHTML = `<button onclick="App.registerForEvent(${ev.id})" class="w-full py-2.5 bg-indigo-600 text-white font-bold rounded-xl">Confirm Registration</button>`;
                } else {
                    act.innerHTML = `<span class="text-xs text-slate-500">Logged in as ${API.user.role.toUpperCase()}</span>`;
                }
                const m = document.getElementById('event-detail-modal');
                m.classList.remove('hidden'); m.classList.add('flex');
            },
            closeEventModal() {
                const m = document.getElementById('event-detail-modal');
                m.classList.add('hidden'); m.classList.remove('flex');
            },
            async registerForEvent(eid) {
                try {
                    const r = await API.post('/api/student/register-event', { event_id: eid });
                    API.toast(r.message, 'success');
                    this.closeEventModal();
                    await this.loadPublicEvents();
                } catch (e) { API.toast(e.message, 'error'); }
            },
            showAuth(mode, role) {
                this.showView('auth-view');
                this.switchAuthTab(mode);
            },
            switchAuthTab(mode) {
                const isL = mode === 'login';
                document.getElementById('auth-form-login').classList.toggle('hidden', !isL);
                document.getElementById('auth-form-register').classList.toggle('hidden', isL);
                document.getElementById('auth-tab-login').className = isL ? 'flex-1 py-3 font-bold text-sm text-indigo-600 border-b-2 border-indigo-600' : 'flex-1 py-3 font-bold text-sm text-slate-500';
                document.getElementById('auth-tab-register').className = !isL ? 'flex-1 py-3 font-bold text-sm text-indigo-600 border-b-2 border-indigo-600' : 'flex-1 py-3 font-bold text-sm text-slate-500';
            },
            handleRoleChangeInRegister(r) {
                document.getElementById('reg-student-fields').classList.toggle('hidden', r !== 'student');
                document.getElementById('reg-organizer-fields').classList.toggle('hidden', r === 'student');
            },
            async handleLoginSubmit(e) {
                e.preventDefault();
                try {
                    const r = await API.login(document.getElementById('login-identifier').value, document.getElementById('login-password').value);
                    this.updateHeaderUI();
                    this.showRolePortal(r.user.role);
                } catch (err) { API.toast(err.message, 'error'); }
            },
            async handleRegisterSubmit(e) {
                e.preventDefault();
                const role = document.getElementById('reg-role').value;
                const p = {
                    username: document.getElementById('reg-username').value,
                    email: document.getElementById('reg-email').value,
                    password: document.getElementById('reg-password').value,
                    full_name: document.getElementById('reg-fullname').value,
                    phone: document.getElementById('reg-phone').value,
                    department: document.getElementById('reg-dept').value,
                    role: role,
                    roll_number: document.getElementById('reg-roll').value,
                    year_of_study: document.getElementById('reg-year').value,
                    organization_unit: document.getElementById('reg-orgunit').value
                };
                try {
                    const r = await API.post('/api/auth/register', p);
                    API.user = r.user;
                    this.updateHeaderUI();
                    this.showRolePortal(r.user.role);
                } catch (err) { API.toast(err.message, 'error'); }
            },
            async triggerDemoLogin(role) {
                const r = await API.demoLogin(role);
                this.updateHeaderUI();
                this.showRolePortal(r.user.role);
            },
            async handleLogout() {
                await API.logout();
                this.updateHeaderUI();
                this.showView('public-home');
                await this.loadPublicEvents();
            },
            switchStudentSection(s) {
                ['dashboard', 'browse', 'registrations', 'certificates', 'profile'].forEach(x => {
                    const el = document.getElementById(`student-sec-${x}`);
                    const n = document.getElementById(`student-nav-${x}`);
                    if (el) el.classList.toggle('hidden', x !== s);
                    if (n) n.classList.toggle('active', x === s);
                });
                if (s === 'dashboard') this.loadStudentDash();
                else if (s === 'browse') this.loadStudentBrowse();
                else if (s === 'registrations') this.loadStudentRegs();
                else if (s === 'certificates') this.loadStudentCerts();
            },
            async loadStudentDash() {
                const r = await API.get('/api/student/dashboard');
                if (r.success) {
                    document.getElementById('st-dash-total-reg').textContent = r.stats.total_registered;
                    document.getElementById('st-dash-approved').textContent = r.stats.approved_count;
                    document.getElementById('st-dash-attended').textContent = r.stats.attended_count;
                    document.getElementById('st-dash-certs').textContent = r.stats.certificates_count;
                    document.getElementById('st-dash-upcoming-list').innerHTML = r.upcoming_events.map(e => `
                        <div class="flex justify-between items-center p-3 bg-slate-50 rounded-xl text-xs">
                            <span class="font-bold">${e.title}</span>
                            <span class="px-2 py-0.5 rounded-full font-bold ${e.registration_status === 'approved' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${e.registration_status.toUpperCase()}</span>
                        </div>
                    `).join('') || '<p class="text-xs text-slate-400">No registered upcoming events.</p>';
                    document.getElementById('st-dash-certs-list').innerHTML = r.recent_certificates.map(c => `
                        <div class="flex justify-between items-center p-3 bg-amber-50 rounded-xl text-xs">
                            <span class="font-bold">${c.event_title}</span>
                            <button onclick="CertificateEngine.openPreview(${c.id})" class="px-2 py-1 bg-amber-600 text-white font-bold rounded-lg">View</button>
                        </div>
                    `).join('') || '<p class="text-xs text-slate-400">No certificates yet.</p>';
                }
            },
            async loadStudentBrowse() {
                const res = await API.get('/api/events');
                if (res.success) {
                    document.getElementById('student-events-grid').innerHTML = res.events.map(ev => `
                        <div class="bg-white p-4 rounded-2xl border flex flex-col justify-between">
                            <div><h4 class="font-bold text-sm">${ev.title}</h4><p class="text-xs text-slate-500 mb-3">${ev.event_date} • ${ev.venue}</p></div>
                            <button onclick="App.openEventModal(${ev.id})" class="px-3 py-1.5 bg-indigo-600 text-white font-bold text-xs rounded-xl">Details & Register</button>
                        </div>
                    `).join('');
                }
            },
            async loadStudentRegs() {
                const r = await API.get('/api/student/my-registrations');
                if (r.success) {
                    document.getElementById('student-registrations-tbody').innerHTML = r.registrations.map(reg => `
                        <tr class="border-b p-3"><td class="p-3 font-bold">${reg.event_title}</td><td class="p-3">${reg.event_date}</td><td class="p-3"><span class="px-2 py-0.5 rounded-full font-bold ${reg.registration_status === 'approved' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${reg.registration_status.toUpperCase()}</span></td><td class="p-3 text-right">${reg.certificate_id ? `<button onclick="CertificateEngine.openPreview(${reg.certificate_id})" class="px-2 py-1 bg-amber-100 text-amber-900 font-bold rounded-lg">View Cert</button>` : '—'}</td></tr>
                    `).join('');
                }
            },
            async loadStudentCerts() {
                const r = await API.get('/api/student/my-certificates');
                if (r.success) {
                    document.getElementById('student-certificates-grid').innerHTML = r.certificates.map(c => `
                        <div class="bg-amber-50/60 p-5 rounded-2xl border border-amber-200 flex flex-col justify-between">
                            <div><span class="px-2 py-0.5 bg-amber-200 text-amber-900 text-xs font-bold rounded-full">${c.certificate_type}</span><h3 class="font-bold text-base mt-2">${c.event_title}</h3><p class="text-xs text-slate-500 mb-4">Code: ${c.certificate_code}</p></div>
                            <button onclick="CertificateEngine.openPreview(${c.id})" class="px-4 py-2 bg-amber-600 text-white font-bold text-xs rounded-xl shadow">View & Download</button>
                        </div>
                    `).join('');
                }
            },
            switchOrganizerSection(s) {
                ['dashboard', 'events', 'participants', 'reports'].forEach(x => {
                    const el = document.getElementById(`org-sec-${x}`);
                    const n = document.getElementById(`org-nav-${x}`);
                    if (el) el.classList.toggle('hidden', x !== s);
                    if (n) n.classList.toggle('active', x === s);
                });
                if (s === 'dashboard' || s === 'events') this.loadOrgDash();
                else if (s === 'participants') this.loadOrgParticipants();
                else if (s === 'reports') this.loadOrgReports();
            },
            async loadOrgDash() {
                const r = await API.get('/api/organizer/dashboard');
                if (r.success) {
                    document.getElementById('org-stat-events').textContent = r.stats.events_count;
                    document.getElementById('org-stat-participants').textContent = r.stats.total_participants;
                    document.getElementById('org-stat-attended').textContent = r.stats.total_attended;
                    document.getElementById('org-stat-certs').textContent = r.stats.certificates_issued;
                    document.getElementById('org-dash-events-tbody').innerHTML = r.events.map(e => `
                        <tr class="border-b"><td class="p-3 font-bold">${e.title}</td><td class="p-3">${e.event_date}</td><td class="p-3">${e.total_registrations} registered</td><td class="p-3 text-right"><button onclick="App.openManageParticipants(${e.id})" class="px-2.5 py-1 bg-indigo-50 text-indigo-600 font-bold rounded-lg">Attendance & Certs</button></td></tr>
                    `).join('');
                    document.getElementById('org-events-grid').innerHTML = r.events.map(e => `
                        <div class="bg-white p-5 rounded-2xl border flex flex-col justify-between">
                            <div><h3 class="font-bold text-base">${e.title}</h3><p class="text-xs text-slate-500 mb-3">${e.event_date} • ${e.venue}</p><p class="text-xs font-semibold">${e.total_registrations} participants</p></div>
                            <div class="pt-3 border-t mt-3 flex gap-2"><button onclick="App.openManageParticipants(${e.id})" class="flex-1 py-1.5 bg-indigo-600 text-white font-bold text-xs rounded-xl">Participants</button><button onclick="App.deleteEvent(${e.id})" class="px-3 py-1.5 bg-rose-50 text-rose-600 font-bold text-xs rounded-xl">Delete</button></div>
                        </div>
                    `).join('');
                }
            },
            async openManageParticipants(eid) {
                this.switchOrganizerSection('participants');
                const r = await API.get(`/api/organizer/events/${eid}/participants`);
                if (r.success) {
                    document.getElementById('org-part-event-select').innerHTML = `<option value="${eid}">${r.event.title}</option>`;
                    document.getElementById('org-participants-tbody').innerHTML = r.participants.map(p => `
                        <tr class="border-b"><td class="p-3 font-bold">${p.full_name} (${p.roll_number || 'N/A'})</td><td class="p-3">${p.department || 'N/A'}</td><td class="p-3"><span class="px-2 py-0.5 rounded-full font-bold ${p.registration_status === 'approved' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}">${p.registration_status}</span></td><td class="p-3"><button onclick="App.markAttendance(${eid}, ${p.student_id}, 'present')" class="px-2 py-1 font-bold rounded-lg ${p.attendance_status === 'present' ? 'bg-emerald-600 text-white' : 'bg-slate-100 text-slate-600'}">Present</button> <button onclick="App.markAttendance(${eid}, ${p.student_id}, 'absent')" class="px-2 py-1 font-bold rounded-lg ${p.attendance_status === 'absent' ? 'bg-rose-600 text-white' : 'bg-slate-100 text-slate-600'}">Absent</button></td><td class="p-3 text-right">${p.certificate_id ? `<span class="text-xs font-mono font-bold text-amber-800">${p.certificate_code}</span>` : `<button onclick="App.issueCert(${eid}, ${p.student_id})" class="px-2 py-1 bg-indigo-50 text-indigo-700 font-bold rounded-lg">+ Issue</button>`}</td></tr>
                    `).join('');
                }
            },
            async markAttendance(eid, sid, st) {
                await API.post('/api/organizer/attendance/mark', { event_id: eid, student_id: sid, status: st });
                this.openManageParticipants(eid);
            },
            async issueCert(eid, sid) {
                const t = prompt('Certificate Type (Participation, Merit):', 'Participation');
                if (!t) return;
                await API.post('/api/organizer/certificates/issue', { event_id: eid, student_id: sid, certificate_type: t });
                this.openManageParticipants(eid);
            },
            async bulkIssueCertificates() {
                const eid = document.getElementById('org-part-event-select').value;
                if (!confirm('Issue certificates to all attendees marked present?')) return;
                await API.post('/api/organizer/certificates/bulk-issue', { event_id: parseInt(eid) });
                this.openManageParticipants(eid);
            },
            async loadOrgReports() {
                const r = await API.get('/api/admin/reports/summary');
                if (r.success) {
                    document.getElementById('org-reports-tbody').innerHTML = r.events_report.map(e => `
                        <tr class="border-b"><td class="p-3 font-bold">${e.title}</td><td class="p-3">${e.event_date}</td><td class="p-3">${e.total_registered}</td><td class="p-3 text-emerald-600 font-bold">${e.present_count || 0}</td><td class="p-3">${e.certificates_issued}</td><td class="p-3 text-right"><a href="/api/admin/reports/export-csv" class="px-2.5 py-1 bg-indigo-50 text-indigo-600 font-bold rounded-lg">CSV</a></td></tr>
                    `).join('');
                }
            },
            switchAdminSection(s) {
                ['dashboard', 'events', 'registrations', 'students', 'organizers', 'reports'].forEach(x => {
                    const el = document.getElementById(`admin-sec-${x}`);
                    const n = document.getElementById(`admin-nav-${x}`);
                    if (el) el.classList.toggle('hidden', x !== s);
                    if (n) n.classList.toggle('active', x === s);
                });
                if (s === 'dashboard') this.loadAdminDash();
                else if (s === 'events') this.loadAdminEvents();
                else if (s === 'registrations') this.loadAdminRegs();
                else if (s === 'students') this.loadAdminStudents();
                else if (s === 'organizers') this.loadAdminOrgs();
                else if (s === 'reports') this.loadAdminReports();
            },
            async loadAdminDash() {
                const r = await API.get('/api/admin/dashboard');
                if (r.success) {
                    document.getElementById('adm-stat-students').textContent = r.stats.total_students;
                    document.getElementById('adm-stat-events').textContent = r.stats.total_events;
                    document.getElementById('adm-stat-registrations').textContent = r.stats.total_registrations;
                    document.getElementById('adm-stat-pending-regs').textContent = r.stats.pending_registrations;
                    document.getElementById('adm-stat-approved-regs').textContent = r.stats.approved_registrations;
                    document.getElementById('adm-stat-certs').textContent = r.stats.certificates_issued;
                    document.getElementById('adm-dash-activities').innerHTML = r.recent_activities.map(a => `
                        <div class="p-2.5 bg-slate-50 rounded-xl text-xs flex justify-between"><span class="font-semibold">${a.description}</span><span class="text-slate-400">${a.created_at}</span></div>
                    `).join('');
                    this.renderAdminCharts(r.category_stats, r.stats);
                }
            },
            renderAdminCharts(cat, st) {
                const c1 = document.getElementById('admin-chart-categories');
                if (c1) {
                    if (this.charts.cat) this.charts.cat.destroy();
                    this.charts.cat = new Chart(c1, {
                        type: 'doughnut',
                        data: { labels: cat.map(x => x.category), datasets: [{ data: cat.map(x => x.count), backgroundColor: ['#6366f1', '#ec4899', '#f59e0b', '#10b981', '#3b82f6'] }] },
                        options: { responsive: true, maintainAspectRatio: false }
                    });
                }
                const c2 = document.getElementById('admin-chart-registrations');
                if (c2) {
                    if (this.charts.reg) this.charts.reg.destroy();
                    this.charts.reg = new Chart(c2, {
                        type: 'bar',
                        data: { labels: ['Pending', 'Approved', 'Attended', 'Rejected'], datasets: [{ data: [st.pending_registrations, st.approved_registrations, st.attended_registrations, st.rejected_registrations], backgroundColor: ['#f59e0b', '#10b981', '#8b5cf6', '#ef4444'] }] },
                        options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
                    });
                }
            },
            async loadAdminEvents() {
                const r = await API.get('/api/events');
                if (r.success) {
                    document.getElementById('admin-events-tbody').innerHTML = r.events.map(e => `
                        <tr class="border-b"><td class="p-3 font-bold">${e.title}</td><td class="p-3">${e.category}</td><td class="p-3">${e.event_date}</td><td class="p-3">${e.total_registered} / ${e.max_participants}</td><td class="p-3 text-right"><button onclick="App.deleteEvent(${e.id})" class="text-rose-600 font-bold"><i class="fa-solid fa-trash"></i></button></td></tr>
                    `).join('');
                }
            },
            async loadAdminRegs() {
                const r = await API.get('/api/admin/registrations');
                if (r.success) {
                    document.getElementById('admin-registrations-tbody').innerHTML = r.registrations.map(reg => `
                        <tr class="border-b"><td class="p-3 font-bold">${reg.student_name}</td><td class="p-3">${reg.event_title}</td><td class="p-3">${reg.status.toUpperCase()}</td><td class="p-3 text-right"><button onclick="App.approveReg(${reg.id}, 'approved')" class="px-2 py-1 bg-emerald-100 text-emerald-800 font-bold rounded-lg">Approve</button> <button onclick="App.approveReg(${reg.id}, 'rejected')" class="px-2 py-1 bg-rose-100 text-rose-800 font-bold rounded-lg">Reject</button></td></tr>
                    `).join('');
                }
            },
            async approveReg(rid, st) {
                await API.put(`/api/admin/registrations/${rid}/status`, { status: st });
                this.loadAdminRegs();
            },
            async loadAdminStudents() {
                const r = await API.get('/api/admin/students');
                if (r.success) {
                    document.getElementById('admin-students-tbody').innerHTML = r.students.map(s => `
                        <tr class="border-b"><td class="p-3 font-bold">${s.full_name} (${s.roll_number || 'N/A'})</td><td class="p-3">${s.department || 'N/A'}</td><td class="p-3">${s.registered_events_count} events</td><td class="p-3 text-right"><button onclick="App.deleteStudent(${s.id})" class="text-rose-600 font-bold"><i class="fa-solid fa-trash"></i></button></td></tr>
                    `).join('');
                }
            },
            async deleteStudent(sid) {
                if (!confirm('Delete student?')) return;
                await API.delete(`/api/admin/students/${sid}`);
                this.loadAdminStudents();
            },
            async loadAdminOrgs() {
                const r = await API.get('/api/admin/organizers');
                if (r.success) {
                    document.getElementById('admin-organizers-tbody').innerHTML = r.organizers.map(o => `
                        <tr class="border-b"><td class="p-3 font-bold">${o.full_name}</td><td class="p-3">${o.organization_unit || 'N/A'}</td><td class="p-3">${o.events_count} events</td><td class="p-3 text-right"><button onclick="App.deleteOrg(${o.id})" class="text-rose-600 font-bold"><i class="fa-solid fa-trash"></i></button></td></tr>
                    `).join('');
                }
            },
            async deleteOrg(oid) {
                if (!confirm('Delete organizer?')) return;
                await API.delete(`/api/admin/organizers/${oid}`);
                this.loadAdminOrgs();
            },
            async loadAdminReports() {
                const r = await API.get('/api/admin/reports/summary');
                if (r.success) {
                    document.getElementById('admin-reports-tbody').innerHTML = r.events_report.map(e => `
                        <tr class="border-b"><td class="p-3 font-bold">${e.title}</td><td class="p-3">${e.category}</td><td class="p-3">${e.total_registered}</td><td class="p-3">${e.present_count || 0}</td><td class="p-3">${e.certificates_issued}</td><td class="p-3 text-right"><a href="/api/admin/reports/export-csv" class="px-2 py-1 bg-indigo-50 text-indigo-700 font-bold rounded-lg">CSV</a></td></tr>
                    `).join('');
                }
            },
            openCreateEventModal() {
                document.getElementById('create-event-modal').classList.remove('hidden');
                document.getElementById('create-event-modal').classList.add('flex');
            },
            closeCreateEventModal() {
                document.getElementById('create-event-modal').classList.add('hidden');
                document.getElementById('create-event-modal').classList.remove('flex');
            },
            async handleSaveEvent(e) {
                e.preventDefault();
                const p = {
                    title: document.getElementById('event-form-title').value,
                    category: document.getElementById('event-form-category').value,
                    max_participants: parseInt(document.getElementById('event-form-capacity').value),
                    event_date: document.getElementById('event-form-date').value,
                    start_time: document.getElementById('event-form-start').value,
                    end_time: document.getElementById('event-form-end').value,
                    venue: document.getElementById('event-form-venue').value,
                    registration_deadline: document.getElementById('event-form-deadline').value.replace('T', ' ') + ':00',
                    description: document.getElementById('event-form-desc').value
                };
                await API.post('/api/organizer/events', p);
                this.closeCreateEventModal();
                if (API.user.role === 'admin') this.loadAdminEvents();
                else this.loadOrgDash();
            },
            openAddStudentModal() {
                document.getElementById('student-manage-modal').classList.remove('hidden');
                document.getElementById('student-manage-modal').classList.add('flex');
            },
            closeStudentManageModal() {
                document.getElementById('student-manage-modal').classList.add('hidden');
                document.getElementById('student-manage-modal').classList.remove('flex');
            },
            async handleSaveStudent(e) {
                e.preventDefault();
                await API.post('/api/admin/students', {
                    username: document.getElementById('stm-username').value,
                    email: document.getElementById('stm-email').value,
                    full_name: document.getElementById('stm-name').value,
                    roll_number: document.getElementById('stm-roll').value,
                    department: document.getElementById('stm-dept').value
                });
                this.closeStudentManageModal();
                this.loadAdminStudents();
            },
            openAddOrganizerModal() {
                document.getElementById('organizer-manage-modal').classList.remove('hidden');
                document.getElementById('organizer-manage-modal').classList.add('flex');
            },
            closeOrganizerManageModal() {
                document.getElementById('organizer-manage-modal').classList.add('hidden');
                document.getElementById('organizer-manage-modal').classList.remove('flex');
            },
            async handleSaveOrganizer(e) {
                e.preventDefault();
                await API.post('/api/admin/organizers', {
                    username: document.getElementById('ogm-username').value,
                    email: document.getElementById('ogm-email').value,
                    full_name: document.getElementById('ogm-name').value,
                    organization_unit: document.getElementById('ogm-orgunit').value
                });
                this.closeOrganizerManageModal();
                this.loadAdminOrgs();
            },
            openVerifyModal() {
                document.getElementById('verify-cert-modal').classList.remove('hidden');
                document.getElementById('verify-cert-modal').classList.add('flex');
            },
            closeVerifyModal() {
                document.getElementById('verify-cert-modal').classList.add('hidden');
                document.getElementById('verify-cert-modal').classList.remove('flex');
            },
            async handleVerifyCertificate(e) {
                e.preventDefault();
                const code = document.getElementById('verify-code-input').value.trim();
                const resBox = document.getElementById('verify-cert-result');
                try {
                    const r = await API.get(`/api/certificates/verify/${encodeURIComponent(code)}`);
                    resBox.classList.remove('hidden');
                    resBox.innerHTML = `<div class="p-3 bg-emerald-50 text-emerald-800 rounded-xl text-xs"><p class="font-bold">✓ Official Certificate Verified</p><p class="mt-1">Issued to: <b>${r.certificate.student_name}</b> for event <b>${r.certificate.event_title}</b> on ${r.certificate.issue_date}.</p></div>`;
                } catch (err) {
                    resBox.classList.remove('hidden');
                    resBox.innerHTML = `<div class="p-3 bg-rose-50 text-rose-800 rounded-xl text-xs font-semibold">✗ Invalid Certificate Code.</div>`;
                }
            }
        };

        document.addEventListener('DOMContentLoaded', () => App.init());
    </script>
</body>
</html>
"""

# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '0.0.0.0')
    print("=" * 65)
    print("  COLLEGE EVENT MANAGEMENT SYSTEM (CEMS)")
    print("  Single-File Standalone Edition")
    print("=" * 65)
    print(f"[*] Server starting on http://localhost:{port}")
    print(f"[*] Available on network: http://{host}:{port}")
    print("\n[+] DEMO CREDENTIALS:")
    print("    1. Admin:     admin / admin123")
    print("    2. Organizer: organizer / org123")
    print("    3. Student:   student / student123")
    print("=" * 65)
    app.run(host=host, port=port, debug=False)
