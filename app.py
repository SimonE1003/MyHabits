import os
import random
import sqlite3
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from flask import Flask, g, redirect, render_template, request, session, jsonify
from flask_wtf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv

from helpers import apology, login_required
from ai_planner import generate_plan
from stats import compute_user_stats
from translations import t as translate, QUOTE_KEYS

load_dotenv()

# Default timezone for the app (used when user hasn't picked one).
DEFAULT_TIMEZONE = 'Asia/Shanghai'
SHANGHAI_TZ = timezone(timedelta(hours=8))

# Timezone options shown on the set_habits page.
# (IANA name, display label) — label is city + UTC offset, language-neutral.
SUPPORTED_TIMEZONES = [
    ('Asia/Shanghai',        '北京/上海 (UTC+8)'),
    ('Asia/Hong_Kong',       '香港 (UTC+8)'),
    ('Asia/Tokyo',           '东京 (UTC+9)'),
    ('Asia/Singapore',       '新加坡 (UTC+8)'),
    ('America/Los_Angeles',  'Los Angeles (UTC-8)'),
    ('America/New_York',     'New York (UTC-5)'),
    ('Europe/London',        'London (UTC+0)'),
    ('UTC',                  'UTC'),
]
SUPPORTED_TIMEZONE_NAMES = {tz for tz, _ in SUPPORTED_TIMEZONES}

DATABASE = os.environ.get('DATABASE', 'myhabits.db')


# ---------- Database helpers ----------

def get_db():
    """Per-request SQLite connection stored on Flask `g`, reused within a request."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db():
    """Create tables and indexes once at startup. Idempotent."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            hash TEXT NOT NULL,
            challenge_start_date DATE DEFAULT NULL,
            timezone TEXT DEFAULT 'Asia/Shanghai'
        );

        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phase TEXT NOT NULL,
            completed_days INTEGER DEFAULT 0,
            challenge_start DATE DEFAULT (date('now')),
            last_completed DATE DEFAULT NULL,
            challenge_round INTEGER DEFAULT 1,
            archived INTEGER DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        -- habit_logs prevents double-counting: UNIQUE(habit_id, completed_date)
        -- makes marking done idempotent per day.
        CREATE TABLE IF NOT EXISTS habit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            completed_date DATE NOT NULL,
            FOREIGN KEY(habit_id) REFERENCES habits(id) ON DELETE CASCADE,
            UNIQUE(habit_id, completed_date)
        );

        CREATE INDEX IF NOT EXISTS idx_habits_user ON habits(user_id);
        CREATE INDEX IF NOT EXISTS idx_logs_habit_date ON habit_logs(habit_id, completed_date);
    """)
    db.commit()
    db.close()


def migrate_db():
    """Add new columns to existing tables. Idempotent — safe to run every startup.

    SQLite's ALTER TABLE ADD COLUMN lets us evolve the schema without losing data.
    """
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row

    user_cols = {c['name'] for c in db.execute("PRAGMA table_info(users)").fetchall()}
    if 'timezone' not in user_cols:
        db.execute("ALTER TABLE users ADD COLUMN timezone TEXT DEFAULT 'Asia/Shanghai'")

    habit_cols = {c['name'] for c in db.execute("PRAGMA table_info(habits)").fetchall()}
    if 'challenge_round' not in habit_cols:
        db.execute("ALTER TABLE habits ADD COLUMN challenge_round INTEGER DEFAULT 1")
    if 'archived' not in habit_cols:
        db.execute("ALTER TABLE habits ADD COLUMN archived INTEGER DEFAULT 0")

    db.commit()
    db.close()


# ---------- App setup ----------

app = Flask(__name__)
# In production, ALWAYS set SECRET_KEY env var. The os.urandom fallback
# invalidates all sessions on every restart, so it's dev-only.
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24)

# Keep users logged in for 30 days instead of just until the browser closes.
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

# CSRF protection on all POST routes. Exemptions are applied per-route below.
csrf = CSRFProtect(app)

# Initialize schema at import time so tables exist before first request.
init_db()
# Evolve existing databases by adding new columns (timezone, challenge_round, archived).
migrate_db()


@app.before_request
def make_session_permanent():
    """Extend every session to use the 30-day lifetime."""
    session.permanent = True


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ---------- Timezone helpers ----------

def get_user_timezone(user_id):
    """Return the user's ZoneInfo, defaulting to Asia/Shanghai.

    Falls back gracefully if the stored timezone name is invalid.
    """
    db = get_db()
    row = db.execute("SELECT timezone FROM users WHERE id = ?", (user_id,)).fetchone()
    tz_name = row['timezone'] if row and row['timezone'] else DEFAULT_TIMEZONE
    try:
        return ZoneInfo(tz_name)
    except (KeyError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def user_today(user_id):
    """Today's date in the user's timezone — replaces date.today() everywhere."""
    return datetime.now(get_user_timezone(user_id)).date()


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# ---------- i18n ----------

SUPPORTED_LANGS = {'en', 'zh'}

@app.context_processor
def inject_i18n():
    """Make t(key) and lang available in every template."""
    lang = session.get('lang', 'en')
    return {'t': lambda key: translate(key, lang), 'lang': lang}


@app.route("/set_language", methods=["POST"])
@csrf.exempt
def set_language():
    """Switch language. Called via sendBeacon from the nav button."""
    # sendBeacon sends with Content-Type from the Blob, but some browsers
    # override to text/plain. Accept both JSON and form data.
    data = request.get_json(silent=True)
    if data is None:
        data = request.form.to_dict()
    lang = (data or {}).get('lang', 'en')
    if lang not in SUPPORTED_LANGS:
        return jsonify(success=False), 400
    session['lang'] = lang
    return jsonify(success=True)


# ---------- Auth routes ----------

@app.route("/")
@login_required
def home():
    return redirect("/today")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Preserve language preference across session.clear()
    saved_lang = session.get('lang')
    session.clear()
    if saved_lang:
        session['lang'] = saved_lang
    db = get_db()

    if request.method == "POST":
        username = (request.form.get("username", "") or "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return render_template("login.html", error_key="login.error_both", username_value=username), 400

        rows = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchall()

        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], password):
            return render_template("login.html", error_key="login.error_match", username_value=username), 401

        session["user_id"] = rows[0]["id"]
        return redirect("/")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")

    db = get_db()
    username = (request.form.get("username", "") or "").strip()
    password = request.form.get("password", "")
    confirmation = request.form.get("confirmation", "")

    if not username or not password:
        return render_template("register.html", error_key="register.error_both", username_value=username), 400
    if confirmation != password:
        return render_template("register.html", error_key="register.error_match", username_value=username), 400
    if len(username) > 64 or len(password) > 128:
        return render_template("register.html", error_key="register.error_length", username_value=username), 400

    rows = db.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchall()
    if len(rows) != 0:
        return render_template("register.html", error_key="register.error_taken", username_value=username), 409

    pw_hash = generate_password_hash(password, method='pbkdf2:sha256')
    cursor = db.execute(
        "INSERT INTO users (username, hash) VALUES (?, ?)", (username, pw_hash)
    )
    db.commit()
    session["user_id"] = cursor.lastrowid
    return redirect("/")


@app.route("/logout")
def logout():
    """Log user out"""
    session.clear()
    return redirect("/")


# ---------- Habit routes ----------

@app.route("/today")
@login_required
def today():
    db = get_db()
    user_id = session["user_id"]
    habit_count = db.execute(
        "SELECT COUNT(*) AS count FROM habits WHERE user_id = ? AND archived = 0",
        (user_id,)
    ).fetchone()["count"]

    if habit_count == 0:
        return render_template("today1.html")

    user = db.execute(
        "SELECT challenge_start_date FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    challenge_start = user['challenge_start_date']
    if challenge_start is None:
        return render_template("today1.html")

    today_date = user_today(user_id)
    today_str = today_date.isoformat()
    delta = today_date - date.fromisoformat(str(challenge_start))
    current_day = delta.days + 1  # Day 1 = first day of the challenge

    habits = db.execute(
        "SELECT id, name, phase, completed_days, last_completed FROM habits WHERE user_id = ? AND archived = 0",
        (user_id,)
    ).fetchall()

    if current_day > 21:
        # Challenge finished: show the report + link to start a new round.
        return render_template("today3.html", habits=habits, challenge_finished=True)

    random_quote_key = random.choice(QUOTE_KEYS)

    return render_template(
        "today2.html",
        habits=habits,
        today=today_str,
        challenge_day=max(1, current_day),
        challenge_start=challenge_start,
        random_quote_key=random_quote_key
    )


@app.route("/set_habits", methods=["GET", "POST"])
@login_required
def set_habits():
    user_id = session["user_id"]
    if request.method == "POST":
        db = get_db()

        # Validate ALL inputs first, before mutating any data.
        VALID_PHASES = {'morning', 'afternoon', 'evening'}
        new_habits = []
        for i in range(6):
            name = (request.form.get(f"habit{i}") or "").strip()
            phase = request.form.get(f"phase{i}")
            if name:
                if not phase or phase not in VALID_PHASES:
                    return apology(translate("set_habits.error_no_phase", session.get('lang', 'en')))
                new_habits.append((name, phase))

        if not new_habits:
            return apology(translate("set_habits.error_no_habit", session.get('lang', 'en')))

        # Validate timezone (falls back to default if invalid/missing)
        tz_val = request.form.get("timezone", DEFAULT_TIMEZONE)
        if tz_val not in SUPPORTED_TIMEZONE_NAMES:
            tz_val = DEFAULT_TIMEZONE

        today = user_today(user_id).isoformat()
        try:
            # Archive current habits instead of deleting — preserves history.
            # habit_logs are kept too since the habit rows still exist.
            db.execute(
                "UPDATE habits SET archived = 1 WHERE user_id = ? AND archived = 0",
                (user_id,)
            )

            # Determine next challenge round (1 if no prior rounds exist)
            round_row = db.execute(
                "SELECT MAX(challenge_round) AS max_round FROM habits WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            next_round = (round_row['max_round'] or 0) + 1

            db.execute(
                "UPDATE users SET challenge_start_date = ?, timezone = ? WHERE id = ?",
                (today, tz_val, user_id)
            )

            for name, phase in new_habits:
                db.execute(
                    "INSERT INTO habits (user_id, name, phase, challenge_round, archived) VALUES (?, ?, ?, ?, 0)",
                    (user_id, name, phase, next_round)
                )
            db.commit()
        except Exception:
            db.rollback()
            raise

        return redirect("/today")

    # GET: pass timezone info so the dropdown can show the current selection.
    db = get_db()
    user = db.execute("SELECT timezone FROM users WHERE id = ?", (user_id,)).fetchone()
    current_tz = user['timezone'] if user and user['timezone'] else DEFAULT_TIMEZONE
    return render_template("set_habits.html", timezones=SUPPORTED_TIMEZONES, current_timezone=current_tz)


@app.route("/now", methods=["GET"])
@login_required
def now():
    """Show the 'Now' page.

    Only available during an active 21-day challenge:
    - No habits set, challenge not started, or challenge finished →
      prompt the user to set habits / start a new round.
    - All habits done today → 'today complete' message.
    - Otherwise → bedtime input + 'What to do now' AI planner.
    """
    db = get_db()
    user_id = session["user_id"]
    today_str = user_today(user_id).isoformat()
    total_habits = db.execute(
        "SELECT COUNT(*) AS n FROM habits WHERE user_id = ? AND archived = 0",
        (user_id,)
    ).fetchone()["n"]

    # No habits yet → set habits first.
    if total_habits == 0:
        return render_template('now_result.html', state='no_habits')

    # Mirror /today's challenge-window checks so /now is only usable mid-challenge.
    user = db.execute(
        "SELECT challenge_start_date FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    challenge_start = user['challenge_start_date']

    # Has habits but challenge never started → set habits to begin.
    if challenge_start is None:
        return render_template('now_result.html', state='not_started')

    today_date = user_today(user_id)
    current_day = (today_date - date.fromisoformat(str(challenge_start))).days + 1

    # 21-day challenge finished → prompt to start a new round.
    if current_day > 21:
        return render_template('now_result.html', state='challenge_finished')

    # Inside the challenge window: proceed as normal.
    habits_not_completed = db.execute(
        """SELECT name, phase FROM habits
           WHERE user_id = ? AND archived = 0
             AND (last_completed IS NULL OR last_completed != ?)""",
        (user_id, today_str)
    ).fetchall()

    if not habits_not_completed:
        return render_template('now_result.html', state='all_done')

    current_time = datetime.now(get_user_timezone(user_id)).strftime("%H:%M")
    return render_template('now.html', habits_not_completed=habits_not_completed, current_time=current_time)


@app.route("/api/now_plan", methods=["POST"])
@login_required
def now_plan():
    """Generate an AI plan for the user's remaining habits today.

    Only callable during an active 21-day challenge. Expects JSON body:
    {"bedtime": "23:30"} (bedtime optional). Returns JSON:
    {"plan": "...", "latency_ms": ..., "usage": {...}} or {"error": "..."}.
    """
    db = get_db()
    user_id = session["user_id"]
    today_str = user_today(user_id).isoformat()

    # Same challenge-window guard as /now — defense in depth against
    # direct API calls outside the challenge.
    total_habits = db.execute(
        "SELECT COUNT(*) AS n FROM habits WHERE user_id = ? AND archived = 0",
        (user_id,)
    ).fetchone()["n"]
    if total_habits == 0:
        return jsonify({"error": "No habits set. Define your habits first."}), 400

    user = db.execute(
        "SELECT challenge_start_date FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()
    challenge_start = user['challenge_start_date']
    if challenge_start is None:
        return jsonify({"error": "Challenge not started. Set your habits to begin."}), 400

    today_date = user_today(user_id)
    current_day = (today_date - date.fromisoformat(str(challenge_start))).days + 1
    if current_day > 21:
        return jsonify({"error": "This 21-day challenge is complete. Start a new round to plan again."}), 400

    habits_not_completed = db.execute(
        """SELECT name, phase FROM habits
           WHERE user_id = ? AND archived = 0
             AND (last_completed IS NULL OR last_completed != ?)""",
        (user_id, today_str)
    ).fetchall()

    if not habits_not_completed:
        return jsonify({"error": "All habits are already done today."}), 400

    data = request.get_json(silent=True) or {}
    bedtime = data.get("bedtime") or None
    lang = session.get('lang', 'en')
    user_tz = get_user_timezone(user_id)

    habits_list = [{"name": h["name"], "phase": h["phase"]} for h in habits_not_completed]
    result = generate_plan(habits_list, bedtime=bedtime, lang=lang, user_tz=user_tz)

    if result["error"]:
        return jsonify({"error": result["error"]}), 502

    return jsonify({
        "plan": result["plan"],
        "latency_ms": result["latency_ms"],
        "usage": result["usage"],
    })


@app.route("/mark_done", methods=["POST"])
@login_required
def mark_done():
    """Mark a habit as done for today. Idempotent: clicking twice does not double-count."""
    db = get_db()
    user_id = session["user_id"]
    try:
        data = request.get_json(silent=True)
        if not data or "habit_id" not in data:
            return jsonify(success=False, message="Invalid request"), 400
        habit_id = data.get("habit_id")
        # Validate habit_id is a positive integer (defends against odd input)
        try:
            habit_id = int(habit_id)
            if habit_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify(success=False, message="Invalid habit id"), 400
        today = user_today(user_id).isoformat()

        # Step 1: verify ownership AND habit is active (not archived) BEFORE
        # touching habit_logs, so a user can't probe archived habits.
        owns = db.execute(
            "SELECT 1 FROM habits WHERE id = ? AND user_id = ? AND archived = 0",
            (habit_id, user_id)
        ).fetchone()
        if owns is None:
            return jsonify(success=False, message="Habit not found"), 404

        # Step 2: insert into habit_logs. UNIQUE(habit_id, completed_date)
        # makes this idempotent per day.
        cur = db.execute(
            "INSERT OR IGNORE INTO habit_logs (habit_id, completed_date) VALUES (?, ?)",
            (habit_id, today)
        )
        if cur.rowcount == 0:
            # Already logged today — treat as success, no counter change.
            db.commit()
            return jsonify(success=True, already_done=True)

        # Step 3: bump counters. Ownership already verified above.
        db.execute(
            """UPDATE habits
               SET completed_days = completed_days + 1,
                   last_completed = ?
               WHERE id = ?""",
            (today, habit_id)
        )
        db.commit()
        return jsonify(success=True)
    except Exception as e:
        db.rollback()
        return jsonify(success=False, message=str(e)), 500


@app.route("/info")
@login_required
def info():
    return render_template("info.html")


@app.route("/stats")
@login_required
def stats():
    """Show discipline metrics and a calendar heatmap of the user's history.

    Pulls data from all challenge rounds (active + archived) so the user
    sees their full trajectory, not just the current round.
    """
    user_id = session["user_id"]
    user_tz = get_user_timezone(user_id)
    db = get_db()
    data = compute_user_stats(db, user_id, user_tz=user_tz)

    if data is None:
        # No habits at all → same empty state as /today
        return render_template("stats.html", has_data=False)

    return render_template("stats.html", has_data=True, stats=data)


# ---------- Reverse proxy middleware ----------

class ReverseProxied:
    """Fix redirect Location headers when running behind a path-prefixed reverse proxy."""

    def __init__(self, app, prefix=None):
        self.app = app
        self.prefix = prefix or os.environ.get('REVERSE_PROXY_PREFIX', '')

    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name

        prefix = self.prefix

        def custom_start_response(status, headers, *args):
            if prefix:
                for i, (k, v) in enumerate(headers):
                    if k.lower() == 'location' and v.startswith('/') and not v.startswith(prefix):
                        headers[i] = (k, prefix + v)
            return start_response(status, headers, *args)

        return self.app(environ, custom_start_response)


app.wsgi_app = ReverseProxied(app.wsgi_app)


if __name__ == "__main__":
    # Debug only when explicitly enabled. Never enable in production.
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=debug, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
