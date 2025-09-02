import random
from datetime import date, datetime
from flask import Flask, redirect, render_template, request, session, jsonify
#from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
import pymysql

from helpers import apology, login_required

def get_db():
    conn = pymysql.connect(
        host='localhost',
        user='root',
        password='Wym:050311',
        database='myhabits',
        charset='utf8mb4'  # 通常建议设置合适的字符集
    )
    return conn

def init_app(app):
    pass

app = Flask(__name__)
init_app(app)

# Configure session to use filesystem (instead of signed cookies)
#app.config["SESSION_PERMANENT"] = False
#app.config["SESSION_TYPE"] = "filesystem"
#Session(app)

# 设置flask自带session所需的secret_key
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
    with db.cursor(pymysql.cursors.DictCursor) as cursor:  # 使用DictCursor方便以字典形式获取结果
        # 创建users表，自增主键使用AUTO_INCREMENT，创建唯一索引方式修改
        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY NOT NULL, username VARCHAR(255) NOT NULL, hash VARCHAR(255) NOT NULL, challenge_start_date DATE DEFAULT NULL, UNIQUE (username));")
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

        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            # Query database for username
            cursor.execute("SELECT * FROM users WHERE username = %s", (request.form.get("username"),))
            rows = cursor.fetchall()

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
        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            # 创建users表，自增主键使用AUTO_INCREMENT，创建唯一索引方式修改
            cursor.execute("CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY NOT NULL, username VARCHAR(255) NOT NULL, hash VARCHAR(255) NOT NULL, challenge_start_date DATE DEFAULT NULL, UNIQUE (username));")
        db.commit()

        if not request.form.get("username"):
            return apology("must enter username")

        elif not request.form.get("password"):
            return apology("must enter password")
        
        elif request.form.get("confirmation") != request.form.get("password"):
            return apology("passwords and confirmation not the same")

        username = request.form.get("username")

        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            rows = cursor.fetchall()
        if len(rows) != 0:
            return apology("username already exists")

        hash = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256')
        with db.cursor() as cursor:
            cursor.execute("INSERT INTO users (username, hash) VALUES (%s, %s)", (username, hash))
        db.commit()

        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            rows = cursor.fetchall()
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
    # Check if user has any habits
    db = get_db()
    with db.cursor(pymysql.cursors.DictCursor) as cursor:
        # 创建habits表，自增主键使用AUTO_INCREMENT，创建唯一索引方式修改
        cursor.execute("""CREATE TABLE IF NOT EXISTS habits 
                   (id INT AUTO_INCREMENT PRIMARY KEY, 
                   user_id INT, 
                   name VARCHAR(255), 
                   phase VARCHAR(255), 
                   completed_days INT DEFAULT 0, 
                   challenge_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                   last_completed DATE DEFAULT NULL,
                   FOREIGN KEY(user_id) REFERENCES users(id));""")
    db.commit()

    with db.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM habits WHERE user_id = %s", (session["user_id"],))
        habit_count = cursor.fetchone()["count"]

    if habit_count == 0:
        return render_template("today1.html") 
    
    else:
        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT challenge_start_date FROM users WHERE id = %s", (session["user_id"],))
            user = cursor.fetchone()
        
        challenge_start_date_str = str(user['challenge_start_date'])
        delta = date.today() - date.fromisoformat(challenge_start_date_str)
        current_day = min(max(1, delta.days + 1), 21)  # Clamp 1 - 21

        with db.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute("SELECT id, name, phase, completed_days, last_completed FROM habits WHERE user_id = %s", (session["user_id"],))
            habits = cursor.fetchall()

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

        today_date = datetime.strptime(date.today().isoformat(), '%Y-%m-%d').date()
        
        current_day = 21
        if current_day == 21:
            return render_template("today3.html", habits=habits)
        
        return render_template("today2.html", habits=habits, today=today_date, challenge_day=current_day, challenge_start=user['challenge_start_date'], random_quote=random_quote)



@app.route("/set_habits", methods=["GET", "POST"])
@login_required
def set_habits():
    if request.method == "POST":
        db = get_db()
        today = date.today().isoformat()

        # Set challenge start date (NEW)
        with db.cursor() as cursor:
            cursor.execute("UPDATE users SET challenge_start_date = %s WHERE id = %s", (today, session["user_id"]))

        # Delete existing habits if any
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM habits WHERE user_id = %s", (session["user_id"],))
        
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
                    with db.cursor() as cursor:
                        cursor.execute("INSERT INTO habits (user_id, name, phase) VALUES (%s, %s, %s)", (session["user_id"], name, phase))

        if not found_valid_habit:
            return apology("You need at least one habit")

        db.commit()
        return redirect("/today")
    
    else:
        return render_template("set_habits.html")


@app.route("/mark_done", methods=["POST"])
@login_required
def mark_done():
    try:
        db = get_db()
        habit_id = request.json.get("habit_id")
        today = date.today().isoformat()

        with db.cursor() as cursor:
            cursor.execute("UPDATE habits SET completed_days = completed_days + 1, last_completed = %s WHERE id = %s", (today, habit_id))
        db.commit()
        return jsonify(success=True)
    except Exception as e:
        db.rollback()
        return jsonify(success=False, message=str(e)), 500
    
@app.route("/info")
@login_required
def info():
    return render_template("info.html")

if __name__ == "__main__":
    app.run(debug=True)
