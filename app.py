import os
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

# In-memory record of everyone who submitted the fake login.
# NOTE: this resets on serverless cold starts / restarts. For durable
# storage, swap this for a database (e.g. Vercel KV, Supabase, SQLite).
# We deliberately DO NOT store the submitted password.
caught_users = []


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
    if any(u["username"] == username for u in caught_users):
        return
    now = datetime.now()
    caught_users.append(
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
    viewed_count = len(caught_users)
    not_viewed = max(TOTAL_MEMBERS - viewed_count, 0)

    return render_template(
        "dashboard.html",
        users=caught_users,
        total_members=TOTAL_MEMBERS,
        viewed_count=viewed_count,
        not_viewed=not_viewed,
    )


if __name__ == "__main__":
    app.run(debug=True)
