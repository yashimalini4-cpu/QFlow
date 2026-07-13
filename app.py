import requests
import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, session, redirect 
import mysql.connector
import re
import random

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# ---------------- DATABASE ---------------- #

db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT")),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    ssl_ca="certs/ca.pem"
)

print("Database Connected Successfully!")

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")


# ---------------- HOME ---------------- #

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/customer")
def customer():
    return render_template("customer_access.html")

# ---------------- ABOUT ---------------- #

@app.route("/about")
def about():
    return render_template("about.html")

# ---------------- CONTACT ---------------- #

@app.route("/contact")
def contact():
    return render_template("contact.html")

# ---------------- REGISTER ---------------- #
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        mobile = request.form["mobile"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]

        name_pattern = r"^[A-Za-z ]+$"
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        mobile_pattern = r"^[6-9]\d{9}$"

        if not re.match(name_pattern, full_name):
            return render_template(
                "register.html",
                name_error="Enter a valid name."
            )

        if not re.match(email_pattern, email):
            return render_template(
                "register.html",
                email_error="Enter a valid email."
            )

        if not re.match(mobile_pattern, mobile):
            return render_template(
                "register.html",
                mobile_error="Enter a valid 10-digit mobile number."
            )

        if len(password) < 4:
            return render_template(
                "register.html",
                password_error="Password must contain at least 4 characters."
            )

        if password != confirm_password:
            return render_template(
                "register.html",
                confirm_password_error="Passwords do not match."
            )

        cursor = db.cursor()

        cursor.execute(
            "SELECT * FROM customers WHERE email=%s",
            (email,)
        )

        existing_user = cursor.fetchone()

        if existing_user:
            cursor.close()
            return render_template(
                "register.html",
                email_error="Email already registered. Please login."
            )

        # Generate OTP
        otp = str(random.randint(100000, 999999))

        # Store details in session
        session["otp"] = otp
        session["full_name"] = full_name
        session["email"] = email
        session["mobile"] = mobile
        session["password"] = password

        # Send OTP using Brevo API
        headers = {
            "accept": "application/json",
            "api-key": os.getenv("BREVO_API_KEY"),
            "content-type": "application/json"
        }

        data = {
            "sender": {
                "name": "QFlow",
                "email": EMAIL_ADDRESS
            },
            "to": [
                {
                    "email": email
                }
            ],
            "subject": "QFlow Email Verification OTP",
            "textContent": f"""
Welcome to QFlow!

Your OTP for email verification is:

{otp}

This OTP is valid for this registration only.

Thank you,
Team QFlow
"""
        }

        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=data
        )

        if response.status_code not in [200, 201]:
            cursor.close()
            return f"Email sending failed: {response.text}", 500

        cursor.close()

        return redirect("/verify-otp")

    return render_template("register.html")

# ---------------- VERIFY OTP ---------------- #

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():

    if request.method == "POST":

        entered_otp = request.form["otp"]

        if entered_otp == session.get("otp"):

            cursor = db.cursor()

            cursor.execute(
                """
                INSERT INTO customers(full_name,email,mobile,password)
                VALUES(%s,%s,%s,%s)
                """,
                (
                    session["full_name"],
                    session["email"],
                    session["mobile"],
                    session["password"]
                )
            )

            db.commit()
            cursor.close()

            session.pop("otp", None)

            return """
            <h2 style='color:green;'>Email Verified Successfully!</h2>

            <br>

            <a href='/login'>Go to Login</a>
            """

        return render_template(
            "verify_otp.html",
            otp_error="Invalid OTP. Please try again."
        )

    return render_template("verify_otp.html")


# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM customers WHERE email=%s AND password=%s",
            (email, password)
        )

        user = cursor.fetchone()

        cursor.close()

        if user:
            session["email"] = user["email"]

            return redirect("/customer-dashboard")

        return render_template(
            "login.html",
            login_password_error="Invalid Email or Password."
        )

    return render_template("login.html")

# ---------------- CUSTOMER DASHBOARD ---------------- #

@app.route("/customer-dashboard")
def customer_dashboard():

    if "email" not in session:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT full_name FROM customers WHERE email=%s",
        (session["email"],)
    )

    user = cursor.fetchone()

    cursor.close()

    return render_template(
        "customer_dashboard.html",
        name=user["full_name"]
    )


# ---------------- BOOK TOKEN ---------------- #

@app.route("/book-token", methods=["GET", "POST"])
def book_token():

    if request.method == "POST":

        organization = request.form["organization"]
        department = request.form["department"]

        #Customer email
        customer_email = session.get("email")

        cursor = db.cursor()

        # Check if customer already has an active token
        cursor.execute(
            """
            SELECT token_number
            FROM tokens
            WHERE customer_email=%s
            AND organization=%s
            AND department=%s
            AND status='Waiting'
            """,
            (customer_email, organization, department)
        )

        existing_token = cursor.fetchone()

        if existing_token:

            cursor.close()

            return f"""
            <h2>You already have an active token.</h2>

            <p><b>Token Number:</b> {existing_token[0]}</p>

            <br>

            <a href="/book-token">Back</a>
            """

        # Generate next token number
        cursor.execute(
            """
            SELECT MAX(token_number)
            FROM tokens
            WHERE organization=%s
            AND department=%s
            """,
            (organization, department)
        )

        result = cursor.fetchone()

        if result[0] is None:
            token_number = 1
        else:
            token_number = result[0] + 1

        # Save token
        cursor.execute(
            """
            INSERT INTO tokens
            (customer_email, organization, department, token_number, status)
            VALUES (%s,%s,%s,%s,%s)
            """,
            (
                customer_email,
                organization,
                department,
                token_number,
                "Waiting"
            )
        )

        db.commit()
        cursor.close()

        return render_template(
          "token.html",
           token_number=token_number,
           customer_email=customer_email,
           organization=organization,
           department=department,
           status="Waiting"
        )

    return render_template("book_token.html")

# ---------------- MY TOKEN ---------------- #

@app.route("/my-token")
def my_token():

    customer_email = session.get("email")

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM tokens
        WHERE customer_email=%s
        AND status='Waiting'
        ORDER BY token_id DESC
        LIMIT 1
        """,
        (customer_email,)
    )

    token = cursor.fetchone()

    cursor.close()

    if token:

        return render_template(
            "token.html",
            token_number=token["token_number"],
            customer_email=token["customer_email"],
            organization=token["organization"],
            department=token["department"],
            status=token["status"]
        )

    return """
    <h2>No Active Token Found.</h2>

    <br>

    <a href="/book-token">Book a Token</a>
    """

# ---------------- QUEUE STATUS ---------------- #

@app.route("/queue-status")
def queue_status():

    customer_email = session.get("email")

    if not customer_email:
        return redirect("/login")

    cursor = db.cursor(dictionary=True)

    # Get customer's active token
    cursor.execute(
        """
        SELECT *
        FROM tokens
        WHERE customer_email=%s
        AND status='Waiting'
        ORDER BY token_id DESC
        LIMIT 1
        """,
        (customer_email,)
    )

    token = cursor.fetchone()

    if not token:
        cursor.close()
        return """
        <h2>No Active Token Found.</h2>

        <br>

        <a href="/book-token">Book a Token</a>
        """

    # Count people ahead
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM tokens
        WHERE organization=%s
        AND department=%s
        AND status='Waiting'
        AND token_number < %s
        """,
        (
            token["organization"],
            token["department"],
            token["token_number"]
        )
    )

    people_result = cursor.fetchone()
    people_ahead = people_result["COUNT(*)"]

    waiting_time = people_ahead * 5

    # Current token being served
    cursor.execute(
        """
        SELECT MAX(token_number)
        FROM tokens
        WHERE organization=%s
        AND department=%s
        AND status='Completed'
        """,
        (
            token["organization"],
            token["department"]
        )
    )

    current_result = cursor.fetchone()
    current_token = current_result["MAX(token_number)"]

    if current_token is None:
        current_token = 0

    # Progress Percentage
    progress = int((current_token / token["token_number"]) * 100)

    if progress > 100:
        progress = 100

    cursor.close()

    return render_template(
        "queue_status.html",
        token_number=token["token_number"],
        people_ahead=people_ahead,
        waiting_time=waiting_time,
        status=token["status"],
        current_token=current_token,
        progress=progress
    )

# ---------------- VIEW WAITING TOKENS ---------------- #

@app.route("/view-tokens")
def view_tokens():

    organization = session.get("organization")

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM tokens
        WHERE organization=%s
        AND status='Waiting'
        ORDER BY token_number
        """,
        (organization,)
    )

    tokens = cursor.fetchall()

    cursor.close()

    return render_template(
        "view_tokens.html",
        tokens=tokens
    )

# ---------------- CALL NEXT TOKEN ---------------- #

@app.route("/call-next-token")
def call_next_token():

    organization = session.get("organization")

    cursor = db.cursor(dictionary=True)

    # Get the first waiting token
    cursor.execute(
        """
        SELECT *
        FROM tokens
        WHERE organization=%s
        AND status='Waiting'
        ORDER BY token_number
        LIMIT 1
        """,
        (organization,)
    )

    token = cursor.fetchone()

    if not token:
        cursor.close()
        return """
        <h2>No Waiting Tokens</h2>
        <br>
        <a href="/organization">Back to Dashboard</a>
        """

   
    # First remove any previously called token
    cursor.execute("""
    UPDATE tokens
    SET status='Completed'
    WHERE organization=%s
    AND status='Called'
    """, (organization,))

    # Now call the next waiting token
    cursor.execute("""
    UPDATE tokens
    SET status='Called'
    WHERE token_id=%s
    """, (token["token_id"],))

    db.commit()
    cursor.close()

    return f"""
    <h2>Next Token Called Successfully!</h2>

    <h3>Token Number: {token['token_number']}</h3>

    <p><b>Customer:</b> {token['customer_email']}</p>

    <p><b>Department:</b> {token['department']}</p>

    <p><b>Status:</b> Completed</p>

    <br>

    <a href="/view-tokens">View Waiting Tokens</a>
    """
# ---------------- ORGANIZATION DASHBOARD ---------------- #

@app.route("/organization-dashboard")
def organization_dashboard():

    if "organization" not in session:
        return redirect("/organization")

    return render_template(
        "organization_dashboard.html",
        organization=session["organization"]
    )

# ---------------- ORGANIZATION LOGIN ---------------- #

@app.route("/organization", methods=["GET", "POST"])
def organization():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT *
            FROM organizations
            WHERE email=%s AND password=%s
            """,
            (email, password)
        )

        admin = cursor.fetchone()

        cursor.close()

        if admin:

            session["organization"] = admin["organization_name"]

            return redirect("/organization-dashboard")

        return render_template(
            "organization_login.html",
            login_error="Invalid Email or Password."
        )

    return render_template("organization_login.html")

# ---------------- COMPLETED TOKENS ---------------- #

@app.route("/completed-tokens")
def completed_tokens():

    organization = session.get("organization")

    cursor = db.cursor(dictionary=True)

    cursor.execute(
        """
        SELECT *
        FROM tokens
        WHERE organization=%s
        AND status='Completed'
        ORDER BY token_number DESC
        """,
        (organization,)
    )

    completed = cursor.fetchall()

    cursor.close()

    return render_template(
        "completed_tokens.html",
        completed=completed
    )


# ---------------- RUN APP ---------------- #

import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)