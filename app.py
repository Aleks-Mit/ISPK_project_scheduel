# app.py
# Pagrindinis Flask programos failas: "Tvarkaraštis" prototipas

import calendar
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

# Vaidmenys (RBAC): raktas duomenų bazėje -> pavadinimas sąsajoje
ROLES = {
    "employee": "Darbuotojas",
    "manager": "Vadovas",
    "hr": "Personalo specialistas",
    "admin": "Administratorius",
}
DEFAULT_ROLE = "employee"

# Senos (ankstesnės versijos) vaidmenų reikšmės, kurias konvertuojame
LEGACY_ROLES = {
    "adminas": "admin",
    "pamainu vadovas": "manager",
    "darbotojas": "employee",
}

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
    """Sukuria 'users' lentelę ir papildo ją trūkstamais stulpeliais."""
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
            is_active     INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # Jei duomenų bazė sukurta senesne versija, pridedame trūkstamus stulpelius
    columns = [row[1] for row in db.execute("PRAGMA table_info(users)")]
    if "role" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'employee'")
    if "is_active" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")

    # Senus vaidmenų pavadinimus paverčiame naujais raktais
    for old, new in LEGACY_ROLES.items():
        db.execute("UPDATE users SET role = ? WHERE role = ?", (new, old))

    # Jei administratoriaus dar nėra, pirmas naudotojas tampa administratoriumi
    has_admin = db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone()
    has_users = db.execute("SELECT 1 FROM users").fetchone()
    if has_users and not has_admin:
        db.execute("UPDATE users SET role = 'admin' WHERE id = (SELECT MIN(id) FROM users)")

    db.commit()
    db.close()


init_db()


# ---------------------------------------------------------------
# 3. Pagalbinės funkcijos
# ---------------------------------------------------------------


@app.before_request
def load_current_user():
    """Prieš kiekvieną užklausą patikrina, ar prisijungęs naudotojas vis dar
    egzistuoja ir yra aktyvus. Vaidmuo visada skaitomas iš duomenų bazės."""
    g.user = None
    if request.endpoint in (None, "static"):
        return

    user_id = session.get("user_id")
    if user_id is None:
        return

    user = get_db().execute(
        "SELECT id, full_name, email, role, is_active FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()

    if user is None or not user["is_active"]:
        session.clear()
        flash("Jūsų paskyra deaktyvuota. Kreipkitės į administratorių.", "error")
        return redirect(url_for("login"))

    g.user = user
    session["user_name"] = user["full_name"]
    session["user_role"] = user["role"]


def login_required(view):
    """Apsauga: puslapį mato tik prisijungę naudotojai."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if g.user is None:
            flash("Norėdami matyti šį puslapį, prisijunkite.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped_view


def role_required(*roles):
    """Apsauga: puslapį mato tik naudotojai su nurodytais vaidmenimis."""
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if g.user is None:
                flash("Norėdami matyti šį puslapį, prisijunkite.", "error")
                return redirect(url_for("login"))
            if g.user["role"] not in roles:
                flash("Neturite teisės matyti šio puslapio.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped_view
    return decorator


@app.context_processor
def inject_globals():
    """Kintamieji, kurie automatiškai prieinami visuose šablonuose."""
    role = g.user["role"] if g.get("user") else DEFAULT_ROLE
    return {
        "notification_count": 3,   # demonstracinis pranešimų skaičius
        "user_role": role,
        "role_labels": ROLES,
    }





# ---------------------------------------------------------------
# 4. DEMONSTRACINIAI duomenys (ne tikra darbuotojų informacija)
# ---------------------------------------------------------------

DAY_NAMES = ["Pirmadienis", "Antradienis", "Trečiadienis", "Ketvirtadienis",
             "Penktadienis", "Šeštadienis", "Sekmadienis"]
DAY_SHORT = ["Pir", "Ant", "Tre", "Ket", "Pen", "Šeš", "Sek"]
MONTHS_GENITIVE = ["sausio", "vasario", "kovo", "balandžio", "gegužės", "birželio",
                   "liepos", "rugpjūčio", "rugsėjo", "spalio", "lapkričio", "gruodžio"]

# Pamainų tipai: raktas -> (pavadinimas, pradžia, pabaiga)
SHIFT_TYPES = {
    "day":     ("Dieninė",   "06:00", "14:00"),
    "evening": ("Vakarinė",  "14:00", "22:00"),
    "night":   ("Naktinė",   "22:00", "06:00"),
}

# Savaičių šablonai (demonstraciniai): [Pir, Ant, Tre, Ket, Pen, Šeš, Sek], None = poilsio diena.
# Šablonai kartojasi: ši savaitė = 1-as, kita = 2-as, praėjusi = 3-ias ir t. t.
WEEK_PATTERNS = [
    ["day", "day", "evening", None, "evening", "night", None],
    [None, "day", "day", "day", "evening", None, None],
    ["night", "night", None, None, "evening", "evening", None],
]
MONTHS_NOMINATIVE = ["Sausis", "Vasaris", "Kovas", "Balandis", "Gegužė", "Birželis",
                     "Liepa", "Rugpjūtis", "Rugsėjis", "Spalis", "Lapkritis", "Gruodis"]
SCHEDULE_VIEWS = ("month", "week")   # mėnesio tinklelis arba savaitės sąrašas
MAX_WEEK_OFFSET = 8
MAX_MONTH_OFFSET = 6

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


def shift_key_for(day, today):
    """Demonstracinė pamaina šiai dienai: pamainos raktas arba None
    (poilsio diena, laisva savaitė arba tvarkaraštis dar nepaskelbtas)."""
    # Tvarkaraštis paskelbtas iki kito mėnesio pabaigos
    next_year = today.year + (1 if today.month == 12 else 0)
    next_month = today.month % 12 + 1
    published_until = date(next_year, next_month, calendar.monthrange(next_year, next_month)[1])
    if day > published_until:
        return None

    # Kelinta savaitė nuo šios savaitės yra ši diena (0 = ši, 1 = kita, -1 = praėjusi)
    this_monday = today - timedelta(days=today.weekday())
    day_monday = day - timedelta(days=day.weekday())
    weeks_from_now = (day_monday - this_monday).days // 7

    # Kas penkta savaitė - laisva (pamainų nėra)
    if weeks_from_now % 5 == 3:
        return None
    return WEEK_PATTERNS[weeks_from_now % 3][day.weekday()]


def make_shift(key):
    """Pamainos žodynas šablonui (arba None, jei pamainos nėra)."""
    if not key:
        return None
    name, start, end = SHIFT_TYPES[key]
    return {"key": key, "name": name, "start": start, "end": end,
            "time": f"{start}–{end}", "ends_next_day": end < start}


def build_week(today, offset=0):
    """Sudaro pasirinktos savaitės dienų sąrašą su demonstracinėmis pamainomis.
    offset: 0 = ši savaitė, -1 = praėjusi, 1 = kita ir t. t."""
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    week = []
    for i in range(7):
        day = monday + timedelta(days=i)
        week.append({
            "short": DAY_SHORT[i],
            "name": DAY_NAMES[i],
            "date": f"{MONTHS_GENITIVE[day.month - 1][:3]}. {day.day}",
            "full_date": f"{day.year}-{day.month:02d}-{day.day:02d}",
            "is_today": day == today,
            "shift": make_shift(shift_key_for(day, today)),
            "day_obj": day,
        })
    return week, monday, monday + timedelta(days=6)


def build_month(today, offset=0):
    """Sudaro mėnesio kalendoriaus langelius (savaitės po 7 dienas, pirmadienis pirmas).
    offset: 0 = šis mėnuo, -1 = praėjęs, 1 = kitas ir t. t."""
    index = today.year * 12 + (today.month - 1) + offset
    year, month = index // 12, index % 12 + 1
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])

    # Kalendorius prasideda pirmadienį ir baigiasi sekmadienį
    day = first - timedelta(days=first.weekday())
    end = last + timedelta(days=6 - last.weekday())

    cells = []
    while day <= end:
        cells.append({
            "day": day.day,
            "in_month": day.month == month,
            "is_today": day == today,
            "shift": make_shift(shift_key_for(day, today)),
        })
        day += timedelta(days=1)

    shift_count = sum(1 for c in cells if c["in_month"] and c["shift"])
    return cells, f"{MONTHS_NOMINATIVE[month - 1]} {year}", shift_count


# ---------------------------------------------------------------
# 5. Registracija, prisijungimas, atsijungimas
# ---------------------------------------------------------------

REQUIRED_MSG = "Šis laukas privalomas."


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
    today = date.today()

    # Rodinys: mėnesio tinklelis (numatytasis) arba savaitės sąrašas. Pasirinkimas įsimenamas.
    view = request.args.get("view")
    if view in SCHEDULE_VIEWS:
        session["schedule_view"] = view
    else:
        view = session.get("schedule_view")
        if view not in SCHEDULE_VIEWS:
            view = "month"

    if view == "month":
        offset = request.args.get("month", 0, type=int)
        offset = max(-MAX_MONTH_OFFSET, min(MAX_MONTH_OFFSET, offset))
        cells, title, shift_count = build_month(today, offset)
        return render_template(
            "schedule.html",
            view=view,
            offset=offset,
            period_title=title,
            cells=cells,
            day_heads=DAY_SHORT,
            prev_url=url_for("schedule", view="month", month=offset - 1),
            next_url=url_for("schedule", view="month", month=offset + 1),
            current_url=url_for("schedule", view="month"),
            has_prev=offset > -MAX_MONTH_OFFSET,
            has_next=offset < MAX_MONTH_OFFSET,
            shift_count=shift_count,
            total_hours=shift_count * 8,  # kiekviena pamaina - 8 val.
            shift_types=SHIFT_TYPES,
        )

    offset = request.args.get("week", 0, type=int)
    offset = max(-MAX_WEEK_OFFSET, min(MAX_WEEK_OFFSET, offset))
    week, monday, sunday = build_week(today, offset)
    shifts = [d for d in week if d["shift"]]
    week_range = (f"{monday.year} m. {MONTHS_GENITIVE[monday.month - 1]} {monday.day} – "
                  f"{MONTHS_GENITIVE[sunday.month - 1]} {sunday.day} d.")
    return render_template(
        "schedule.html",
        view=view,
        offset=offset,
        period_title=week_range,
        week=week,
        prev_url=url_for("schedule", view="week", week=offset - 1),
        next_url=url_for("schedule", view="week", week=offset + 1),
        current_url=url_for("schedule", view="week"),
        has_prev=offset > -MAX_WEEK_OFFSET,
        has_next=offset < MAX_WEEK_OFFSET,
        shift_count=len(shifts),
        total_hours=len(shifts) * 8,  # kiekviena pamaina - 8 val.
        shift_types=SHIFT_TYPES,
    )

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

@app.route("/team")
@role_required("manager", "hr", "admin")
def team():
    return render_template("placeholder.html", title="Komandos valdymas")


@app.route("/hr")
@role_required("hr", "admin")
def hr_section():
    return render_template("placeholder.html", title="Personalo skiltis")


@app.route("/admin/roles")
@role_required("admin")
def admin_roles():
    users = get_db().execute(
        "SELECT id, full_name, email, role, is_active, created_at "
        "FROM users ORDER BY full_name COLLATE NOCASE"
    ).fetchall()
    active_count = sum(1 for u in users if u["is_active"])
    return render_template(
        "admin_roles.html",
        users=users,
        roles=ROLES,
        active_count=active_count,
    )


@app.route("/admin/roles/<int:user_id>", methods=["POST"])
@role_required("admin")
def admin_set_role(user_id):
    new_role = request.form.get("role", "")
    if new_role not in ROLES:
        flash("Neteisingas vaidmuo.", "error")
        return redirect(url_for("admin_roles"))
    if user_id == g.user["id"]:
        flash("Negalite pakeisti savo vaidmens.", "error")
        return redirect(url_for("admin_roles"))

    db = get_db()
    target = db.execute("SELECT full_name FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        flash("Naudotojas nerastas.", "error")
        return redirect(url_for("admin_roles"))

    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    db.commit()
    flash(f"Naudotojo {target['full_name']} vaidmuo pakeistas į „{ROLES[new_role]}“.", "success")
    return redirect(url_for("admin_roles"))


@app.route("/admin/users/<int:user_id>/status", methods=["POST"])
@role_required("admin")
def admin_set_status(user_id):
    make_active = request.form.get("active") == "1"
    if user_id == g.user["id"]:
        flash("Negalite deaktyvuoti savo paskyros.", "error")
        return redirect(url_for("admin_roles"))

    db = get_db()
    target = db.execute("SELECT full_name FROM users WHERE id = ?", (user_id,)).fetchone()
    if target is None:
        flash("Naudotojas nerastas.", "error")
        return redirect(url_for("admin_roles"))

    db.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if make_active else 0, user_id))
    db.commit()
    action = "aktyvuota" if make_active else "deaktyvuota"
    flash(f"Paskyra {target['full_name']} {action}.", "success")
    return redirect(url_for("admin_roles"))

# ---------------------------------------------------------------
# 7. Programos paleidimas
# ---------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)