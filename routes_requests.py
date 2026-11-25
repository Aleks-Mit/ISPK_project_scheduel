import uuid
from datetime import date, datetime
from pathlib import Path

from flask import (abort, flash, g, redirect, render_template, request,
                   send_from_directory, url_for)

from config import (ALLOWED_EXTENSIONS, MAX_FILES, REQUEST_STATUSES,
                    REQUEST_TYPES, UPLOAD_DIR)
from core import app, get_db, login_required, role_required

def load_requests(db, rows):
    """Prie kiekvieno prašymo prideda prisegtų failų sąrašą ir dienų skaičių."""
    result = []
    for r in rows:
        item = dict(r)
        item["files"] = db.execute(
            "SELECT id, original_name FROM request_files WHERE request_id = ?",
            (r["id"],),
        ).fetchall()
        item["days"] = (date.fromisoformat(r["end_date"])
                        - date.fromisoformat(r["start_date"])).days + 1
        result.append(item)
    return result

@app.route("/requests", methods=["GET", "POST"])
@login_required
def requests_page():
    db = get_db()
    today = date.today()
    form = {"type": "", "start_date": "", "end_date": "", "reason": ""}
    errors = {}

    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}

        # 1) Tipas
        if form["type"] not in REQUEST_TYPES:
            errors["type"] = "Pasirinkite prašymo tipą."

        # 2) Datos
        start = end = None
        try:
            start = date.fromisoformat(form["start_date"])
        except ValueError:
            errors["start_date"] = "Įveskite teisingą pradžios datą."
        try:
            end = date.fromisoformat(form["end_date"])
        except ValueError:
            errors["end_date"] = "Įveskite teisingą pabaigos datą."

        if start and end:
            if end < start:
                errors["end_date"] = "Pabaigos data negali būti ankstesnė už pradžios datą."
            elif (end - start).days > 365:
                errors["end_date"] = "Laikotarpis negali būti ilgesnis nei 1 metai."
            elif start < today and form["type"] != "sick":
                errors["start_date"] = "Pradžios data negali būti praeityje."
            else:
                overlap = db.execute(
                    "SELECT 1 FROM requests WHERE user_id = ? AND status != 'rejected' "
                    "AND start_date <= ? AND end_date >= ?",
                    (g.user["id"], end.isoformat(), start.isoformat()),
                ).fetchone()
                if overlap:
                    errors["start_date"] = "Šiame laikotarpyje jau turite pateiktą ar patvirtintą prašymą."

        # 3) Priežastis
        if not form["reason"]:
            errors["reason"] = "Šis laukas privalomas."
        elif len(form["reason"]) < 5:
            errors["reason"] = "Priežastis per trumpa (bent 5 simboliai)."
        elif len(form["reason"]) > 500:
            errors["reason"] = "Priežastis per ilga (daugiausia 500 simbolių)."

        # 4) Dokumentai (neprivalomi)
        uploads = [f for f in request.files.getlist("documents") if f and f.filename]
        if len(uploads) > MAX_FILES:
            errors["documents"] = f"Galima prisegti ne daugiau kaip {MAX_FILES} failus."
        else:
            for f in uploads:
                if Path(f.filename).suffix.lower() not in ALLOWED_EXTENSIONS:
                    errors["documents"] = "Leidžiami formatai: PDF, PNG, JPG, DOC, DOCX."
                    break

        if not errors:
            cur = db.execute(
                "INSERT INTO requests (user_id, type, start_date, end_date, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (g.user["id"], form["type"], start.isoformat(), end.isoformat(),
                 form["reason"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            request_id = cur.lastrowid
            for f in uploads:
                stored = uuid.uuid4().hex + Path(f.filename).suffix.lower()
                f.save(UPLOAD_DIR / stored)
                db.execute(
                    "INSERT INTO request_files (request_id, original_name, stored_name) "
                    "VALUES (?, ?, ?)",
                    (request_id, Path(f.filename).name, stored),
                )
            db.commit()
            flash("Prašymas pateiktas. Jo būseną matysite sąraše.", "success")
            return redirect(url_for("requests_page"))

    # Filtrai (US-10): ?f_status=...&f_type=...
    f_status = request.args.get("f_status", "")
    f_type = request.args.get("f_type", "")
    if f_status not in REQUEST_STATUSES:
        f_status = ""
    if f_type not in REQUEST_TYPES:
        f_type = ""

    sql = "SELECT * FROM requests WHERE user_id = ?"
    params = [g.user["id"]]
    if f_status:
        sql += " AND status = ?"
        params.append(f_status)
    if f_type:
        sql += " AND type = ?"
        params.append(f_type)
    rows = db.execute(sql + " ORDER BY created_at DESC, id DESC", params).fetchall()

    total_requests = db.execute(
        "SELECT COUNT(*) FROM requests WHERE user_id = ?", (g.user["id"],)
    ).fetchone()[0]

    return render_template(
        "requests.html",
        form=form,
        errors=errors,
        my_requests=load_requests(db, rows),
        total_requests=total_requests,
        f_status=f_status,
        f_type=f_type,
        types=REQUEST_TYPES,
        statuses=REQUEST_STATUSES,
        today_iso=today.isoformat(),
    )


@app.route("/requests/files/<int:file_id>")
@login_required
def request_file(file_id):
    row = get_db().execute(
        "SELECT f.original_name, f.stored_name, r.user_id "
        "FROM request_files f JOIN requests r ON r.id = f.request_id "
        "WHERE f.id = ?", (file_id,),
    ).fetchone()
    if row is None:
        abort(404)
    if row["user_id"] != g.user["id"] and g.user["role"] not in ("manager", "hr", "admin"):
        abort(403)
    return send_from_directory(UPLOAD_DIR, row["stored_name"],
                               as_attachment=True, download_name=row["original_name"])


@app.route("/team")
@role_required("manager", "hr", "admin")
def team():
    db = get_db()
    status = request.args.get("status", "submitted")
    if status != "all" and status not in REQUEST_STATUSES:
        status = "submitted"

    query = ("SELECT r.*, u.full_name, u.email FROM requests r "
             "JOIN users u ON u.id = r.user_id")
    params = ()
    if status != "all":
        query += " WHERE r.status = ?"
        params = (status,)
    query += " ORDER BY r.created_at DESC, r.id DESC"

    counts = {row["status"]: row["c"] for row in db.execute(
        "SELECT status, COUNT(*) AS c FROM requests GROUP BY status")}

    return render_template(
        "team.html",
        reqs=load_requests(db, db.execute(query, params).fetchall()),
        current_status=status,
        counts=counts,
        total=sum(counts.values()),
        types=REQUEST_TYPES,
        statuses=REQUEST_STATUSES,
    )


@app.route("/team/requests/<int:request_id>/decision", methods=["POST"])
@role_required("manager", "hr", "admin")
def request_decision(request_id):
    decision = request.form.get("decision", "")
    comment = request.form.get("comment", "").strip()[:300]
    db = get_db()
    row = db.execute("SELECT id, user_id, status FROM requests WHERE id = ?",
                     (request_id,)).fetchone()

    if decision not in ("approved", "rejected"):
        flash("Neteisingas sprendimas.", "error")
    elif row is None:
        flash("Prašymas nerastas.", "error")
    elif row["user_id"] == g.user["id"]:
        flash("Negalite spręsti dėl savo paties prašymo.", "error")
    elif row["status"] != "submitted":
        flash("Dėl šio prašymo sprendimas jau priimtas.", "error")
    elif decision == "rejected" and not comment:
        flash("Atmesdami prašymą, nurodykite komentarą.", "error")
    else:
        db.execute(
            "UPDATE requests SET status = ?, reviewed_by = ?, reviewed_at = CURRENT_TIMESTAMP, "
            "review_comment = ? WHERE id = ?",
            (decision, g.user["id"], comment, request_id),
        )
        db.commit()
        flash("Prašymas patvirtintas." if decision == "approved" else "Prašymas atmestas.", "success")
    return redirect(url_for("team"))



