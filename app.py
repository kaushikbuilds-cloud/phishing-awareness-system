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

TOTAL_MEMBERS = int(os.environ.get("TOTAL_MEMBERS", "10"))

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
# We deliberately DO NOT store the submitted password.
#
# Vercel runs this app "serverless": each request may be handled by a
# different instance, so a plain in-memory list cannot be shared between the
# user who clicks and the admin who views the dashboard.
#
# If Vercel KV (Upstash Redis) is configured, we persist clicks there so the
# dashboard reliably shows every click. Otherwise we fall back to an in-memory
# list (fine for local testing and always-on hosts like Render/Railway).
# ---------------------------------------------------------------------------
KV_URL = os.environ.get("KV_REST_API_URL")
KV_TOKEN = os.environ.get("KV_REST_API_TOKEN")
KV_KEY = "caught_users"

_memory_users = []


def _kv_command(command):
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


def load_users():
    """Return all recorded clicks, newest last."""
    if KV_URL and KV_TOKEN:
        try:
            raw = _kv_command(["LRANGE", KV_KEY, 0, -1]) or []
            return [json.loads(item) for item in raw]
        except Exception:
            return []
    return list(_memory_users)


def add_user(record):
    """Record a click once per username."""
    existing = load_users()
    if any(u["username"] == record["username"] for u in existing):
        return

    if KV_URL and KV_TOKEN:
        try:
            _kv_command(["RPUSH", KV_KEY, json.dumps(record)])
        except Exception:
            pass
        return

    _memory_users.append(record)


def is_admin(username, password):
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin"))
        return view(*args, **kwargs)

    return wrapped


def record_catch(username):
    """Log that a user submitted the fake login (once per username)."""
    now = datetime.now()
    add_user(
        {
            "username": username,
            "date": now.strftime("%d-%m-%Y"),
            "time": now.strftime("%I:%M %p"),
            "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
        }
    )


@app.route("/")
def phishing_login():
    return render_template("phishing_login.html")


@app.route("/login", methods=["POST"])
def login():
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    # Admins skip the awareness flow and go straight to the dashboard.
    if is_admin(username, password):
        session["admin"] = True
        return redirect(url_for("dashboard"))

    if username:
        record_catch(username)

    return redirect(url_for("awareness"))


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
    users = load_users()
    viewed_count = len(users)
    not_viewed = max(TOTAL_MEMBERS - viewed_count, 0)

    return render_template(
        "dashboard.html",
        users=users,
        total_members=TOTAL_MEMBERS,
        viewed_count=viewed_count,
        not_viewed=not_viewed,
    )


if __name__ == "__main__":
    app.run(debug=True)
