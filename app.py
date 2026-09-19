from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
import psycopg
from psycopg.rows import dict_row
from werkzeug.security import generate_password_hash, check_password_hash

from pathlib import Path
app = Flask(__name__)
app.secret_key = "blogger-change-this-secret-key"

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")



PLANS = {
    "starter": {
        "number": "01",
        "name": "Starter",
        "amount": 7000,
        "daily": 1000
    },
    "standard": {
        "number": "02",
        "name": "Standard",
        "amount": 15000,
        "daily": 2700
    },
    "growth": {
        "number": "03",
        "name": "Growth",
        "amount": 30000,
        "daily": 5300
    },
    "advanced": {
        "number": "04",
        "name": "Advanced",
        "amount": 45000,
        "daily": 8500
    },
    "elite": {
        "number": "05",
        "name": "Elite",
        "amount": 70000,
        "daily": 10000
    },
    "ultimate": {
        "number": "06",
        "name": "Ultimate",
        "amount": 100000,
        "daily": 15000
    }
}

def get_db():
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return conn


def init_db():
    db = get_db()

    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            fullname TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            referral_code TEXT NOT NULL UNIQUE,
            referred_by INTEGER,
            balance DOUBLE PRECISION NOT NULL DEFAULT 700,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS user_plans (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            plan_id TEXT NOT NULL,
            plan_name TEXT NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            daily_amount DOUBLE PRECISION NOT NULL,
            status TEXT NOT NULL DEFAULT 'Active',
            activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS daily_bonuses (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount DOUBLE PRECISION NOT NULL DEFAULT 50,
            claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS deposits (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            payment_method TEXT NOT NULL,
            payment_name TEXT NOT NULL,
            screenshot TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            admin_note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            amount DOUBLE PRECISION NOT NULL,
            method TEXT NOT NULL DEFAULT 'Bank Transfer',
            account_name TEXT NOT NULL,
            account_number TEXT NOT NULL,
            bank_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    db.commit()
    db.close()

# Add admin flag to existing users table if needed
def ensure_admin_column():
    db = get_db()

    column = db.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'is_admin'
        LIMIT 1
    """).fetchone()

    if not column:
        db.execute("""
            ALTER TABLE users
            ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0
        """)
        db.commit()

    db.close()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        referral = request.form.get("referral", "").strip()

        if not fullname or not username or not email or not password:
            flash("Please complete all required fields.")
            return redirect(url_for("register"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.")
            return redirect(url_for("register"))

        referral_code = username.upper()

        referral_code_from_link = request.args.get("ref", "").strip().upper()

        conn = get_db()

        referred_by = None

        if referral_code_from_link:
            referrer = conn.execute("""
                SELECT id
                FROM users
                WHERE referral_code = %s
                LIMIT 1
            """, (referral_code_from_link,)).fetchone()

            if referrer:
                referred_by = referrer["id"]

        try:
            conn.execute("""
                INSERT INTO users
                (fullname, username, email, password, referral_code, referred_by)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                fullname,
                username,
                email,
                generate_password_hash(password),
                referral_code,
                referred_by
            ))

            conn.commit()

        except psycopg.IntegrityError:
            conn.close()
            flash("Username or email already exists.")
            return redirect(url_for("register"))

        conn.close()

        flash("Account created successfully. Please login.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db()

        user = conn.execute("""
            SELECT * FROM users
            WHERE username = %s OR email = %s
        """, (username, username)).fetchone()

        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]

            return redirect(url_for("dashboard"))

        flash("Invalid username/email or password.")

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    user = conn.execute(
        "SELECT * FROM users WHERE id = %s",
        (session["user_id"],)
    ).fetchone()

    active_plans = conn.execute("""
        SELECT *
        FROM user_plans
        WHERE user_id = %s
          AND status = 'Active'
        ORDER BY id DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        user=user,
        active_plans=active_plans
    )



@app.route("/activate-plan/<plan_id>", methods=["POST"])
def activate_plan(plan_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    selected_plan = PLANS.get(plan_id)

    if not selected_plan:
        flash("Plan not found.", "error")
        return redirect(url_for("dashboard"))

    db = get_db()
    user_id = session["user_id"]

    user = db.execute("""
        SELECT balance
        FROM users
        WHERE id = %s
    """, (user_id,)).fetchone()

    balance = float(user["balance"] or 0)

    existing = db.execute("""
        SELECT id
        FROM user_plans
        WHERE user_id = %s
          AND plan_id = %s
          AND status = 'Active'
        LIMIT 1
    """, (user_id, plan_id)).fetchone()

    if existing:
        db.close()
        flash("This plan is already active.", "error")
        return redirect(url_for("plan", plan_id=plan_id))

    if balance < selected_plan["amount"]:
        db.close()
        flash(
            f"Insufficient balance. You need ₦{selected_plan['amount']:,.2f} "
            f"but your available balance is ₦{balance:,.2f}.",
            "error"
        )
        return redirect(url_for("plan", plan_id=plan_id))

    db.execute("""
        UPDATE users
        SET balance = balance - %s
        WHERE id = %s
    """, (selected_plan["amount"], user_id))

    db.execute("""
        INSERT INTO user_plans
        (user_id, plan_id, plan_name, amount, daily_amount, status)
        VALUES (%s, %s, %s, %s, %s, 'Active')
    """, (
        user_id,
        plan_id,
        selected_plan["name"],
        selected_plan["amount"],
        selected_plan["daily"]
    ))


    # Demo referral credit: 20% of the activated package amount
    referral_info = db.execute("""
        SELECT referred_by
        FROM users
        WHERE id = %s
    """, (user_id,)).fetchone()

    if referral_info and referral_info["referred_by"]:
        referral_bonus = selected_plan["amount"] * 0.20

        db.execute("""
            UPDATE users
            SET balance = COALESCE(balance, 0) + %s
            WHERE id = %s
        """, (
            referral_bonus,
            referral_info["referred_by"]
        ))

    db.commit()
    db.close()

    flash(
        f"{selected_plan['name']} plan activated successfully! "
        f"₦{selected_plan['amount']:,.2f} has been deducted from your balance.",
        "success"
    )

    return redirect(url_for("dashboard"))

@app.route("/plan/<plan_id>")
def plan(plan_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    selected_plan = PLANS.get(plan_id)

    if not selected_plan:
        return redirect(url_for("dashboard"))

    return render_template(
        "plan.html",
        plan=selected_plan,
        plan_id=plan_id
    )



@app.route("/daily-bonus", methods=["GET", "POST"])
def daily_bonus():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    user_id = session["user_id"]

    if request.method == "POST":
        last_claim = db.execute("""
            SELECT id
            FROM daily_bonuses
            WHERE user_id = %s
              AND claimed_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ORDER BY id DESC
            LIMIT 1
        """, (user_id,)).fetchone()

        if last_claim:
            flash(
                "You have already claimed your ₦50 daily bonus. Please come back after 24 hours.",
                "error"
            )
            return redirect(url_for("daily_bonus"))

        db.execute("""
            UPDATE users
            SET balance = COALESCE(balance, 0) + 50
            WHERE id = %s
        """, (user_id,))

        db.execute("""
            INSERT INTO daily_bonuses (user_id, amount, claimed_at)
            VALUES (%s, 50, CURRENT_TIMESTAMP)
        """, (user_id,))

        db.commit()

        flash("₦50 daily bonus added to your balance successfully!", "success")
        return redirect(url_for("daily_bonus"))

    last_claim = db.execute("""
        SELECT id
        FROM daily_bonuses
        WHERE user_id = %s
          AND claimed_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,)).fetchone()

    can_claim = last_claim is None

    user = db.execute("""
        SELECT balance
        FROM users
        WHERE id = %s
    """, (user_id,)).fetchone()

    balance = float(user["balance"] or 0)

    history = db.execute("""
        SELECT amount, claimed_at
        FROM daily_bonuses
        WHERE user_id = %s
        ORDER BY id DESC
        LIMIT 10
    """, (user_id,)).fetchall()

    return render_template(
        "daily_bonus.html",
        can_claim=can_claim,
        history=history,
        balance=balance
    )


@app.route("/withdraw", methods=["GET", "POST"])
def withdraw():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    user_id = session["user_id"]

    user = db.execute("""
        SELECT balance
        FROM users
        WHERE id = %s
    """, (user_id,)).fetchone()

    balance = float(user["balance"] or 0)

    if request.method == "POST":
        amount_text = request.form.get("amount", "").strip()
        account_name = request.form.get("account_name", "").strip()
        account_number = request.form.get("account_number", "").strip()
        bank_name = request.form.get("bank_name", "").strip()

        try:
            amount = float(amount_text)
        except (ValueError, TypeError):
            amount = 0

        if amount < 1500:
            flash("Minimum withdrawal amount is ₦1,500.", "error")
            return redirect(url_for("withdraw"))

        if not all([account_name, account_number, bank_name]):
            flash("Please complete all withdrawal details.", "error")
            return redirect(url_for("withdraw"))

        if amount > balance:
            flash(
                f"Insufficient balance. Your available balance is ₦{balance:,.2f}.",
                "error"
            )
            return redirect(url_for("withdraw"))

        db.execute("""
            INSERT INTO withdrawals
            (user_id, amount, method, account_name, account_number, bank_name)
            VALUES (%s, %s, 'Bank Transfer', %s, %s, %s)
        """, (
            user_id,
            amount,
            account_name,
            account_number,
            bank_name
        ))

        db.execute("""
            UPDATE users
            SET balance = balance - %s
            WHERE id = %s
        """, (amount, user_id))

        db.commit()

        flash("Withdrawal request submitted successfully and is now Pending.", "success")
        return redirect(url_for("withdraw"))

    withdrawals = db.execute("""
        SELECT *
        FROM withdrawals
        WHERE user_id = %s
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    return render_template(
        "withdraw.html",
        withdrawals=withdrawals,
        balance=balance
    )



@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        db = get_db()
        admin = db.execute("""
            SELECT id, username, password, is_admin
            FROM users
            WHERE username = %s
              AND is_admin = 1
            LIMIT 1
        """, (username,)).fetchone()
        db.close()

        if admin and check_password_hash(admin["password"], password):
            session["admin_id"] = admin["id"]
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin login details.", "error")

    return render_template("admin_login.html")


@app.route("/admin")
def admin_dashboard():
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    db = get_db()

    deposits = db.execute("""
        SELECT
            deposits.*,
            users.fullname,
            users.username,
            users.email
        FROM deposits
        JOIN users ON users.id = deposits.user_id
        ORDER BY deposits.id DESC
    """).fetchall()

    withdrawals = db.execute("""
        SELECT
            withdrawals.*,
            users.fullname,
            users.username,
            users.email
        FROM withdrawals
        JOIN users ON users.id = withdrawals.user_id
        ORDER BY withdrawals.id DESC
    """).fetchall()

    db.close()

    return render_template(
        "admin.html",
        deposits=deposits,
        withdrawals=withdrawals
    )


@app.route("/admin/deposit/<int:deposit_id>/approve", methods=["POST"])
def approve_deposit(deposit_id):
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    db = get_db()

    deposit = db.execute("""
        SELECT *
        FROM deposits
        WHERE id = %s AND status = 'Pending'
    """, (deposit_id,)).fetchone()

    if not deposit:
        db.close()
        flash("Deposit is no longer pending.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute("""
        UPDATE users
        SET balance = COALESCE(balance, 0) + %s
        WHERE id = %s
    """, (deposit["amount"], deposit["user_id"]))

    db.execute("""
        UPDATE deposits
        SET status = 'Approved',
            admin_note = 'Deposit approved',
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = %s AND status = 'Pending'
    """, (deposit_id,))

    db.commit()
    db.close()

    flash("Deposit approved and user balance credited.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/deposit/<int:deposit_id>/reject", methods=["POST"])
def reject_deposit(deposit_id):
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("Please provide a rejection reason.", "error")
        return redirect(url_for("admin_dashboard"))

    db = get_db()

    deposit = db.execute("""
        SELECT id
        FROM deposits
        WHERE id = %s AND status = 'Pending'
    """, (deposit_id,)).fetchone()

    if not deposit:
        db.close()
        flash("Deposit is no longer pending.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute("""
        UPDATE deposits
        SET status = 'Rejected',
            admin_note = %s,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = %s AND status = 'Pending'
    """, (reason, deposit_id))

    db.commit()
    db.close()

    flash("Deposit rejected.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/withdrawal/<int:withdrawal_id>/approve", methods=["POST"])
def approve_withdrawal(withdrawal_id):
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    db = get_db()

    withdrawal = db.execute("""
        SELECT *
        FROM withdrawals
        WHERE id = %s AND status = 'Pending'
    """, (withdrawal_id,)).fetchone()

    if not withdrawal:
        db.close()
        flash("Withdrawal is no longer pending.", "error")
        return redirect(url_for("admin_dashboard"))

    db.execute("""
        UPDATE withdrawals
        SET status = 'Approved'
        WHERE id = %s AND status = 'Pending'
    """, (withdrawal_id,))

    db.commit()
    db.close()

    flash("Withdrawal approved.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/withdrawal/<int:withdrawal_id>/reject", methods=["POST"])
def reject_withdrawal(withdrawal_id):
    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("Please provide a rejection reason.", "error")
        return redirect(url_for("admin_dashboard"))

    db = get_db()

    withdrawal = db.execute("""
        SELECT *
        FROM withdrawals
        WHERE id = %s AND status = 'Pending'
    """, (withdrawal_id,)).fetchone()

    if not withdrawal:
        db.close()
        flash("Withdrawal is no longer pending.", "error")
        return redirect(url_for("admin_dashboard"))

    # Return the previously reserved amount to the user
    db.execute("""
        UPDATE users
        SET balance = COALESCE(balance, 0) + %s
        WHERE id = %s
    """, (withdrawal["amount"], withdrawal["user_id"]))

    db.execute("""
        UPDATE withdrawals
        SET status = 'Rejected'
        WHERE id = %s AND status = 'Pending'
    """, (withdrawal_id,))

    db.commit()
    db.close()

    flash("Withdrawal rejected and amount returned to user balance.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_id", None)
    return redirect(url_for("admin_login"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


init_db()




@app.route("/deposit", methods=["GET", "POST"])
def deposit():
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    user_id = session["user_id"]

    if request.method == "POST":
        amount_text = request.form.get("amount", "").strip()
        payment_name = request.form.get("payment_name", "").strip()
        screenshot = request.files.get("screenshot")

        try:
            amount = float(amount_text)
        except (ValueError, TypeError):
            amount = 0

        if amount < 7000:
            flash("Minimum deposit amount is ₦7,000.", "error")
            return redirect(url_for("deposit"))

        if not payment_name:
            flash("Please enter the payment name.", "error")
            return redirect(url_for("deposit"))

        if not screenshot or not screenshot.filename:
            flash("Please upload your transaction screenshot.", "error")
            return redirect(url_for("deposit"))

        allowed = {"png", "jpg", "jpeg", "webp"}

        filename = screenshot.filename
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

        if extension not in allowed:
            flash("Please upload a PNG, JPG, JPEG, or WEBP screenshot.", "error")
            return redirect(url_for("deposit"))

        import uuid

        safe_filename = f"{uuid.uuid4().hex}.{extension}"
        upload_dir = Path(app.root_path) / "static" / "uploads" / "deposits"
        upload_dir.mkdir(parents=True, exist_ok=True)
        screenshot.save(str(upload_dir / safe_filename))

        db.execute("""
            INSERT INTO deposits
            (user_id, amount, payment_method, payment_name, screenshot, status)
            VALUES (%s, %s, %s, %s, %s, 'Pending')
        """, (
            user_id,
            amount,
            "Manual Payment",
            payment_name,
            safe_filename
        ))

        db.commit()

        flash("Deposit submitted successfully. It is now Pending admin approval.", "success")
        return redirect(url_for("deposit"))

    deposits = db.execute("""
        SELECT *
        FROM deposits
        WHERE user_id = %s
        ORDER BY id DESC
    """, (user_id,)).fetchall()

    return render_template(
        "deposit.html",
        deposits=deposits
    )



@app.route("/claim-package-reward/<int:plan_id>", methods=["POST"])
def claim_package_reward(plan_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    user_id = session["user_id"]

    plan = db.execute("""
        SELECT *
        FROM user_plans
        WHERE id = %s
          AND user_id = %s
          AND status = 'Active'
        LIMIT 1
    """, (plan_id, user_id)).fetchone()

    if not plan:
        db.close()
        flash("Active package not found.", "error")
        return redirect(url_for("dashboard"))

    recent_claim = db.execute("""
        SELECT id
        FROM package_rewards
        WHERE user_id = %s
          AND user_plan_id = %s
          AND claimed_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
        LIMIT 1
    """, (user_id, plan_id)).fetchone()

    if recent_claim:
        db.close()
        flash(
            "You have already claimed this package reward. "
            "Please come back after 24 hours.",
            "error"
        )
        return redirect(url_for("dashboard"))

    reward = float(plan["daily_amount"])

    db.execute("""
        UPDATE users
        SET balance = COALESCE(balance, 0) + %s
        WHERE id = %s
    """, (reward, user_id))

    db.execute("""
        INSERT INTO package_rewards
        (user_id, user_plan_id, amount)
        VALUES (%s, %s, %s)
    """, (user_id, plan_id, reward))

    db.commit()
    db.close()

    flash(
        f"₦{reward:,.2f} package reward added to your balance.",
        "success"
    )

    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
