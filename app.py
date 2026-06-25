import os
import json
import urllib.request
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Admin credentials (override via environment variables in production)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
# DEMO / TRAINING ONLY: passwords are stored and shown in plaintext on the
# admin dashboard because that is an explicit requirement of this awareness
# project. A real production app must NEVER do this -- always hash passwords.
#
# Vercel runs this app "serverless": each request may hit a different
# instance, so a plain in-memory store cannot be shared between the user and
# the admin. When Vercel KV (Upstash Redis) is configured we persist data
# there; otherwise we fall back to in-memory (local dev / always-on hosts).
#
#   users    -> Redis hash:  username -> {username, password, date, time}
#   attempts -> Redis list:  every login attempt (correct or wrong)
# ---------------------------------------------------------------------------
KV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")
KV_ENABLED = bool(KV_URL and KV_TOKEN)

USERS_KEY = "users"
ATTEMPTS_KEY = "attempts"

_mem_users = {}
_mem_attempts = []


def _kv(command):
    req = urllib.request.Request(
        KV_URL,
        data=json.dumps(command).encode(),
        headers={
            "Authorization": f"Bearer {KV_TOKEN}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode()).get("result")


# ---- registered users -----------------------------------------------------
def users_all():
    if KV_ENABLED:
        try:
            flat = _kv(["HGETALL", USERS_KEY]) or []
            return {
                flat[i]: json.loads(flat[i + 1]) for i in range(0, len(flat), 2)
            }
        except Exception:
            return {}
    return dict(_mem_users)


def user_get(username):
    if KV_ENABLED:
        try:
            value = _kv(["HGET", USERS_KEY, username])
            return json.loads(value) if value else None
        except Exception:
            return None
    return _mem_users.get(username)


def user_set(username, record):
    if KV_ENABLED:
        try:
            _kv(["HSET", USERS_KEY, username, json.dumps(record)])
        except Exception:
            pass
        return
    _mem_users[username] = record


# ---- login attempts -------------------------------------------------------
def attempts_all():
    if KV_ENABLED:
        try:
            raw = _kv(["LRANGE", ATTEMPTS_KEY, 0, -1]) or []
            return [json.loads(item) for item in raw]
        except Exception:
            return []
    return list(_mem_attempts)


def attempt_add(record):
    if KV_ENABLED:
        try:
            _kv(["RPUSH", ATTEMPTS_KEY, json.dumps(record)])
        except Exception:
            pass
        return
    _mem_attempts.append(record)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def now_parts():
    now = datetime.now()
    return now.strftime("%d-%m-%Y"), now.strftime("%I:%M %p")


def client_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr)


def is_admin(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin"))
        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Please enter both a username and a password.")
            return redirect(url_for("register"))

        if user_get(username):
            flash("That username already exists. Please log in.")
            return redirect(url_for("home"))

        date, time = now_parts()
        user_set(
            username,
            {"username": username, "password": password, "date": date, "time": time},
        )
        flash("Account created successfully! Please log in.")
        return redirect(url_for("home"))

    return render_template("register.html")


@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    # Admin shortcut -> dashboard.
    if is_admin(username, password):
        session["admin"] = True
        return redirect(url_for("dashboard"))

    user = user_get(username)
    correct = bool(user and user.get("password") == password)

    date, time = now_parts()
    attempt_add(
        {
            "username": username,
            "password": password,
            "result": "Correct" if correct else "Wrong",
            "date": date,
            "time": time,
            "ip": client_ip(),
        }
    )

    if correct:
        return redirect(url_for("awareness"))

    flash("Invalid username or password.")
    return redirect(url_for("home"))


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        user = user_get(username)
        if not user:
            flash("No account found with that username.")
            return redirect(url_for("forgot"))

        if not password:
            flash("Please enter a new password.")
            return redirect(url_for("forgot"))

        user["password"] = password
        user_set(username, user)
        flash("Password updated successfully! Please log in.")
        return redirect(url_for("home"))

    return render_template("forgot.html")


@app.route("/awareness")
def awareness():
    return render_template("awareness.html")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if is_admin(username, password):
            session["admin"] = True
            return redirect(url_for("dashboard"))

        flash("Invalid admin credentials.")
        return redirect(url_for("admin"))

    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("admin"))


@app.route("/dashboard")
@login_required
def dashboard():
    users = list(users_all().values())
    attempts = attempts_all()

    return render_template(
        "dashboard.html",
        users=users,
        attempts=attempts,
        total_users=len(users),
        total_attempts=len(attempts),
        correct_count=sum(1 for a in attempts if a.get("result") == "Correct"),
        wrong_count=sum(1 for a in attempts if a.get("result") == "Wrong"),
    )


if __name__ == "__main__":
    app.run(debug=True)
