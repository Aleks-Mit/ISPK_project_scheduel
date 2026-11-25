import sqlite3
from functools import wraps

from flask import Flask, flash, g, redirect, request, session, url_for

from config import DATABASE, DEFAULT_ROLE, LEGACY_ROLES, ROLES

app = Flask(__name__)
app.config["SECRET_KEY"] = "prototipo-paslaptis-pakeisti-realiame-projekte"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024   # visi failai kartu iki 10 MB



# ---------------------------------------------------------------
# Duomenų bazė (SQLite)
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
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            type           TEXT NOT NULL,
            start_date     TEXT NOT NULL,
            end_date       TEXT NOT NULL,
            reason         TEXT NOT NULL,
            status         TEXT NOT NULL DEFAULT 'submitted',
            reviewed_by    INTEGER,
            reviewed_at    TEXT,
            review_comment TEXT,
            created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS request_files (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id    INTEGER NOT NULL,
            original_name TEXT NOT NULL,
            stored_name   TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS shifts (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            shift_date TEXT NOT NULL,
            shift_type TEXT NOT NULL,
            UNIQUE (user_id, shift_date)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id  INTEGER NOT NULL,
            body       TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS message_recipients (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id   INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            read_at      TEXT,
            UNIQUE (message_id, recipient_id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS message_replies (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id     INTEGER NOT NULL,
            thread_user_id INTEGER NOT NULL,
            sender_id      INTEGER NOT NULL,
            body           TEXT NOT NULL,
            created_at     TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            title      TEXT NOT NULL,
            preview    TEXT NOT NULL,
            url        TEXT NOT NULL,
            is_read    INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_seed (
            user_id      INTEGER PRIMARY KEY,
            seeded_until TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS shift_changes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            shift_date   TEXT NOT NULL,
            shift_type   TEXT NOT NULL,
            action       TEXT NOT NULL,
            from_user_id INTEGER NOT NULL,
            to_user_id   INTEGER,
            changed_by   INTEGER NOT NULL,
            reason       TEXT,
            created_at   TEXT NOT NULL
        )
        """
    )
    shift_cols = [row[1] for row in db.execute("PRAGMA table_info(shifts)")]
    if "status" not in shift_cols:
        db.execute("ALTER TABLE shifts ADD COLUMN status TEXT NOT NULL DEFAULT 'scheduled'")
    if "seeking_by" not in shift_cols:
        db.execute("ALTER TABLE shifts ADD COLUMN seeking_by INTEGER")
    if "seeking_at" not in shift_cols:
        db.execute("ALTER TABLE shifts ADD COLUMN seeking_at TEXT")


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
# Pagalbinės funkcijos
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
    notification_count = 0
    unread_messages = 0
    if g.get("user"):
        db = get_db()
        notification_count = db.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
            (g.user["id"],),
        ).fetchone()[0]
        unread_messages = db.execute(
            "SELECT COUNT(*) FROM message_recipients "
            "WHERE recipient_id = ? AND read_at IS NULL",
            (g.user["id"],),
        ).fetchone()[0]
    return {
        "notification_count": notification_count,
        "unread_messages": unread_messages,
        "user_role": role,
        "role_labels": ROLES,
    }

@app.errorhandler(413)
def file_too_large(error):
    flash("Failai per dideli (leidžiama iki 10 MB iš viso).", "error")
    return redirect(url_for("requests_page"))

