from datetime import date, datetime, timedelta

from flask import flash, g, redirect, render_template, request, url_for

from config import DAY_NAMES, MONTHS_GENITIVE, REQUEST_TYPES, SHIFT_TYPES
from core import app, get_db, role_required
from schedule_utils import published_until, user_shift_map

MANAGER_ROLES = ("manager", "admin")
PAST_DAYS = 60   # kiek dienų atgal galima peržiūrėti


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def describe_last_change(db, iso, user_id):
    """Žmogui suprantamas paaiškinimas, kas ir kada jau pakeitė šią pamainą."""
    if not user_id:
        return None
    c = db.execute(
        "SELECT c.action, c.created_at, b.full_name AS by_name, t.full_name AS to_name "
        "FROM shift_changes c JOIN users b ON b.id = c.changed_by "
        "LEFT JOIN users t ON t.id = c.to_user_id "
        "WHERE c.shift_date = ? AND c.from_user_id = ? ORDER BY c.id DESC LIMIT 1",
        (iso, user_id),
    ).fetchone()
    if c is None:
        return None
    what = f"perduota darbuotojui {c['to_name']}" if c["action"] == "replace" else "atšaukta"
    return f"Pamaina jau {what} (vadovas {c['by_name']}, {c['created_at'][11:16]})."


@app.route("/shifts")
@role_required(*MANAGER_ROLES)
def shifts_page():
    today = date.today()
    db = get_db()
    lo, hi = today - timedelta(days=PAST_DAYS), published_until(today)
    try:
        day = date.fromisoformat(request.args.get("date", ""))
    except ValueError:
        day = today
    day = max(lo, min(hi, day))
    iso = day.isoformat()

    users = db.execute(
        "SELECT id, full_name FROM users WHERE is_active = 1 ORDER BY full_name COLLATE NOCASE"
    ).fetchall()
    for u in users:                       # užtikrina, kad visų demonstracinės pamainos sugeneruotos
        user_shift_map(u["id"], today)

    rows = db.execute(
        "SELECT s.id, s.user_id, s.shift_type, s.status, s.seeking_by, s.seeking_at, "
        "       u.full_name, k.full_name AS seeker "
        "FROM shifts s JOIN users u ON u.id = s.user_id "
        "LEFT JOIN users k ON k.id = s.seeking_by "
        "WHERE s.shift_date = ? AND u.is_active = 1 ORDER BY u.full_name COLLATE NOCASE",
        (iso,),
    ).fetchall()

    leave = {r["user_id"]: r["type"] for r in db.execute(
        "SELECT user_id, type FROM requests "
        "WHERE status = 'approved' AND start_date <= ? AND end_date >= ?", (iso, iso))}

    me = g.user["id"]
    is_admin = g.user["role"] == "admin"
    by_type = {key: [] for key in SHIFT_TYPES}
    for r in rows:
        item = dict(r)
        item["leave"] = leave.get(r["user_id"])
        item["locked"] = r["status"] == "seeking" and r["seeking_by"] != me and not is_admin
        by_type[r["shift_type"]].append(item)

    groups = [{"key": key, "name": name, "time": f"{start}–{end}", "people": by_type[key]}
          for key, (name, start, end) in SHIFT_TYPES.items()]
    
    busy = {r["user_id"] for r in rows}
    candidates = [u for u in users if u["id"] not in busy and u["id"] not in leave]

    changes = db.execute(
        "SELECT c.*, f.full_name AS from_name, t.full_name AS to_name, b.full_name AS by_name "
        "FROM shift_changes c JOIN users f ON f.id = c.from_user_id "
        "LEFT JOIN users t ON t.id = c.to_user_id JOIN users b ON b.id = c.changed_by "
        "ORDER BY c.id DESC LIMIT 25"
    ).fetchall()
    changes = [{**dict(c), "shift_name": SHIFT_TYPES[c["shift_type"]][0]} for c in changes]

    return render_template(
        "shifts.html",
        iso=iso,
        day_title=(f"{day.year} m. {MONTHS_GENITIVE[day.month - 1]} {day.day} d., "
                   f"{DAY_NAMES[day.weekday()].lower()}"),
        is_today=day == today,
        can_edit=day >= today,
        prev_url=url_for("shifts_page", date=(day - timedelta(days=1)).isoformat()) if day > lo else None,
        next_url=url_for("shifts_page", date=(day + timedelta(days=1)).isoformat()) if day < hi else None,
        min_iso=lo.isoformat(), max_iso=hi.isoformat(),
        groups=groups, candidates=candidates, changes=changes, types=REQUEST_TYPES,
    )


@app.route("/shifts/<int:shift_id>/action", methods=["POST"])
@role_required(*MANAGER_ROLES)
def shift_action(shift_id):
    db = get_db()
    today = date.today()
    me = g.user["id"]
    is_admin = g.user["role"] == "admin"
    action = request.form.get("action", "")
    form_iso = request.form.get("date", "")
    expected_user = request.form.get("expected_user", type=int)

    shift = db.execute(
        "SELECT s.*, u.full_name, k.full_name AS seeker FROM shifts s "
        "JOIN users u ON u.id = s.user_id LEFT JOIN users k ON k.id = s.seeking_by "
        "WHERE s.id = ?", (shift_id,),
    ).fetchone()

    # Kitas vadovas jau pakeitė šią pamainą, kol jūsų puslapis buvo atidarytas
    if shift is None or shift["user_id"] != expected_user:
        flash(describe_last_change(db, form_iso, expected_user)
              or "Ši pamaina jau pakeista kito vadovo. Peržiūrėkite atnaujintą sąrašą.", "error")
        return redirect(url_for("shifts_page", date=form_iso))

    iso = shift["shift_date"]
    back = redirect(url_for("shifts_page", date=iso))

    if date.fromisoformat(iso) < today:
        flash("Praėjusių dienų pamainų keisti negalima.", "error")
        return back

    seeking = shift["status"] == "seeking"
    locked = seeking and shift["seeking_by"] != me and not is_admin

    if action == "seek":
        if seeking:
            flash("Pakeitimo jau ieško " + ("jūs." if shift["seeking_by"] == me
                                             else f"vadovas {shift['seeker']}."), "error")
        else:
            db.execute("UPDATE shifts SET status = 'seeking', seeking_by = ?, seeking_at = ? "
                       "WHERE id = ?", (me, now_str(), shift_id))
            db.commit()
            flash("Pažymėta: ieškote pakeitimo. Kiti vadovai tai mato.", "success")

    elif action == "release":
        if not seeking:
            flash("Ši pamaina nėra pažymėta kaip ieškanti pakeitimo.", "error")
        elif locked:
            flash(f"Paiešką gali nutraukti tik {shift['seeker']} arba administratorius.", "error")
        else:
            db.execute("UPDATE shifts SET status = 'scheduled', seeking_by = NULL, "
                       "seeking_at = NULL WHERE id = ?", (shift_id,))
            db.commit()
            flash("Pakeitimo paieška nutraukta.", "success")

    elif action in ("replace", "cancel"):
        if locked:
            flash(f"Šios pamainos pakeitimo jau ieško vadovas {shift['seeker']}. "
                  "Susisiekite su juo arba palaukite.", "error")
            return back
        reason = request.form.get("reason", "").strip()[:200]

        if action == "replace":
            new_id = request.form.get("new_user", type=int)
            new_user = None
            if new_id:
                new_user = db.execute("SELECT id, full_name FROM users "
                                      "WHERE id = ? AND is_active = 1", (new_id,)).fetchone()
            if new_user is None or new_user["id"] == shift["user_id"]:
                flash("Pasirinkite pakeitimui tinkamą darbuotoją.", "error")
                return back
            user_shift_map(new_user["id"], today)
            if db.execute("SELECT 1 FROM shifts WHERE user_id = ? AND shift_date = ?",
                          (new_user["id"], iso)).fetchone():
                flash(f"{new_user['full_name']} šią dieną jau turi pamainą.", "error")
                return back
            if db.execute("SELECT 1 FROM requests WHERE user_id = ? AND status = 'approved' "
                          "AND start_date <= ? AND end_date >= ?",
                          (new_user["id"], iso, iso)).fetchone():
                flash(f"{new_user['full_name']} šią dieną turi patvirtintą nebuvimą.", "error")
                return back
            db.execute("UPDATE shifts SET user_id = ?, status = 'scheduled', seeking_by = NULL, "
                       "seeking_at = NULL WHERE id = ?", (new_user["id"], shift_id))
            db.execute("INSERT INTO shift_changes (shift_date, shift_type, action, from_user_id, "
                       "to_user_id, changed_by, reason, created_at) VALUES (?, ?, 'replace', ?, ?, ?, ?, ?)",
                       (iso, shift["shift_type"], shift["user_id"], new_user["id"], me, reason, now_str()))
            db.commit()
            flash(f"Pamaina perduota: {shift['full_name']} → {new_user['full_name']}.", "success")
        else:
            db.execute("DELETE FROM shifts WHERE id = ?", (shift_id,))
            db.execute("INSERT INTO shift_changes (shift_date, shift_type, action, from_user_id, "
                       "to_user_id, changed_by, reason, created_at) VALUES (?, ?, 'cancel', ?, NULL, ?, ?, ?)",
                       (iso, shift["shift_type"], shift["user_id"], me, reason, now_str()))
            db.commit()
            flash("Pamaina atšaukta.", "success")
    else:
        flash("Neteisingas veiksmas.", "error")

    return back