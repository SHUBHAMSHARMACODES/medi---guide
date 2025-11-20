from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import mysql.connector
import joblib
import pandas as pd
import numpy as np
import requests
from werkzeug.security import generate_password_hash, check_password_hash


# ================== OPENROUTER FREE MODEL CONFIG ==================
from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="YOUR_API_KEY_HERE"
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
        autocommit=True
    )


# ================== OPENROUTER FREE MODEL CONFIG ==================


# ================== ML MODEL ==================
model = joblib.load("disease_prediction_model.model")
data = pd.read_csv("disease.csv")
data.drop(columns=["diseases"], inplace=True)
columns = data.columns.to_list()


# ================== ROUTES ==================
@app.route("/")
def home():
    return render_template("home.html")


# ================== SEARCH ==================
@app.route("/search")
def search():
    hospital_name = request.args.get('hospital', '').strip()
    pincode = request.args.get('pincode', '').strip()

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if pincode and not hospital_name:
        cursor.execute("SELECT * FROM hospitals WHERE pincode = %s", (pincode,))

    elif hospital_name and not pincode:
        cursor.execute("SELECT * FROM hospitals WHERE LOWER(name) LIKE LOWER(%s)", (f"{hospital_name}%",))

    elif pincode and hospital_name:
        cursor.execute(
            "SELECT * FROM hospitals WHERE pincode = %s AND LOWER(name) LIKE LOWER(%s)",
            (pincode, f"{hospital_name}%")
        )

    else:
        cursor.close()
        conn.close()
        return render_template('search.html', hospitals=[])

    result = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template('search.html', hospitals=result)


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
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = generate_password_hash(request.form["password"])

        conn = get_connection()
        cursor = conn.cursor(buffered=True)

        cursor.execute("SELECT id FROM hospital_accounts WHERE email=%s", (email,))
        if cursor.fetchone():
            flash("Email already registered!", "danger")
            return redirect(url_for("hospital_register"))

        cursor.execute("""
            INSERT INTO hospital_accounts (name, email, phone, password)
            VALUES (%s, %s, %s, %s)
        """, (name, email, phone, password))

        account_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO hospitals (account_id, name)
            VALUES (%s, %s)
        """, (account_id, name))

        cursor.close()
        conn.close()

        flash("Registration Successful! Please login.", "success")
        return redirect(url_for("hospital_login"))

    return render_template("hospital_register.html")


# ================== LOGIN ==================
@app.route("/hospital/login", methods=["GET", "POST"])
def hospital_login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM hospital_accounts WHERE email=%s", (email,))
        user = cursor.fetchone()

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

    cursor.execute("""
        SELECT name, total_beds, available_beds, bed_charge, emergency_available
        FROM hospitals 
        WHERE account_id = %s
    """, (session["hospital_id"],))

    hospital = cursor.fetchone()

    cursor.close()
    conn.close()

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

    if request.method == "POST":

        fields = (
            "name", "address", "pincode", "speciality", "ayushman_supported",
            "phone", "email", "total_beds", "available_beds", "bed_charge",
            "ambulance_available", "emergency_available",
            "opening_time", "closing_time"
        )

        values = tuple(request.form[f] for f in fields)

        update_query = f"""
            UPDATE hospitals SET
                {", ".join([f"{f}=%s" for f in fields])}
            WHERE account_id=%s
        """

        cursor.execute(update_query, values + (session["hospital_id"],))

        cursor.close()
        conn.close()

        return redirect(url_for("hospital_dashboard"))

    cursor.execute("SELECT * FROM hospitals WHERE account_id=%s", (session["hospital_id"],))
    hospital = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("hospital_profile.html", hospital=hospital)


# ================== LOGOUT ==================
@app.route("/hospital/logout")
def hospital_logout():
    session.clear()
    return redirect(url_for("hospital_login"))


# ================== MAIN ==================
if __name__ == "__main__":
    app.run(debug=True)
