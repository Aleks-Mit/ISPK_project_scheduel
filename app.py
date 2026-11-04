# app.py
# Pagrindinis Flask programos failas: "Tvarkaraštis" prototipas

import re
import sqlite3
from datetime import date, timedelta
from functools import wraps
from pathlib import Path

from flask import (
    Flask, flash, g, redirect, render_template,
    request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

# ---------------------------------------------------------------
# 1. Nustatymai
# ---------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "instance" / "tvarkarastis.db"

app = Flask(__name__)

# SECRET_KEY reikalingas, kad Flask galėtų saugiai pasirašyti "sesiją"
# ir rodyti pranešimus (flash). Prototipui tinka ir toks.
app.config["SECRET_KEY"] = "prototipo-paslaptis-pakeisti-realiame-projekte"

# Paprastas el. pašto formato tikrinimas: kažkas@kažkas.kažkas
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------
# 2. Duomenų bazė (SQLite)
# ---------------------------------------------------------------

def get_db():
    """Atidaro ryšį su duomenų baze (vienas ryšys vienai užklausai)."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error):
    """Uždaro ryšį, kai užklausa baigta."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Sukuria 'users' lentelę, jei jos dar nėra."""
    DATABASE.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(DATABASE)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name     TEXT NOT NULL,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'employee',
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # if db already exists, without 'role' column
    try:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'employee'")
    except sqlite3.OperationalError:
        pass  # column already exists
    db.commit()
    db.close()


init_db()


# ---------------------------------------------------------------
# 3. Pagalbinės funkcijos
# ---------------------------------------------------------------

ROLES = ("adminas", "pamainu vadovas", "darbotojas")

def login_required(view):
    """Apsauga: puslapį mato tik prisijungę naudotojai."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Norėdami matyti šį puslapį, prisijunkite.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view

def role_required(*roles):
    """Apsauga: puslapį mato tik naudotojai su nurodyta rolėmis."""
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                flash("Norėdami matyti šį puslapį, prisijunkite.", "error")
                return redirect(url_for("login"))
            if "user_role" not in session or session["user_role"] not in roles:
                flash("Neturite teisės matyti šį puslapį.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped_view
    return decorator


@app.context_processor
def inject_globals():
    """Kintamieji, kurie automatiškai prieinami visuose šablonuose."""
    return {
        "notification_count": 3,
        "user_role": session.get("user_role", "employee"),
            }   # demonstracinis pranešimų skaičius
                # & role


# ---------------------------------------------------------------
# 4. DEMONSTRACINIAI duomenys (ne tikra darbuotojų informacija)
# ---------------------------------------------------------------

DAY_NAMES = ["Pirmadienis", "Antradienis", "Trečiadienis", "Ketvirtadienis",
             "Penktadienis", "Šeštadienis", "Sekmadienis"]
DAY_SHORT = ["Pir", "Ant", "Tre", "Ket", "Pen", "Šeš", "Sek"]
MONTHS_GENITIVE = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio",
                   "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

# Pamainų tipai: raktas -> (pavadinimas, laikas)
SHIFT_TYPES = {
    "day":     ("Dieninė",   "06:00–14:00"),
    "evening": ("Vakarinė",  "14:00–22:00"),
    "night":   ("Naktinė",   "22:00–06:00"),
}

# Savaitės planas: Pir, Ant, Tre, Ket, Pen, Šeš, Sek (None = poilsio diena)
WEEK_PLAN = ["day", "day", "evening", None, "evening", "night", None]

DEMO_ANNOUNCEMENTS = [
    {"tag": "Svarbu", "color": "amber",
     "title": "Atnaujintas lapkričio tvarkaraštis",
     "text": "Lapkričio mėnesio pamainų grafikas jau paskelbtas. Prašome jį peržiūrėti.",
     "time": "Prieš 2 val."},
    {"tag": "Naujiena", "color": "indigo",
     "title": "Prašymų teikimas per sistemą",
     "text": "Atostogų ir nedarbingumo prašymus nuo šiol teikite čia, o ne per žinučių programėles.",
     "time": "Vakar"},
    {"tag": "Primenama", "color": "green",
     "title": "Prieinamumo pateikimas",
     "text": "Nurodykite savo galimas darbo dienas kitam mėnesiui iki šio penktadienio.",
     "time": "Prieš 3 d."},
]


def build_week(today):
    """Sudaro šios savaitės dienų sąrašą su demonstracinėmis pamainomis."""
    monday = today - timedelta(days=today.weekday())
    week = []
    for i in range(7):
        day = monday + timedelta(days=i)
        shift = None
        if WEEK_PLAN[i]:
            name, time = SHIFT_TYPES[WEEK_PLAN[i]]
            shift = {"key": WEEK_PLAN[i], "name": name, "time": time}
        week.append({
            "short": DAY_SHORT[i],
            "date": f"{MONTHS_GENITIVE[day.month - 1][:3]}. {day.day}",
            "is_today": day == today,
            "shift": shift,
            "day_obj": day,
        })
    return week, monday, monday + timedelta(days=6)


# ---------------------------------------------------------------
# 5. Registracija, prisijungimas, atsijungimas
# ---------------------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    form = {"full_name": "", "email": ""}
    errors = {}

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        form = {"full_name": full_name, "email": email}

        if len(full_name) < 2:
            errors["full_name"] = "Įveskite vardą ir pavardę (bent 2 simboliai)."

        if not EMAIL_PATTERN.match(email):
            errors["email"] = "Įveskite teisingą el. pašto adresą."

        if len(password) < 8:
            errors["password"] = "Slaptažodis turi būti bent 8 simbolių ilgio."

        if confirm_password != password:
            errors["confirm_password"] = "Slaptažodžiai nesutampa."

        if "email" not in errors:
            existing = get_db().execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                errors["email"] = "Paskyra su šiuo el. paštu jau egzistuoja."

        if not errors:
            db = get_db()
            try:
                # first registered user is admin, others are employees
                existing_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                role = "admin" if existing_count == 0 else "employee"
                db.execute(
                    "INSERT INTO users (full_name, email, password_hash) VALUES (?, ?, ?)",
                    (full_name, email, generate_password_hash(password)),
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
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    error = None
    email = ""

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()

        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Neteisingas el. paštas arba slaptažodis."
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


# ---------------------------------------------------------------
# 6. Skydelis ir kiti puslapiai (tik prisijungus)
# ---------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    today = date.today()
    week, monday, sunday = build_week(today)

    # Kiek pamainų dar laukia (šiandien ir vėliau) ir kiek valandų suplanuota
    upcoming = sum(1 for d in week if d["shift"] and d["day_obj"] >= today)
    total_shifts = sum(1 for d in week if d["shift"])
    hours = total_shifts * 8  # kiekviena pamaina - 8 val.

    cards = [
        {"label": "Artimiausios pamainos", "value": upcoming, "note": "Likusios šią savaitę",
         "color": "indigo",
         "icon": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/><path d="M9 16l2 2 4-4"/>'},
        {"label": "Valandos šią savaitę", "value": f"{hours} val.", "note": f"{total_shifts} pamainos po 8 val.",
         "color": "green",
         "icon": '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>'},
        {"label": "Laukiantys prašymai", "value": 2, "note": "Laukia vadovo patvirtinimo",
         "color": "amber",
         "icon": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>'},
    ]

    today_text = (f"{today.year} m. {MONTHS_GENITIVE[today.month - 1]} {today.day} d., "
                  f"{DAY_NAMES[today.weekday()].lower()}")
    week_range = (f"{MONTHS_GENITIVE[monday.month - 1]} {monday.day} – "
                  f"{MONTHS_GENITIVE[sunday.month - 1]} {sunday.day} d.")

    return render_template(
        "dashboard.html",
        first_name=session["user_name"].split()[0],
        today_text=today_text,
        week_range=week_range,
        cards=cards,
        week=week,
        announcements=DEMO_ANNOUNCEMENTS,
    )


# Likę meniu punktai kol kas rodo tik "Skiltis kuriama"
@app.route("/schedule")
@login_required
def schedule():
    return render_template("placeholder.html", title="Mano tvarkaraštis")


@app.route("/requests")
@login_required
def requests_page():
    return render_template("placeholder.html", title="Prašymai")


@app.route("/messages")
@login_required
def messages():
    return render_template("placeholder.html", title="Žinutės")


@app.route("/settings")
@login_required
def settings():
    return render_template("placeholder.html", title="Nustatymai")

@app.route("/admin/roles")
@role_required("admin")
def admin_roles():
    users = get_db().execute( 
        "SELECT id, full_name, email, role, created_at FROM users ORDER BY full_name"
        ).fetchall()
    return render_template("admin_roles.html", users=users, roles=ROLES)

@app.route("/admin/roles/<int:user_id>", methods=["POST"])
@role_required("admin")
def admin_set_role(user_id):
    new_role = request.form.get("role", "employee")
    if new_role not in ROLES:
        flash("Neteisinga rolė.", "error")
        return redirect(url_for("admin_roles"))
    if user_id == session["user_id"]:
        flash("Negalite pakeisti savo rolės.", "error")
        return redirect(url_for("admin_roles"))
    db = get_db()
    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    db.commit()
    flash("Rolė sėkmingai pakeista.", "success")
    return redirect(url_for("admin_roles"))

# ---------------------------------------------------------------
# 7. Programos paleidimas
# ---------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)