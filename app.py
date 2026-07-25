import os
import random
import sqlite3
from datetime import date
from flask import Flask, g, redirect, render_template, request, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required

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
            challenge_start_date DATE DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            phase TEXT NOT NULL,
            completed_days INTEGER DEFAULT 0,
            challenge_start DATE DEFAULT (date('now')),
            last_completed DATE DEFAULT NULL,
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


# ---------- App setup ----------

app = Flask(__name__)
# In production, ALWAYS set SECRET_KEY env var. The os.urandom fallback
# invalidates all sessions on every restart, so it's dev-only.
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24)

# Initialize schema at import time so tables exist before first request.
init_db()


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# ---------- Auth routes ----------

@app.route("/")
@login_required
def home():
    return redirect("/today")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()
    db = get_db()

    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must enter username")
        if not request.form.get("password"):
            return apology("must enter password")

        rows = db.execute(
            "SELECT * FROM users WHERE username = ?",
            (request.form.get("username"),)
        ).fetchall()

        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password")

        session["user_id"] = rows[0]["id"]
        return redirect("/")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")

    db = get_db()
    if not request.form.get("username"):
        return apology("must enter username")
    if not request.form.get("password"):
        return apology("must enter password")
    if request.form.get("confirmation") != request.form.get("password"):
        return apology("passwords and confirmation not the same")

    username = request.form.get("username")
    rows = db.execute(
        "SELECT id FROM users WHERE username = ?", (username,)
    ).fetchall()
    if len(rows) != 0:
        return apology("username already exists")

    pw_hash = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256')
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
    habit_count = db.execute(
        "SELECT COUNT(*) AS count FROM habits WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()["count"]

    if habit_count == 0:
        return render_template("today1.html")

    user = db.execute(
        "SELECT challenge_start_date FROM users WHERE id = ?",
        (session["user_id"],)
    ).fetchone()

    challenge_start = user['challenge_start_date']
    if challenge_start is None:
        return render_template("today1.html")

    today_date = date.today()
    today_str = today_date.isoformat()
    delta = today_date - date.fromisoformat(str(challenge_start))
    current_day = delta.days + 1  # Day 1 = first day of the challenge

    habits = db.execute(
        "SELECT id, name, phase, completed_days, last_completed FROM habits WHERE user_id = ?",
        (session["user_id"],)
    ).fetchall()

    if current_day > 21:
        # Challenge finished: show the report + link to start a new round.
        return render_template("today3.html", habits=habits, challenge_finished=True)

    quotes = [
        "Up to 70% of our waking behaviors are made up of habitual behaviors. — Andrew Huberman",
        "A slight change in your daily habits can guide your life to a very different destination - James Clear",
        "Forget about goals, focus on systems instead - James Clear",
        "Goals are good for setting a direction, but systems are best for making progress - James Clear",
        "Until you make the unconscious conscious, it will direct your life and you will call it fate - Carl Jung",
        "Environment is the invisible hand that shapes human behavior - James Clear",
        "Stay Hard! - David Goggins",
        "Discipline Equals Freedom - Jocko Willink"
    ]
    random_quote = random.choice(quotes)

    return render_template(
        "today2.html",
        habits=habits,
        today=today_str,
        challenge_day=max(1, current_day),
        challenge_start=challenge_start,
        random_quote=random_quote
    )


@app.route("/set_habits", methods=["GET", "POST"])
@login_required
def set_habits():
    if request.method == "POST":
        db = get_db()

        # Validate ALL inputs first, before mutating any data.
        new_habits = []
        for i in range(6):
            name = (request.form.get(f"habit{i}") or "").strip()
            phase = request.form.get(f"phase{i}")
            if name:
                if not phase:
                    return apology("please enter a Time Phase for each habit")
                new_habits.append((name, phase))

        if not new_habits:
            return apology("You need at least one habit")

        today = date.today().isoformat()
        try:
            db.execute(
                "UPDATE users SET challenge_start_date = ? WHERE id = ?",
                (today, session["user_id"])
            )
            # ON DELETE CASCADE not guaranteed without PRAGMA, so delete logs explicitly.
            db.execute(
                """DELETE FROM habit_logs WHERE habit_id IN
                   (SELECT id FROM habits WHERE user_id = ?)""",
                (session["user_id"],)
            )
            db.execute("DELETE FROM habits WHERE user_id = ?", (session["user_id"],))
            for name, phase in new_habits:
                db.execute(
                    "INSERT INTO habits (user_id, name, phase) VALUES (?, ?, ?)",
                    (session["user_id"], name, phase)
                )
            db.commit()
        except Exception:
            db.rollback()
            raise

        return redirect("/today")

    return render_template("set_habits.html")


@app.route("/now", methods=["GET", "POST"])
@login_required
def now():
    if request.method == "POST":
        db = get_db()
        today_str = date.today().isoformat()
        habits_not_completed = db.execute(
            """SELECT name FROM habits
               WHERE user_id = ?
                 AND (last_completed IS NULL OR last_completed != ?)""",
            (session["user_id"], today_str)
        ).fetchall()
        return render_template('now_result.html', habits_not_completed=habits_not_completed)
    return render_template('now.html')


@app.route("/mark_done", methods=["POST"])
@login_required
def mark_done():
    """Mark a habit as done for today. Idempotent: clicking twice does not double-count."""
    db = get_db()
    try:
        habit_id = request.json.get("habit_id")
        today = date.today().isoformat()
        user_id = session["user_id"]

        # Step 1: verify ownership BEFORE touching habit_logs, so a user
        # can't probe whether someone else's habit was already marked today.
        owns = db.execute(
            "SELECT 1 FROM habits WHERE id = ? AND user_id = ?",
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
