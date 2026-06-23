from flask import Flask, render_template, request, redirect
from datetime import datetime

app = Flask(__name__)

# Awareness page open pannina users save aagum
viewed_users = []


@app.route('/')
def phishing_login():
    return render_template('phishing_login.html')


@app.route('/login', methods=['POST'])
def login():

    username = request.form.get('username')
    password = request.form.get('password')

    # Admin Login
    if username == "admin" and password == "1234":
        return redirect('/dashboard')

    # Normal User Record Save
    already_viewed = any(
        user["username"] == username
        for user in viewed_users
    )

    if not already_viewed:
        viewed_users.append({
            "username": username,
            "date": datetime.now().strftime("%d-%m-%Y"),
            "time": datetime.now().strftime("%I:%M %p")
        })

    return redirect('/awareness')


@app.route('/awareness')
def awareness():
    return render_template('awareness.html')


@app.route('/admin', methods=['GET', 'POST'])
def admin():

    if request.method == 'POST':

        username = request.form.get('username')
        password = request.form.get('password')

        if username == "admin" and password == "1234":
            return redirect('/dashboard')

        return "Invalid Admin Credentials"

    return render_template('admin_login.html')


@app.route('/dashboard')
def dashboard():

    total_members = 10

    viewed_count = len(viewed_users)
    not_viewed = total_members - viewed_count

    return render_template(
        'dashboard.html',
        users=viewed_users,
        total_members=total_members,
        viewed_count=viewed_count,
        not_viewed=not_viewed
    )


if __name__ == '__main__':
    app.run(debug=True)