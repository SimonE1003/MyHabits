import random
import sqlite3
from datetime import date, datetime
from flask import Flask, redirect, render_template, request, session, jsonify
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required

DATABASE = 'myhabits.db'


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


app = Flask(__name__)
app.secret_key = 'your_secret_key'


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def home():
    return redirect("today")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
        username TEXT NOT NULL UNIQUE,
        hash TEXT NOT NULL,
        challenge_start_date DATE DEFAULT NULL
    )""")
    db.commit()

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must enter username")

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must enter password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          (request.form.get("username"),)).fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        db = get_db()
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            hash TEXT NOT NULL,
            challenge_start_date DATE DEFAULT NULL
        )""")
        db.commit()

        if not request.form.get("username"):
            return apology("must enter username")

        elif not request.form.get("password"):
            return apology("must enter password")

        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("passwords and confirmation not the same")

        username = request.form.get("username")

        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          (username,)).fetchall()
        if len(rows) != 0:
            return apology("username already exists")

        hash = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256')
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, hash))
        db.commit()

        rows = db.execute("SELECT * FROM users WHERE username = ?",
                          (username,)).fetchall()
        session["user_id"] = rows[0]["id"]

    return redirect("/")


@app.route("/logout")
def logout():
    """Log user out"""
    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/today")
@login_required
def today():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS habits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        phase TEXT,
        completed_days INTEGER DEFAULT 0,
        challenge_start DATE DEFAULT (date('now')),
        last_completed DATE DEFAULT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )""")
    db.commit()

    habit_count = db.execute(
        "SELECT COUNT(*) AS count FROM habits WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()["count"]

    if habit_count == 0:
        return render_template("today1.html")

    else:
        user = db.execute(
            "SELECT challenge_start_date FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()

        challenge_start_date_str = str(user['challenge_start_date'])
        delta = date.today() - date.fromisoformat(challenge_start_date_str)
        current_day = min(max(1, delta.days + 1), 21)

        habits = db.execute(
            "SELECT id, name, phase, completed_days, last_completed FROM habits WHERE user_id = ?",
            (session["user_id"],)
        ).fetchall()

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
        today_date = date.today()

        if current_day == 21:
            return render_template("today3.html", habits=habits)

        return render_template("today2.html", habits=habits, today=today_date,
                               challenge_day=current_day, challenge_start=user['challenge_start_date'],
                               random_quote=random_quote)


@app.route("/set_habits", methods=["GET", "POST"])
@login_required
def set_habits():
    if request.method == "POST":
        db = get_db()
        today = date.today().isoformat()

        # Set challenge start date
        db.execute("UPDATE users SET challenge_start_date = ? WHERE id = ?",
                   (today, session["user_id"]))

        # Delete existing habits if any
        db.execute("DELETE FROM habits WHERE user_id = ?", (session["user_id"],))

        # Insert new habits
        found_valid_habit = False
        for i in range(6):
            name = request.form.get(f"habit{i}")
            phase = request.form.get(f"phase{i}")
            if name:
                if not phase:
                    return apology("please enter a Time Phase for each habit")
                else:
                    found_valid_habit = True
                    db.execute("INSERT INTO habits (user_id, name, phase) VALUES (?, ?, ?)",
                               (session["user_id"], name, phase))

        if not found_valid_habit:
            return apology("You need at least one habit")

        db.commit()
        return redirect("/today")

    else:
        return render_template("set_habits.html")


@app.route("/now", methods=["GET", "POST"])
@login_required
def now():
    if request.method == "POST":
        db = get_db()
        today = date.today()
        habits_not_completed = db.execute(
            "SELECT name FROM habits WHERE user_id = ? AND (last_completed IS NULL OR last_completed != ?)",
            (session["user_id"], today)
        ).fetchall()

        return render_template('now_result.html', habits_not_completed=habits_not_completed)
    return render_template('now.html')


@app.route("/mark_done", methods=["POST"])
@login_required
def mark_done():
    try:
        db = get_db()
        habit_id = request.json.get("habit_id")
        today = date.today().isoformat()

        db.execute("UPDATE habits SET completed_days = completed_days + 1, last_completed = ? WHERE id = ?",
                   (today, habit_id))
        db.commit()
        return jsonify(success=True)
    except Exception as e:
        db.rollback()
        return jsonify(success=False, message=str(e)), 500


@app.route("/info")
@login_required
def info():
    return render_template("info.html")


class ReverseProxied:
    def __init__(self, app, prefix='/habits'):
        self.app = app
        self.prefix = prefix
    def __call__(self, environ, start_response):
        script_name = environ.get('HTTP_X_SCRIPT_NAME', '')
        if script_name:
            environ['SCRIPT_NAME'] = script_name

        def custom_start_response(status, headers, *args):
            # Fix Location headers in redirects
            for i, (k, v) in enumerate(headers):
                if k.lower() == 'location' and v.startswith('/') and not v.startswith(self.prefix):
                    headers[i] = (k, self.prefix + v)
            return start_response(status, headers, *args)

        return self.app(environ, custom_start_response)

app.wsgi_app = ReverseProxied(app.wsgi_app)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
