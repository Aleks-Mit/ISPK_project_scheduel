from datetime import datetime
from flask import (abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)
from core import app, get_db, login_required, role_required

SENDER_ROLES = ("manager", "hr", "admin")   # kas gali pradėti pokalbį
MAX_BODY = 2000


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def short(text, limit=80):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def notify(db, user_id, message_id, title, preview, url):
    """Sukuria sistemos pranešimą (rodomas varpelyje)."""
    db.execute(
        "INSERT INTO notifications (user_id, message_id, title, preview, url, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, message_id, title, short(preview), url, now_str()),
    )


# ---------------------------------------------------------------
# Žinučių sąrašai (gautos / išsiųstos)
# ---------------------------------------------------------------

@app.route("/messages")
@login_required
def messages():
    db = get_db()
    can_send = g.user["role"] in SENDER_ROLES
    box = request.args.get("box", "inbox")
    if box != "sent" or not can_send:
        box = "inbox"

    if box == "sent":
        rows = db.execute(
            "SELECT m.id, m.body, m.created_at, COUNT(r.id) AS total, "
            "       SUM(CASE WHEN r.read_at IS NOT NULL THEN 1 ELSE 0 END) AS read_count, "
            "       MAX(r.read_at) AS last_read "
            "FROM messages m JOIN message_recipients r ON r.message_id = m.id "
            "WHERE m.sender_id = ? GROUP BY m.id "
            "ORDER BY m.created_at DESC, m.id DESC",
            (g.user["id"],),
        ).fetchall()
        items = []
        for row in rows:
            names = [x["full_name"] for x in db.execute(
                "SELECT u.full_name FROM message_recipients r "
                "JOIN users u ON u.id = r.recipient_id WHERE r.message_id = ? "
                "ORDER BY u.full_name COLLATE NOCASE", (row["id"],))]
            items.append({**dict(row), "names": names})
    else:
        items = db.execute(
            "SELECT m.id, m.body, m.created_at, u.full_name AS sender_name, r.read_at "
            "FROM message_recipients r "
            "JOIN messages m ON m.id = r.message_id "
            "JOIN users u ON u.id = m.sender_id "
            "WHERE r.recipient_id = ? ORDER BY m.created_at DESC, m.id DESC",
            (g.user["id"],),
        ).fetchall()

    return render_template("messages.html", box=box, items=items, can_send=can_send)


# ---------------------------------------------------------------
# Naujos žinutės siuntimas (US-5)
# ---------------------------------------------------------------

@app.route("/messages/new", methods=["GET", "POST"])
@role_required(*SENDER_ROLES)
def message_new():
    db = get_db()
    users = db.execute(
        "SELECT id, full_name, email, role FROM users "
        "WHERE is_active = 1 AND id != ? ORDER BY full_name COLLATE NOCASE",
        (g.user["id"],),
    ).fetchall()
    valid_ids = {u["id"] for u in users}
    selected, body, errors = set(), "", {}

    if request.method == "POST":
        body = request.form.get("body", "").strip()
        raw_ids = request.form.getlist("recipients")

        invalid = False
        for value in raw_ids:
            try:
                selected.add(int(value))
            except ValueError:
                invalid = True

        if not raw_ids:
            errors["recipients"] = "Pasirinkite bent vieną gavėją."
        elif invalid or not selected <= valid_ids:
            errors["recipients"] = ("Žinutes galima siųsti tik sistemoje "
                                    "registruotiems aktyviems naudotojams.")

        if not body:
            errors["body"] = "Žinutės turinys negali būti tuščias."
        elif len(body) > MAX_BODY:
            errors["body"] = f"Žinutė per ilga (daugiausia {MAX_BODY} simbolių)."

        if not errors:
            cur = db.execute(
                "INSERT INTO messages (sender_id, body, created_at) VALUES (?, ?, ?)",
                (g.user["id"], body, now_str()),
            )
            message_id = cur.lastrowid
            url = url_for("message_view", message_id=message_id)
            for uid in sorted(selected):
                db.execute(
                    "INSERT INTO message_recipients (message_id, recipient_id) VALUES (?, ?)",
                    (message_id, uid),
                )
                notify(db, uid, message_id,
                       f"Nauja žinutė nuo {g.user['full_name']}", body, url)
            db.commit()
            flash(f"Žinutė išsiųsta ({len(selected)} gavėj.).", "success")
            return redirect(url_for("messages", box="sent"))

    return render_template("message_new.html", users=users, selected=selected,
                           body=body, errors=errors)


# ---------------------------------------------------------------
# Žinutės peržiūra (US-6: automatinis „Perskaityta“) ir pokalbis (US-8)
# ---------------------------------------------------------------

@app.route("/messages/<int:message_id>")
@login_required
def message_view(message_id):
    db = get_db()
    msg = db.execute(
        "SELECT m.id, m.sender_id, m.body, m.created_at, u.full_name AS sender_name "
        "FROM messages m JOIN users u ON u.id = m.sender_id WHERE m.id = ?",
        (message_id,),
    ).fetchone()
    if msg is None:
        abort(404)

    recipients = db.execute(
        "SELECT r.recipient_id, r.read_at, u.full_name "
        "FROM message_recipients r JOIN users u ON u.id = r.recipient_id "
        "WHERE r.message_id = ? ORDER BY u.full_name COLLATE NOCASE",
        (message_id,),
    ).fetchall()
    is_sender = msg["sender_id"] == g.user["id"]
    is_recipient = any(r["recipient_id"] == g.user["id"] for r in recipients)
    if not (is_sender or is_recipient):
        abort(403)

    # Atidarius žinutę: pažymime „Perskaityta“ ir nuimame susijusius pranešimus
    if is_recipient:
        db.execute(
            "UPDATE message_recipients SET read_at = ? "
            "WHERE message_id = ? AND recipient_id = ? AND read_at IS NULL",
            (now_str(), message_id, g.user["id"]),
        )
    db.execute(
        "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND message_id = ?",
        (g.user["id"], message_id),
    )
    db.commit()

    sql = ("SELECT p.id, p.thread_user_id, p.sender_id, p.body, p.created_at, u.full_name "
           "FROM message_replies p JOIN users u ON u.id = p.sender_id "
           "WHERE p.message_id = ?")
    params = [message_id]
    if not is_sender:                      # gavėjas mato tik savo pokalbį
        sql += " AND p.thread_user_id = ?"
        params.append(g.user["id"])
    replies = db.execute(sql + " ORDER BY p.id", params).fetchall()

    threads = []
    for r in recipients:
        if is_sender or r["recipient_id"] == g.user["id"]:
            threads.append({
                "user_id": r["recipient_id"],
                "name": r["full_name"],
                "read_at": r["read_at"],
                "replies": [p for p in replies if p["thread_user_id"] == r["recipient_id"]],
            })

    return render_template("message_view.html", msg=msg, is_sender=is_sender,
                           threads=threads, reply_count=len(replies))


@app.route("/messages/<int:message_id>/reply", methods=["POST"])
@login_required
def message_reply(message_id):
    db = get_db()
    msg = db.execute("SELECT id, sender_id FROM messages WHERE id = ?",
                     (message_id,)).fetchone()
    if msg is None:
        abort(404)
    recipient_ids = {r["recipient_id"] for r in db.execute(
        "SELECT recipient_id FROM message_recipients WHERE message_id = ?", (message_id,))}

    if msg["sender_id"] == g.user["id"]:           # vadovas atsako konkrečiam gavėjui
        try:
            thread_id = int(request.form.get("thread", ""))
        except ValueError:
            abort(400)
        if thread_id not in recipient_ids:
            abort(400)
        notify_user = thread_id
        url = url_for("message_view", message_id=message_id)
    elif g.user["id"] in recipient_ids:            # darbuotojas atsako vadovui
        thread_id = g.user["id"]
        notify_user = msg["sender_id"]
        url = url_for("message_view", message_id=message_id) + f"#t{thread_id}"
    else:
        abort(403)

    body = request.form.get("body", "").strip()
    if not body:
        flash("Atsakymo turinys negali būti tuščias.", "error")
    elif len(body) > MAX_BODY:
        flash(f"Atsakymas per ilgas (daugiausia {MAX_BODY} simbolių).", "error")
    else:
        db.execute(
            "INSERT INTO message_replies (message_id, thread_user_id, sender_id, body, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (message_id, thread_id, g.user["id"], body, now_str()),
        )
        notify(db, notify_user, message_id,
               f"Naujas atsakymas: {g.user['full_name']}", body, url)
        db.commit()
        flash("Atsakymas išsiųstas.", "success")

    return redirect(url_for("message_view", message_id=message_id) + f"#t{thread_id}")


# ---------------------------------------------------------------
# Pranešimai (varpelis) ir „realaus laiko“ API
# ---------------------------------------------------------------

@app.route("/notifications/<int:notification_id>/open")
@login_required
def notification_open(notification_id):
    db = get_db()
    row = db.execute("SELECT id, url FROM notifications WHERE id = ? AND user_id = ?",
                     (notification_id, g.user["id"])).fetchone()
    if row is None:
        abort(404)
    db.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (row["id"],))
    db.commit()
    return redirect(row["url"])


@app.route("/notifications/read-all", methods=["POST"])
@login_required
def notifications_read_all():
    db = get_db()
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (g.user["id"],))
    db.commit()
    return jsonify(ok=True)


@app.route("/api/status")
def api_status():
    if g.user is None:
        return jsonify(error="unauthorized"), 401
    db = get_db()
    uid = g.user["id"]
    rows = db.execute(
        "SELECT id, title, preview, is_read, created_at FROM notifications "
        "WHERE user_id = ? ORDER BY id DESC LIMIT 8", (uid,)).fetchall()
    return jsonify(
        unread_messages=db.execute(
            "SELECT COUNT(*) FROM message_recipients WHERE recipient_id = ? AND read_at IS NULL",
            (uid,)).fetchone()[0],
        unread_notifications=db.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND is_read = 0",
            (uid,)).fetchone()[0],
        notifications=[{
            "id": r["id"], "title": r["title"], "preview": r["preview"],
            "is_read": bool(r["is_read"]), "created_at": r["created_at"][:16],
            "url": url_for("notification_open", notification_id=r["id"]),
        } for r in rows],
    )


@app.route("/api/messages/<int:message_id>/status")
def api_message_status(message_id):
    if g.user is None:
        return jsonify(error="unauthorized"), 401
    db = get_db()
    msg = db.execute("SELECT sender_id FROM messages WHERE id = ?", (message_id,)).fetchone()
    if msg is None:
        return jsonify(error="not found"), 404
    recips = db.execute(
        "SELECT recipient_id, read_at FROM message_recipients WHERE message_id = ?",
        (message_id,)).fetchall()
    is_sender = msg["sender_id"] == g.user["id"]
    if not is_sender and g.user["id"] not in {r["recipient_id"] for r in recips}:
        return jsonify(error="forbidden"), 403

    if is_sender:
        reply_count = db.execute(
            "SELECT COUNT(*) FROM message_replies WHERE message_id = ?",
            (message_id,)).fetchone()[0]
    else:
        reply_count = db.execute(
            "SELECT COUNT(*) FROM message_replies WHERE message_id = ? AND thread_user_id = ?",
            (message_id, g.user["id"])).fetchone()[0]

    return jsonify(
        reply_count=reply_count,
        recipients=[{"id": r["recipient_id"], "read_at": r["read_at"]} for r in recips]
        if is_sender else [],
    )