import sqlite3

from flask import flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from config import DEFAULT_ROLE, EMAIL_PATTERN, REQUIRED_MSG
from core import app, get_db

# ---------------------------------------------------------------
# Registracija, prisijungimas, atsijungimas
# ---------------------------------------------------------------




@app.route("/")
def index():
    if g.user:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard"))

    form = {"full_name": "", "email": ""}
    errors = {}

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        form = {"full_name": full_name, "email": email}

        # 1) Privalomi laukai
        if not full_name:
            errors["full_name"] = REQUIRED_MSG
        if not email:
            errors["email"] = REQUIRED_MSG
        if not password:
            errors["password"] = REQUIRED_MSG
        if not confirm_password:
            errors["confirm_password"] = REQUIRED_MSG

        # 2) Formato patikra (tik jei laukas užpildytas)
        if "full_name" not in errors and len(full_name) < 2:
            errors["full_name"] = "Įveskite vardą ir pavardę (bent 2 simboliai)."

        if "email" not in errors and not EMAIL_PATTERN.match(email):
            errors["email"] = "Įveskite teisingą el. pašto adresą."

        if "password" not in errors and len(password) < 8:
            errors["password"] = "Slaptažodis turi būti bent 8 simbolių ilgio."

        if "confirm_password" not in errors and confirm_password != password:
            errors["confirm_password"] = "Slaptažodžiai nesutampa."

        # 3) El. paštas turi būti unikalus
        if "email" not in errors:
            existing = get_db().execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                errors["email"] = "Paskyra su šiuo el. paštu jau egzistuoja."

        if not errors:
            db = get_db()
            try:
                # Pirmas užsiregistravęs naudotojas tampa administratoriumi
                existing_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                role = "admin" if existing_count == 0 else DEFAULT_ROLE
                db.execute(
                    "INSERT INTO users (full_name, email, password_hash, role) "
                    "VALUES (?, ?, ?, ?)",
                    (full_name, email, generate_password_hash(password), role),
                )
                db.commit()
            except sqlite3.IntegrityError:
                errors["email"] = "Paskyra su šiuo el. paštu jau egzistuoja."
            else:
                flash("Registracija sėkminga! Dabar galite prisijungti.", "success")
                return redirect(url_for("login"))

    return render_template("register.html", form=form, errors=errors)


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard"))

    error = None
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        if not email or not password:
            error = "Įveskite el. paštą ir slaptažodį."
        elif user is None or not check_password_hash(user["password_hash"], password):
            error = "Neteisingas el. paštas arba slaptažodis."
        elif not user["is_active"]:
            error = "Ši paskyra deaktyvuota. Kreipkitės į administratorių."
        else:
            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["full_name"]
            session["user_role"] = user["role"]
            return redirect(url_for("dashboard"))

    return render_template("login.html", error=error, email=email)
    
@app.route("/logout")
def logout():
    session.clear()
    flash("Sėkmingai atsijungėte.", "success")
    return redirect(url_for("login"))

