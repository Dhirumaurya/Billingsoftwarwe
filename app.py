from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from datetime import datetime, timedelta
from pymongo import MongoClient
import uuid, random, string

app = Flask(__name__)
app.secret_key = 'demo-secret'

# ---------------------- DB INIT ----------------------

client = MongoClient("mongodb://localhost:27017/")
db = client["company"]
users_col = db["users"]
licenses_col = db["licenses"]

# ---------------------- API LOGIN ----------------------
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required"}), 400

    user = db.users.find_one({"email": email})
    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    if not verify_pw(password, user["password"]):
        return jsonify({"success": False, "message": "Invalid password"}), 401

    token = make_token({
        "user_id": str(user["_id"]),
        "exp": datetime.utcnow() + timedelta(days=7)
    })
    return jsonify({"success": True, "token": token})

# ------------------ API: Check License ------------------ #
@app.route("/api/check_license", methods=["POST"])
def api_check_license():
    data = request.get_json()
    license_key = data.get("license_key")

    if not license_key:
        return jsonify({"success": False, "message": "License key required"}), 400

    license_data = db.licenses.find_one({"license_key": license_key})
    if not license_data:
        return jsonify({"success": False, "message": "License not found"}), 404

    if license_data.get("status") != "active":
        return jsonify({"success": False, "message": "License inactive"}), 403

    expiry_date = license_data.get("expiry_date")  # string ya datetime
    if isinstance(expiry_date, str):
        expiry_date = datetime.strptime(expiry_date, "%Y-%m-%d")

    if expiry_date < datetime.now():
        return jsonify({"success": False, "message": "License expired"}), 403

    return jsonify({"success": True, "message": "License valid", "expiry_date": expiry_date.strftime("%Y-%m-%d")})
# ---------------------- ROUTES ----------------------

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        if users_col.find_one({"email": email}):
            flash("Email already exists!", "danger")
            return redirect(url_for('signup'))

        user = {
            "name": request.form['name'],
            "mobile": request.form['mobile'],
            "email": email,
            "password": request.form['password'],
            "amount": request.form['amount'],
            "signup_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        users_col.insert_one(user)
        flash("Signup successful!", "success")
        return redirect(url_for('welcome'))

    return render_template('signup.html')

@app.route('/welcome')
def welcome():
    return render_template('welcome.html')

@app.route('/admin')
def admin_dashboard():
    licenses = []
    today = datetime.today()

    for lic in licenses_col.find():
        try:
            valid_until = datetime.strptime(lic["valid_until"], "%Y-%m-%d")
            status = "Valid" if lic["is_active"] and today <= valid_until else "Expired"
        except:
            status = "Invalid Date"

        licenses.append({
            "client_id": lic["client_id"],
            "client_name": lic["client_name"],
            "email": lic["email"],
            "machine_id": lic["machine_id"],
            "last_payment": lic["last_payment"],
            "valid_until": lic["valid_until"],
            "status": status
        })

    return render_template("dashboard.html", licenses=licenses)


@app.route('/activate', methods=["GET", "POST"])
def activate():
    if request.method == "POST":
        client_name = request.form.get('client_name')
        email = request.form.get('email')
        client_id = request.form.get('client_id')
        transaction_id = request.form.get('transaction_id')
        duration = int(request.form.get('duration'))
        password = request.form.get('password')

        today = datetime.today()
        valid_until = today + timedelta(days=duration)
        machine_id = str(uuid.uuid4())


        duplicate = licenses_col.find_one({"email": email, "client_id": client_id})
        if duplicate:

            return render_template("activate.html", already_activated=True)


        license = {
            "client_name": client_name,
            "email": email,
            "client_id": client_id,
            "transaction_id": transaction_id,
            "duration": duration,
            "machine_id": machine_id,
            "password": password,
            "last_payment": today.strftime("%Y-%m-%d"),
            "valid_until": valid_until.strftime("%Y-%m-%d"),
            "is_active": True
        }
        licenses_col.insert_one(license)
        flash(f"✅ License activated for {client_name}.", "success")
        return redirect(url_for("admin_dashboard"))


    return render_template("activate.html", already_activated=False)

@app.route('/deactivate/<client_id>')
def deactivate(client_id):
    licenses_col.update_one({"client_id": client_id}, {"$set": {"is_active": False}})
    flash(f"Client {client_id} deactivated.", "warning")
    return redirect(url_for("admin_dashboard"))

@app.route('/activate/<client_id>')
def reactivate(client_id):
    today = datetime.today()
    valid_until = today + timedelta(days=30)

    licenses_col.update_one(
        {"client_id": client_id},
        {"$set": {
            "is_active": True,
            "last_payment": today.strftime("%Y-%m-%d"),
            "valid_until": valid_until.strftime("%Y-%m-%d")
        }}
    )
    flash(f"Client {client_id} reactivated for 30 days.", "success")
    return redirect(url_for("admin_dashboard"))

@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=5000)
