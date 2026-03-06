from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, os, json
from datetime import datetime, date, timedelta
from functools import wraps
import hashlib, random

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "flowlife_dev_secret")

DB = "flowlife.db"

# ── DATABASE ────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def rows_to_dicts(rows):
    return [dict(r) for r in rows]

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT,
        avatar_color TEXT DEFAULT '#6366f1',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS goals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        category TEXT DEFAULT 'Personal',
        priority TEXT DEFAULT 'medium',
        status TEXT DEFAULT 'active',
        due_date TEXT,
        progress INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        goal_id INTEGER,
        title TEXT NOT NULL,
        description TEXT,
        priority TEXT DEFAULT 'medium',
        status TEXT DEFAULT 'pending',
        due_date TEXT,
        completed_at TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        frequency TEXT DEFAULT 'daily',
        color TEXT DEFAULT '#6366f1',
        icon TEXT DEFAULT '⭐',
        current_streak INTEGER DEFAULT 0,
        longest_streak INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS habit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        logged_date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(habit_id, logged_date)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS budget_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        budget_limit REAL DEFAULT 0,
        color TEXT DEFAULT '#6366f1',
        icon TEXT DEFAULT '💰'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER,
        type TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT,
        transaction_date TEXT DEFAULT CURRENT_DATE,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS mood_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        mood INTEGER NOT NULL,
        energy INTEGER NOT NULL,
        note TEXT,
        logged_date TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, logged_date)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        badge_key TEXT NOT NULL,
        earned_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, badge_key)
    )''')

    conn.commit()
    conn.close()

# ── AUTH ────────────────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── ACHIEVEMENT ENGINE ──────────────────────────────────────────────────
BADGES = {
    'first_task':      {'name': 'First Step',       'icon': '🎯', 'desc': 'Completed your first task'},
    'task_10':         {'name': 'On a Roll',         'icon': '🔥', 'desc': 'Completed 10 tasks'},
    'task_50':         {'name': 'Achiever',          'icon': '⚡', 'desc': 'Completed 50 tasks'},
    'streak_3':        {'name': 'Habit Forming',     'icon': '✨', 'desc': '3-day habit streak'},
    'streak_7':        {'name': 'Week Warrior',      'icon': '🏅', 'desc': '7-day habit streak'},
    'streak_30':       {'name': 'Iron Will',         'icon': '💎', 'desc': '30-day habit streak'},
    'goal_complete':   {'name': 'Goal Getter',       'icon': '🏆', 'desc': 'Completed your first goal'},
    'budget_saver':    {'name': 'Smart Saver',       'icon': '💰', 'desc': 'Stayed under budget for a month'},
    'mood_logger':     {'name': 'Self Aware',        'icon': '🧘', 'desc': 'Logged mood for 7 days'},
    'early_bird':      {'name': 'Early Bird',        'icon': '🌅', 'desc': 'Completed 5 tasks before noon'},
    'planner':         {'name': 'Master Planner',    'icon': '📅', 'desc': 'Created 5 goals'},
    'habit_creator':   {'name': 'Habit Builder',     'icon': '🔄', 'desc': 'Created 5 habits'},
}

def award_badge(user_id, badge_key):
    conn = get_db()
    try:
        conn.execute("INSERT OR IGNORE INTO achievements (user_id, badge_key) VALUES (?,?)",
                     (user_id, badge_key))
        conn.commit()
    except: pass
    finally: conn.close()

def check_achievements(user_id):
    conn = get_db()
    # Tasks completed
    done = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE user_id=? AND status='done'", (user_id,)).fetchone()['c']
    if done >= 1:  award_badge(user_id, 'first_task')
    if done >= 10: award_badge(user_id, 'task_10')
    if done >= 50: award_badge(user_id, 'task_50')
    # Goals
    goals_done = conn.execute("SELECT COUNT(*) as c FROM goals WHERE user_id=? AND status='completed'", (user_id,)).fetchone()['c']
    if goals_done >= 1: award_badge(user_id, 'goal_complete')
    goals_count = conn.execute("SELECT COUNT(*) as c FROM goals WHERE user_id=?", (user_id,)).fetchone()['c']
    if goals_count >= 5: award_badge(user_id, 'planner')
    # Habits
    habits_count = conn.execute("SELECT COUNT(*) as c FROM habits WHERE user_id=?", (user_id,)).fetchone()['c']
    if habits_count >= 5: award_badge(user_id, 'habit_creator')
    # Streaks
    max_streak = conn.execute("SELECT MAX(current_streak) as m FROM habits WHERE user_id=?", (user_id,)).fetchone()['m'] or 0
    if max_streak >= 3:  award_badge(user_id, 'streak_3')
    if max_streak >= 7:  award_badge(user_id, 'streak_7')
    if max_streak >= 30: award_badge(user_id, 'streak_30')
    # Mood logs
    mood_count = conn.execute("SELECT COUNT(*) as c FROM mood_logs WHERE user_id=?", (user_id,)).fetchone()['c']
    if mood_count >= 7: award_badge(user_id, 'mood_logger')
    conn.close()

# ── AI SUGGESTION ENGINE ────────────────────────────────────────────────
def get_ai_suggestions(user_id):
    conn = get_db()
    suggestions = []

    # Overdue tasks
    today = date.today().isoformat()
    overdue = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id=? AND status='pending' AND due_date < ?",
        (user_id, today)).fetchone()['c']
    if overdue > 0:
        suggestions.append({
            'type': 'warning', 'icon': '⚠️',
            'title': f'You have {overdue} overdue task{"s" if overdue>1 else ""}',
            'body': 'Try tackling the smallest one first to build momentum.',
            'action': 'Go to Tasks', 'link': '/tasks'
        })

    # Broken streaks
    broken = conn.execute(
        "SELECT name FROM habits WHERE user_id=? AND current_streak=0", (user_id,)).fetchall()
    if broken:
        suggestions.append({
            'type': 'info', 'icon': '🔄',
            'title': f'Restart your {broken[0]["name"]} habit',
            'body': 'Consistency beats intensity. Even 2 minutes counts today.',
            'action': 'Track Habits', 'link': '/habits'
        })

    # Low mood
    recent_mood = conn.execute(
        "SELECT AVG(mood) as avg FROM mood_logs WHERE user_id=? AND logged_date >= date('now','-3 days')",
        (user_id,)).fetchone()['avg']
    if recent_mood and recent_mood < 3:
        suggestions.append({
            'type': 'care', 'icon': '💙',
            'title': "Your mood has been low lately",
            'body': 'Consider a short walk, hydration, or breaking tasks into smaller steps.',
            'action': 'Log Mood', 'link': '/mood'
        })

    # Budget overspending
    month = date.today().strftime('%Y-%m')
    spending = conn.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE user_id=? AND type='expense' AND strftime('%Y-%m',transaction_date)=?",
        (user_id, month)).fetchone()['s']
    income = conn.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE user_id=? AND type='income' AND strftime('%Y-%m',transaction_date)=?",
        (user_id, month)).fetchone()['s']
    if income > 0 and spending > income * 0.9:
        suggestions.append({
            'type': 'warning', 'icon': '💸',
            'title': 'Spending is close to your income',
            'body': f'You\'ve spent ₱{spending:,.0f} of ₱{income:,.0f} this month. Consider reviewing expenses.',
            'action': 'View Budget', 'link': '/budget'
        })

    # Positive reinforcement
    streaks = conn.execute(
        "SELECT name, current_streak FROM habits WHERE user_id=? AND current_streak >= 7 LIMIT 1",
        (user_id,)).fetchone()
    if streaks:
        suggestions.append({
            'type': 'success', 'icon': '🔥',
            'title': f'{streaks["current_streak"]}-day streak on "{streaks["name"]}"!',
            'body': 'Incredible consistency! You\'re building a lasting habit.',
            'action': None, 'link': None
        })

    # No mood today
    today_mood = conn.execute(
        "SELECT id FROM mood_logs WHERE user_id=? AND logged_date=?", (user_id, today)).fetchone()
    if not today_mood:
        suggestions.append({
            'type': 'info', 'icon': '🧘',
            'title': "How are you feeling today?",
            'body': 'Tracking your mood takes 10 seconds and reveals powerful patterns over time.',
            'action': 'Log Mood', 'link': '/mood'
        })

    conn.close()
    return suggestions[:4]  # max 4 suggestions

# ── GOAL TASK TEMPLATE ENGINE ───────────────────────────────────────────
GOAL_TEMPLATES = {
    'fitness': ['Set a weekly workout schedule', 'Research nutrition basics', 'Track workouts for 1 week',
                'Find an accountability partner', 'Measure progress monthly'],
    'learn':   ['Define what success looks like', 'Find 3 learning resources', 'Schedule daily study time',
                'Complete first lesson/chapter', 'Practice with a real project', 'Review and test yourself'],
    'finance': ['List all income sources', 'Track all expenses for 1 week', 'Set a monthly savings target',
                'Cut one unnecessary subscription', 'Set up automatic savings'],
    'career':  ['Update your resume/CV', 'Identify 3 target companies', 'Polish your LinkedIn profile',
                'Reach out to 2 contacts', 'Prepare for interviews'],
    'health':  ['Book a health checkup', 'Plan weekly meals', 'Set a sleep schedule',
                'Drink 8 glasses of water daily', 'Walk 30 minutes daily'],
    'default': ['Define the goal clearly', 'Break it into milestones', 'Set a deadline',
                'Identify obstacles', 'Take the first small step today'],
}

def generate_tasks_for_goal(title, description=''):
    text = (title + ' ' + (description or '')).lower()
    if any(w in text for w in ['fit','gym','workout','exercise','run','weight']):
        return GOAL_TEMPLATES['fitness']
    if any(w in text for w in ['learn','study','course','skill','book','read']):
        return GOAL_TEMPLATES['learn']
    if any(w in text for w in ['money','save','invest','budget','finance','debt']):
        return GOAL_TEMPLATES['finance']
    if any(w in text for w in ['job','career','work','promotion','resume','business']):
        return GOAL_TEMPLATES['career']
    if any(w in text for w in ['health','diet','sleep','mental','stress','meditat']):
        return GOAL_TEMPLATES['health']
    return GOAL_TEMPLATES['default']

# ── STREAK CALCULATOR ───────────────────────────────────────────────────
def recalc_streak(habit_id, user_id):
    conn = get_db()
    logs = conn.execute(
        "SELECT logged_date FROM habit_logs WHERE habit_id=? ORDER BY logged_date DESC",
        (habit_id,)).fetchall()
    dates = [l['logged_date'] for l in logs]

    streak = 0
    check = date.today()
    for d in dates:
        if d == check.isoformat():
            streak += 1
            check -= timedelta(days=1)
        elif d == (check - timedelta(days=1)).isoformat():
            check -= timedelta(days=1)
            streak += 1
            check -= timedelta(days=1)
        else:
            break

    longest = conn.execute("SELECT longest_streak FROM habits WHERE id=?", (habit_id,)).fetchone()['longest_streak']
    new_longest = max(longest, streak)
    conn.execute("UPDATE habits SET current_streak=?, longest_streak=? WHERE id=?",
                 (streak, new_longest, habit_id))
    conn.commit()
    conn.close()
    return streak

# ════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ════════════════════════════════════════════════════════════════════════
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = hash_pw(request.form['password'])
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE (username=? OR email=?) AND password=?",
                            (username, username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name'] or user['username']
            session['avatar_color'] = user['avatar_color']
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username  = request.form['username'].strip()
        email     = request.form['email'].strip()
        full_name = request.form['full_name'].strip()
        password  = hash_pw(request.form['password'])
        colors = ['#6366f1','#ec4899','#f59e0b','#10b981','#3b82f6','#8b5cf6','#ef4444']
        color = random.choice(colors)
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username,email,full_name,password,avatar_color) VALUES (?,?,?,?,?)",
                         (username, email, full_name, password, color))
            conn.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
        except:
            flash('Username or email already exists.', 'error')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════════════
@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    conn = get_db()
    today = date.today().isoformat()
    month = date.today().strftime('%Y-%m')

    # Summary stats
    tasks_today = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id=? AND due_date=? AND status='pending'", (uid, today)).fetchone()['c']
    tasks_done  = conn.execute(
        "SELECT COUNT(*) as c FROM tasks WHERE user_id=? AND status='done'", (uid,)).fetchone()['c']
    active_goals = conn.execute(
        "SELECT COUNT(*) as c FROM goals WHERE user_id=? AND status='active'", (uid,)).fetchone()['c']
    habits_today = conn.execute(
        "SELECT COUNT(*) as c FROM habit_logs WHERE user_id=? AND logged_date=?", (uid, today)).fetchone()['c']
    total_habits = conn.execute(
        "SELECT COUNT(*) as c FROM habits WHERE user_id=?", (uid,)).fetchone()['c']

    # Budget this month
    income   = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE user_id=? AND type='income' AND strftime('%Y-%m',transaction_date)=?", (uid, month)).fetchone()['s']
    spending = conn.execute("SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE user_id=? AND type='expense' AND strftime('%Y-%m',transaction_date)=?", (uid, month)).fetchone()['s']

    # Today's mood
    today_mood = conn.execute("SELECT mood, energy FROM mood_logs WHERE user_id=? AND logged_date=?", (uid, today)).fetchone()

    # Recent tasks
    recent_tasks = conn.execute(
        "SELECT * FROM tasks WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (uid,)).fetchall()

    # Top habits with streak
    top_habits = conn.execute(
        "SELECT h.*, CASE WHEN hl.id IS NOT NULL THEN 1 ELSE 0 END as done_today FROM habits h LEFT JOIN habit_logs hl ON h.id=hl.habit_id AND hl.logged_date=? WHERE h.user_id=? ORDER BY h.current_streak DESC LIMIT 5",
        (today, uid)).fetchall()

    # Weekly mood chart (last 7 days)
    mood_week = conn.execute(
        "SELECT logged_date, mood, energy FROM mood_logs WHERE user_id=? AND logged_date >= date('now','-6 days') ORDER BY logged_date ASC",
        (uid,)).fetchall()

    # Achievements count
    badge_count = conn.execute("SELECT COUNT(*) as c FROM achievements WHERE user_id=?", (uid,)).fetchone()['c']

    conn.close()
    check_achievements(uid)
    suggestions = get_ai_suggestions(uid)

    now_hour = datetime.now().hour
    return render_template('dashboard.html',
        now_hour=now_hour,
        tasks_today=tasks_today, tasks_done=tasks_done,
        active_goals=active_goals, habits_today=habits_today,
        total_habits=total_habits, income=income, spending=spending,
        today_mood=today_mood, recent_tasks=recent_tasks,
        top_habits=top_habits, mood_week=rows_to_dicts(mood_week),
        badge_count=badge_count, suggestions=suggestions, today=today)

# ════════════════════════════════════════════════════════════════════════
# GOALS & TASKS
# ════════════════════════════════════════════════════════════════════════
@app.route('/goals')
@login_required
def goals():
    uid = session['user_id']
    conn = get_db()
    goals_list = conn.execute(
        "SELECT g.*, (SELECT COUNT(*) FROM tasks WHERE goal_id=g.id AND status='done') as done_tasks, (SELECT COUNT(*) FROM tasks WHERE goal_id=g.id) as total_tasks FROM goals g WHERE g.user_id=? ORDER BY g.created_at DESC",
        (uid,)).fetchall()
    conn.close()
    return render_template('goals.html', goals=goals_list)

@app.route('/goals/add', methods=['POST'])
@login_required
def add_goal():
    uid = session['user_id']
    title    = request.form['title'].strip()
    desc     = request.form.get('description','').strip()
    category = request.form.get('category','Personal')
    priority = request.form.get('priority','medium')
    due_date = request.form.get('due_date','') or None
    auto_tasks = request.form.get('auto_tasks') == '1'

    conn = get_db()
    cur = conn.execute(
        "INSERT INTO goals (user_id,title,description,category,priority,due_date) VALUES (?,?,?,?,?,?)",
        (uid, title, desc, category, priority, due_date))
    goal_id = cur.lastrowid

    if auto_tasks:
        templates = generate_tasks_for_goal(title, desc)
        for t in templates:
            conn.execute("INSERT INTO tasks (user_id,goal_id,title,priority) VALUES (?,?,?,?)",
                         (uid, goal_id, t, priority))

    conn.commit()
    conn.close()
    check_achievements(uid)
    flash(f'Goal "{title}" created{"with AI-generated tasks" if auto_tasks else ""}!', 'success')
    return redirect(url_for('goals'))

@app.route('/goals/<int:gid>/complete', methods=['POST'])
@login_required
def complete_goal(gid):
    uid = session['user_id']
    conn = get_db()
    conn.execute("UPDATE goals SET status='completed', progress=100 WHERE id=? AND user_id=?", (gid, uid))
    conn.commit()
    conn.close()
    check_achievements(uid)
    flash('Goal marked as completed! 🏆', 'success')
    return redirect(url_for('goals'))

@app.route('/goals/<int:gid>/delete', methods=['POST'])
@login_required
def delete_goal(gid):
    uid = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM goals WHERE id=? AND user_id=?", (gid, uid))
    conn.execute("DELETE FROM tasks WHERE goal_id=? AND user_id=?", (gid, uid))
    conn.commit()
    conn.close()
    return redirect(url_for('goals'))

@app.route('/tasks')
@login_required
def tasks():
    uid = session['user_id']
    filter_status = request.args.get('status','all')
    conn = get_db()
    q = "SELECT t.*, g.title as goal_title FROM tasks t LEFT JOIN goals g ON t.goal_id=g.id WHERE t.user_id=?"
    params = [uid]
    if filter_status != 'all':
        q += " AND t.status=?"
        params.append(filter_status)
    q += " ORDER BY CASE t.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, t.due_date ASC"
    tasks_list = conn.execute(q, params).fetchall()
    goals_list = conn.execute("SELECT id, title FROM goals WHERE user_id=? AND status='active'", (uid,)).fetchall()
    conn.close()
    return render_template('tasks.html', tasks=tasks_list, goals=goals_list, filter_status=filter_status)

@app.route('/tasks/add', methods=['POST'])
@login_required
def add_task():
    uid = session['user_id']
    conn = get_db()
    conn.execute("INSERT INTO tasks (user_id,goal_id,title,description,priority,due_date) VALUES (?,?,?,?,?,?)",
        (uid, request.form.get('goal_id') or None, request.form['title'].strip(),
         request.form.get('description','').strip(), request.form.get('priority','medium'),
         request.form.get('due_date','') or None))
    conn.commit()
    conn.close()
    flash('Task added!', 'success')
    return redirect(url_for('tasks'))

@app.route('/tasks/<int:tid>/done', methods=['POST'])
@login_required
def complete_task(tid):
    uid = session['user_id']
    conn = get_db()
    conn.execute("UPDATE tasks SET status='done', completed_at=? WHERE id=? AND user_id=?",
                 (datetime.now().isoformat(), tid, uid))
    # Update goal progress
    task = conn.execute("SELECT goal_id FROM tasks WHERE id=?", (tid,)).fetchone()
    if task and task['goal_id']:
        gid = task['goal_id']
        total = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE goal_id=?", (gid,)).fetchone()['c']
        done  = conn.execute("SELECT COUNT(*) as c FROM tasks WHERE goal_id=? AND status='done'", (gid,)).fetchone()['c']
        progress = int((done/total)*100) if total > 0 else 0
        conn.execute("UPDATE goals SET progress=? WHERE id=?", (progress, gid))
    conn.commit()
    conn.close()
    check_achievements(uid)
    return jsonify({'ok': True})

@app.route('/tasks/<int:tid>/delete', methods=['POST'])
@login_required
def delete_task(tid):
    uid = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (tid, uid))
    conn.commit()
    conn.close()
    return redirect(url_for('tasks'))

# ════════════════════════════════════════════════════════════════════════
# HABITS
# ════════════════════════════════════════════════════════════════════════
@app.route('/habits')
@login_required
def habits():
    uid = session['user_id']
    today = date.today().isoformat()
    conn = get_db()
    habits_list = conn.execute(
        "SELECT h.*, CASE WHEN hl.id IS NOT NULL THEN 1 ELSE 0 END as done_today FROM habits h LEFT JOIN habit_logs hl ON h.id=hl.habit_id AND hl.logged_date=? WHERE h.user_id=? ORDER BY h.current_streak DESC",
        (today, uid)).fetchall()
    # Last 7 days log for each habit
    week_logs = conn.execute(
        "SELECT habit_id, logged_date FROM habit_logs WHERE user_id=? AND logged_date >= date('now','-6 days')",
        (uid,)).fetchall()
    week_map = {}
    for l in week_logs:
        week_map.setdefault(l['habit_id'], set()).add(l['logged_date'])
    conn.close()

    # Build 7-day grid
    days = [(date.today() - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    return render_template('habits.html', habits=habits_list, days=days, week_map=week_map, today=today)

@app.route('/habits/add', methods=['POST'])
@login_required
def add_habit():
    uid = session['user_id']
    conn = get_db()
    conn.execute("INSERT INTO habits (user_id,name,description,frequency,color,icon) VALUES (?,?,?,?,?,?)",
        (uid, request.form['name'].strip(), request.form.get('description','').strip(),
         request.form.get('frequency','daily'), request.form.get('color','#6366f1'),
         request.form.get('icon','⭐')))
    conn.commit()
    conn.close()
    check_achievements(uid)
    flash('Habit created!', 'success')
    return redirect(url_for('habits'))

@app.route('/habits/<int:hid>/log', methods=['POST'])
@login_required
def log_habit(hid):
    uid = session['user_id']
    today = date.today().isoformat()
    conn = get_db()
    try:
        conn.execute("INSERT INTO habit_logs (habit_id,user_id,logged_date) VALUES (?,?,?)", (hid, uid, today))
        conn.commit()
    except: pass
    finally: conn.close()
    streak = recalc_streak(hid, uid)
    check_achievements(uid)
    return jsonify({'ok': True, 'streak': streak})

@app.route('/habits/<int:hid>/unlog', methods=['POST'])
@login_required
def unlog_habit(hid):
    uid = session['user_id']
    today = date.today().isoformat()
    conn = get_db()
    conn.execute("DELETE FROM habit_logs WHERE habit_id=? AND user_id=? AND logged_date=?", (hid, uid, today))
    conn.commit()
    conn.close()
    recalc_streak(hid, uid)
    return jsonify({'ok': True})

@app.route('/habits/<int:hid>/delete', methods=['POST'])
@login_required
def delete_habit(hid):
    uid = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM habits WHERE id=? AND user_id=?", (hid, uid))
    conn.execute("DELETE FROM habit_logs WHERE habit_id=? AND user_id=?", (hid, uid))
    conn.commit()
    conn.close()
    return redirect(url_for('habits'))

# ════════════════════════════════════════════════════════════════════════
# BUDGET
# ════════════════════════════════════════════════════════════════════════
@app.route('/budget')
@login_required
def budget():
    uid = session['user_id']
    month = request.args.get('month', date.today().strftime('%Y-%m'))
    conn = get_db()
    cats = conn.execute("SELECT * FROM budget_categories WHERE user_id=?", (uid,)).fetchall()
    income = conn.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE user_id=? AND type='income' AND strftime('%Y-%m',transaction_date)=?",
        (uid, month)).fetchone()['s']
    spending = conn.execute(
        "SELECT COALESCE(SUM(amount),0) as s FROM transactions WHERE user_id=? AND type='expense' AND strftime('%Y-%m',transaction_date)=?",
        (uid, month)).fetchone()['s']
    txns = conn.execute(
        "SELECT t.*, bc.name as cat_name, bc.icon as cat_icon FROM transactions t LEFT JOIN budget_categories bc ON t.category_id=bc.id WHERE t.user_id=? AND strftime('%Y-%m',t.transaction_date)=? ORDER BY t.transaction_date DESC, t.created_at DESC",
        (uid, month)).fetchall()
    by_cat = conn.execute(
        "SELECT bc.name, bc.icon, bc.color, bc.budget_limit, COALESCE(SUM(t.amount),0) as spent FROM budget_categories bc LEFT JOIN transactions t ON bc.id=t.category_id AND t.type='expense' AND strftime('%Y-%m',t.transaction_date)=? WHERE bc.user_id=? GROUP BY bc.id",
        (month, uid)).fetchall()
    # Monthly trend (last 6 months)
    trend = conn.execute(
        "SELECT strftime('%Y-%m',transaction_date) as mo, type, COALESCE(SUM(amount),0) as total FROM transactions WHERE user_id=? AND transaction_date >= date('now','-5 months','start of month') GROUP BY mo, type ORDER BY mo ASC",
        (uid,)).fetchall()
    conn.close()
    return render_template('budget.html', cats=cats, income=income, spending=spending,
        transactions=txns, by_cat=by_cat, trend=rows_to_dicts(trend), month=month)

@app.route('/budget/add-category', methods=['POST'])
@login_required
def add_budget_category():
    uid = session['user_id']
    conn = get_db()
    conn.execute("INSERT INTO budget_categories (user_id,name,budget_limit,color,icon) VALUES (?,?,?,?,?)",
        (uid, request.form['name'].strip(), float(request.form.get('budget_limit',0)),
         request.form.get('color','#6366f1'), request.form.get('icon','💰')))
    conn.commit()
    conn.close()
    flash('Category added!', 'success')
    return redirect(url_for('budget'))

@app.route('/budget/add-transaction', methods=['POST'])
@login_required
def add_transaction():
    uid = session['user_id']
    conn = get_db()
    conn.execute("INSERT INTO transactions (user_id,category_id,type,amount,description,transaction_date) VALUES (?,?,?,?,?,?)",
        (uid, request.form.get('category_id') or None, request.form['type'],
         float(request.form['amount']), request.form.get('description','').strip(),
         request.form.get('transaction_date', date.today().isoformat())))
    conn.commit()
    conn.close()
    flash('Transaction added!', 'success')
    return redirect(url_for('budget'))

@app.route('/budget/delete/<int:tid>', methods=['POST'])
@login_required
def delete_transaction(tid):
    uid = session['user_id']
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tid, uid))
    conn.commit()
    conn.close()
    return redirect(url_for('budget'))

# ════════════════════════════════════════════════════════════════════════
# MOOD
# ════════════════════════════════════════════════════════════════════════
@app.route('/mood')
@login_required
def mood():
    uid = session['user_id']
    conn = get_db()
    today = date.today().isoformat()
    today_log = conn.execute("SELECT * FROM mood_logs WHERE user_id=? AND logged_date=?", (uid, today)).fetchone()
    history = conn.execute(
        "SELECT * FROM mood_logs WHERE user_id=? ORDER BY logged_date DESC LIMIT 30", (uid,)).fetchall()
    avg_mood   = conn.execute("SELECT AVG(mood) as a FROM mood_logs WHERE user_id=? AND logged_date >= date('now','-7 days')", (uid,)).fetchone()['a']
    avg_energy = conn.execute("SELECT AVG(energy) as a FROM mood_logs WHERE user_id=? AND logged_date >= date('now','-7 days')", (uid,)).fetchone()['a']
    conn.close()
    check_achievements(uid)
    return render_template('mood.html', today_log=today_log, history=history,
        mood_data=rows_to_dicts(history[:14]), avg_mood=avg_mood, avg_energy=avg_energy, today=today)

@app.route('/mood/log', methods=['POST'])
@login_required
def log_mood():
    uid = session['user_id']
    today = date.today().isoformat()
    conn = get_db()
    conn.execute("""INSERT INTO mood_logs (user_id,mood,energy,note,logged_date)
        VALUES (?,?,?,?,?) ON CONFLICT(user_id,logged_date) DO UPDATE SET mood=?,energy=?,note=?""",
        (uid, int(request.form['mood']), int(request.form['energy']),
         request.form.get('note','').strip(), today,
         int(request.form['mood']), int(request.form['energy']),
         request.form.get('note','').strip()))
    conn.commit()
    conn.close()
    check_achievements(uid)
    flash('Mood logged! 🧘', 'success')
    return redirect(url_for('mood'))

# ════════════════════════════════════════════════════════════════════════
# ACHIEVEMENTS
# ════════════════════════════════════════════════════════════════════════
@app.route('/achievements')
@login_required
def achievements():
    uid = session['user_id']
    conn = get_db()
    earned = conn.execute("SELECT badge_key, earned_at FROM achievements WHERE user_id=? ORDER BY earned_at DESC", (uid,)).fetchall()
    conn.close()
    earned_keys = {e['badge_key']: e['earned_at'] for e in earned}
    all_badges = []
    for key, info in BADGES.items():
        all_badges.append({
            'key': key, **info,
            'earned': key in earned_keys,
            'earned_at': earned_keys.get(key, '')
        })
    return render_template('achievements.html', badges=all_badges,
        earned_count=len(earned_keys), total=len(BADGES))

# ════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    app.run(debug=True)