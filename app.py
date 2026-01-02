from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import mysql.connector
import joblib
import pandas as pd
import numpy as np
import requests
from werkzeug.security import generate_password_hash, check_password_hash


from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="Y"
)

def ask_openrouter(question):
    try:
        response = client.chat.completions.create(
            model="deepseek/deepseek-chat:free",  # Correct free model
            messages=[
                {"role": "user", "content": question}
            ]
        )

        # Return AI response
        # Note: structure may vary; adapt if response path differs
        return response.choices[0].message.content

    except Exception as e:
        return f"API Error: {str(e)}"

app = Flask(__name__)
app.secret_key = "mysecretkey"


# ================== DATABASE CONFIG ==================
def get_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="Ghaneshwar!2001",
        database="medi_guide",
        autocommit=True  # we'll commit explicitly where needed
    )


# ================== ML MODEL ==================
# If these files don't exist locally, these lines will raise errors.
# Keep them if you have the model and data files in project root.
model = joblib.load("disease_prediction_model.model")
data = pd.read_csv("disease.csv")
if "diseases" in data.columns:
    data.drop(columns=["diseases"], inplace=True)
columns = data.columns.to_list()


# ================== ROUTES ==================
@app.route("/")
def home():
    return render_template("home.html")


# ================ BASIC SEARCH (search.html) ================
# This route expects GET params: ?hospital=...&pincode=...
@app.route("/search")
def basic_search():
    hospital_name = request.args.get('hospital', '').strip()
    pincode = request.args.get('pincode', '').strip()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        query = "SELECT * FROM hospitals WHERE 1=1"
        params = []

        if hospital_name:
            query += " AND LOWER(name) LIKE LOWER(%s)"
            params.append(hospital_name + "%")

        if pincode:
            query += " AND pincode = %s"
            params.append(pincode)

        # If no filters provided, we can either return empty list or all hospitals.
        # Current behavior: if no input -> show empty (consistent with previous)
        if not params:
            hospitals = []
        else:
            cursor.execute(query, tuple(params))
            hospitals = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template('search.html', hospitals=hospitals)


# ================== DISEASE PAGE ==================
@app.route("/disease")
def disease_page():
    return render_template("disease.html")


# ================== PREDICTION ==================
@app.route("/predict", methods=["POST"])
def predict():
    user_data = request.get_json()
    selected_symptoms = user_data.get("symptoms", [])

    input_vector = [1 if col in selected_symptoms else 0 for col in columns]
    prediction = model.predict([input_vector])[0]

    return jsonify({"prediction": prediction})


# ================== CHATBOT ==================
@app.route("/chatbot")
def chatbot_page():
    return render_template("chatbot.html")


@app.route("/ask_bot", methods=["POST"])
def ask_bot():
    data = request.get_json()
    question = data.get("question", "")

    if not question.strip():
        return jsonify({"answer": "Please write a question."})

    # Ask OpenRouter model
    answer = ask_openrouter(question)

    return jsonify({"answer": answer})


# ================== REGISTER ==================
@app.route("/hospital/register", methods=["GET", "POST"])
def hospital_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        raw_password = request.form.get("password", "")

        if not (name and email and phone and raw_password):
            flash("Please fill all required fields.", "danger")
            return redirect(url_for("hospital_register"))

        password = generate_password_hash(raw_password)

        conn = get_connection()
        cursor = conn.cursor()

        try:
            # check existing account
            cursor.execute("SELECT id FROM hospital_accounts WHERE email=%s", (email,))
            if cursor.fetchone():
                flash("Email already registered!", "danger")
                return redirect(url_for("hospital_register"))

            cursor.execute(
                "INSERT INTO hospital_accounts (name, email, phone, password) VALUES (%s, %s, %s, %s)",
                (name, email, phone, password)
            )
            account_id = cursor.lastrowid

            # create hospitals row with minimal data
            cursor.execute(
                "INSERT INTO hospitals (account_id, name) VALUES (%s, %s)",
                (account_id, name)
            )

            conn.commit()
            flash("Registration Successful! Please login.", "success")
            return redirect(url_for("hospital_login"))

        except Exception as e:
            conn.rollback()
            flash("Registration failed: " + str(e), "danger")
            return redirect(url_for("hospital_register"))

        finally:
            cursor.close()
            conn.close()

    return render_template("hospital_register.html")


# ================== LOGIN ==================
@app.route("/hospital/login", methods=["GET", "POST"])
def hospital_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("SELECT * FROM hospital_accounts WHERE email=%s", (email,))
            user = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

        if user and check_password_hash(user["password"], password):
            session["hospital_id"] = user["id"]
            session["hospital_name"] = user["name"]
            return redirect(url_for("hospital_dashboard"))

        flash("Invalid credentials", "danger")
        return redirect(url_for("hospital_login"))

    return render_template("hospital_login.html")


# ================== DASHBOARD ==================
@app.route("/hospital/dashboard")
def hospital_dashboard():
    if "hospital_id" not in session:
        return redirect(url_for("hospital_login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT name, total_beds, available_beds, bed_charge, emergency_available
            FROM hospitals
            WHERE account_id = %s
        """, (session["hospital_id"],))
        hospital = cursor.fetchone()
    finally:
        cursor.close()
        conn.close()

    if not hospital:
        # fallback defaults to avoid template errors
        hospital = {"name": "Hospital", "total_beds": 0, "available_beds": 0, "bed_charge": 0, "emergency_available": 0}

    return render_template(
        "hospital_dashboard.html",
        hospital_name=hospital.get("name", "Hospital"),
        total_beds=hospital.get("total_beds", 0),
        available_beds=hospital.get("available_beds", 0),
        bed_charge=hospital.get("bed_charge", 0),
        emergency_available=hospital.get("emergency_available", 0)
    )


# ================== PROFILE ==================
@app.route("/hospital/profile", methods=["GET", "POST"])
def hospital_profile():

    if "hospital_id" not in session:
        return redirect(url_for("hospital_login"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        if request.method == "POST":
            fields = (
                "name", "address", "pincode", "speciality", "ayushman_supported",
                "phone", "email", "total_beds", "available_beds", "bed_charge",
                "ambulance_available", "emergency_available",
                "opening_time", "closing_time"
            )

            # Build values safely (missing keys will raise KeyError — you may want to default)
            values = tuple(request.form.get(f, "") for f in fields)

            update_query = f"""
                UPDATE hospitals SET
                    {", ".join([f"{f}=%s" for f in fields])}
                WHERE account_id=%s
            """

            cursor.execute(update_query, values + (session["hospital_id"],))
            conn.commit()

            return redirect(url_for("hospital_dashboard"))

        # GET
        cursor.execute("SELECT * FROM hospitals WHERE account_id=%s", (session["hospital_id"],))
        hospital = cursor.fetchone()

    finally:
        cursor.close()
        conn.close()

    return render_template("hospital_profile.html", hospital=hospital)


# ================== LOGOUT ==================
@app.route("/hospital/logout")
def hospital_logout():
    session.clear()
    return redirect(url_for("hospital_login"))


@app.route("/hospital-search", methods=["GET"])
def hospital_search_page():
    return render_template("hospital_search.html")


# ================ ADVANCED SEARCH RESULT ================
@app.route("/hospital-search/result", methods=["GET"])
def hospital_search_result():

    # IMPORTANT → request.args (GET method)
    name = request.args.get('name', '').strip()
    pincode = request.args.get('pincode', '').strip()
    speciality = request.args.get('speciality', '').strip()
    ayushman = request.args.get('ayushman', '').strip()
    ambulance = request.args.get('ambulance', '').strip()
    emergency = request.args.get('emergency', '').strip()

    query = "SELECT * FROM hospitals WHERE 1=1"
    params = []

    if name:
        query += " AND name LIKE %s"
        params.append("%" + name + "%")

    if pincode:
        query += " AND pincode = %s"
        params.append(pincode)

    if speciality:
        query += " AND speciality LIKE %s"
        params.append("%" + speciality + "%")

    if ayushman:
        query += " AND ayushman_supported = %s"
        params.append(1)

    if ambulance:
        query += " AND ambulance_available = %s"
        params.append(1)

    if emergency:
        query += " AND emergency_available = %s"
        params.append(1)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(query, tuple(params))
        hospitals = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template("hospital_search.html", hospitals=hospitals)



if __name__ == "__main__":
    app.run(debug=True)
