import calendar
import csv
import io
import codecs
from datetime import date, timedelta

from flask import Response, redirect, render_template, request, url_for

from config import MONTHS_NOMINATIVE, REQUEST_TYPES, SHIFT_TYPES
from core import app, get_db, role_required
from schedule_utils import user_shift_map

HOURS_PER_SHIFT = 8
MONTHS_BACK = 6   # kiek mėnesių atgal galima generuoti ataskaitą


def month_options(today):
    """Pasirenkami mėnesiai: šis ir 6 ankstesni -> [(„2026-11“, „Lapkritis 2026“), ...]."""
    options = []
    for i in range(MONTHS_BACK + 1):
        index = today.year * 12 + (today.month - 1) - i
        year, month = index // 12, index % 12 + 1
        options.append((f"{year}-{month:02d}", f"{MONTHS_NOMINATIVE[month - 1]} {year}"))
    return options


def build_report(db, today, month_key):
    """Surenka mėnesio laiko apskaitos duomenis visiems aktyviems naudotojams."""
    year, month = int(month_key[:4]), int(month_key[5:])
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    label = f"{MONTHS_NOMINATIVE[month - 1]} {year}"

    users = db.execute(
        "SELECT id, full_name, email FROM users WHERE is_active = 1 "
        "ORDER BY full_name COLLATE NOCASE"
    ).fetchall()

    # 1) Patvirtinti prašymai, kurių laikotarpis kerta šį mėnesį (su prisegtais dokumentais)
    req_rows = db.execute(
        "SELECT r.*, u.full_name, u.email, a.full_name AS approver "
        "FROM requests r JOIN users u ON u.id = r.user_id "
        "LEFT JOIN users a ON a.id = r.reviewed_by "
        "WHERE r.status = 'approved' AND r.start_date <= ? AND r.end_date >= ? "
        "ORDER BY u.full_name COLLATE NOCASE, r.start_date",
        (last.isoformat(), first.isoformat()),
    ).fetchall()

    approved, absent = [], {}          # absent: {user_id: {data: prašymo tipas}}
    for r in req_rows:
        start = max(date.fromisoformat(r["start_date"]), first)
        end = min(date.fromisoformat(r["end_date"]), last)
        item = dict(r)
        item["files"] = db.execute(
            "SELECT id, original_name FROM request_files WHERE request_id = ?", (r["id"],)
        ).fetchall()
        item["days_in_month"] = (end - start).days + 1
        approved.append(item)
        for i in range(item["days_in_month"]):
            absent.setdefault(r["user_id"], {})[start + timedelta(days=i)] = r["type"]

    # 2) Vadovų atlikti pamainų pakeitimai šį mėnesį (iš pakeitimų žurnalo)
    change_rows = db.execute(
        "SELECT c.*, f.full_name AS from_name, t.full_name AS to_name, b.full_name AS by_name "
        "FROM shift_changes c JOIN users f ON f.id = c.from_user_id "
        "LEFT JOIN users t ON t.id = c.to_user_id JOIN users b ON b.id = c.changed_by "
        "WHERE c.shift_date BETWEEN ? AND ? ORDER BY c.shift_date, c.id",
        (first.isoformat(), last.isoformat()),
    ).fetchall()
    changes = [{**dict(c), "shift_name": SHIFT_TYPES[c["shift_type"]][0]} for c in change_rows]
    taken, given = {}, {}
    for c in changes:
        given[c["from_user_id"]] = given.get(c["from_user_id"], 0) + 1
        if c["to_user_id"]:
            taken[c["to_user_id"]] = taken.get(c["to_user_id"], 0) + 1

    # 3) Kiekvieno darbuotojo faktinis išdirbis (pagal GALUTINĮ tvarkaraštį po pakeitimų)
    rows, adjustments = [], []
    for u in users:
        month_shifts = {d: k for d, k in user_shift_map(u["id"], today).items()
                        if first <= d <= last}
        user_absent = absent.get(u["id"], {})

        unworked = sorted(d for d in month_shifts if d in user_absent)
        remaining = [d for d in month_shifts if d not in user_absent]
        worked = [d for d in remaining if d <= today]

        for d in unworked:
            adjustments.append({
                "name": u["full_name"], "date": d.isoformat(),
                "shift": SHIFT_TYPES[month_shifts[d]][0],
                "reason": REQUEST_TYPES.get(user_absent[d], user_absent[d]),
            })

        kinds = list(user_absent.values())
        rows.append({
            "name": u["full_name"],
            "email": u["email"],
            "planned": len(month_shifts),
            "cancelled": len(unworked),
            "taken_over": taken.get(u["id"], 0),
            "given_away": given.get(u["id"], 0),
            "worked": len(worked),
            "worked_hours": len(worked) * HOURS_PER_SHIFT,
            "vacation_days": kinds.count("vacation"),
            "sick_days": kinds.count("sick"),
            "other_days": kinds.count("personal") + kinds.count("other"),
        })

    totals = {k: sum(r[k] for r in rows) for k in
              ("planned", "cancelled", "taken_over", "given_away", "worked",
               "worked_hours", "vacation_days", "sick_days", "other_days")}

    return {"key": month_key, "label": label, "first": first, "last": last,
            "rows": rows, "totals": totals, "approved": approved,
            "adjustments": adjustments, "changes": changes}


@app.route("/hr")
@role_required("hr", "admin")
def hr_section():
    today = date.today()
    options = month_options(today)
    month_key = request.args.get("month", "")
    report = None
    if month_key in dict(options):
        report = build_report(get_db(), today, month_key)
    else:
        month_key = options[0][0]
    return render_template("hr.html", options=options, month_key=month_key,
                           report=report, types=REQUEST_TYPES,
                           hours_per_shift=HOURS_PER_SHIFT)


def safe_cell(value):
    """Apsauga nuo formulių įterpimo atidarant CSV Excel programoje."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


@app.route("/hr/report.csv")
@role_required("hr", "admin")
def hr_report_csv():
    today = date.today()
    month_key = request.args.get("month", "")
    if month_key not in dict(month_options(today)):
        return redirect(url_for("hr_section"))
    part = request.args.get("part", "summary")
    if part not in ("summary", "requests", "adjustments", "changes"):
        part = "summary"

    report = build_report(get_db(), today, month_key)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t")     # lietuviškas Excel naudoja kabliataškį

    if part == "summary":
        w.writerow(["Darbuotojas", "El. paštas", "Priskirta pamainų",
                    "Neišdirbta dėl nebuvimo", "Perimta pamainų", "Perduota pamainų",
                    "Išdirbtos pamainos", "Išdirbta val.",
                    "Atostogų d.", "Nedarbingumo d.", "Kitų neatvykimų d."])
        for r in report["rows"]:
            w.writerow([safe_cell(r["name"]), safe_cell(r["email"]), r["planned"],
                        r["cancelled"], r["taken_over"], r["given_away"], r["worked"],
                        r["worked_hours"], r["vacation_days"], r["sick_days"], r["other_days"]])
        t = report["totals"]
        w.writerow(["IŠ VISO", "", t["planned"], t["cancelled"], t["taken_over"],
                    t["given_away"], t["worked"], t["worked_hours"],
                    t["vacation_days"], t["sick_days"], t["other_days"]])
    elif part == "requests":
        w.writerow(["Darbuotojas", "Tipas", "Nuo", "Iki", "Dienos šį mėnesį",
                    "Priežastis", "Dokumentai", "Patvirtino", "Vadovo komentaras"])
        for r in report["approved"]:
            w.writerow([safe_cell(r["full_name"]), REQUEST_TYPES.get(r["type"], r["type"]),
                        r["start_date"], r["end_date"], r["days_in_month"],
                        safe_cell(r["reason"]),
                        safe_cell(", ".join(f["original_name"] for f in r["files"])),
                        safe_cell(r["approver"] or ""), safe_cell(r["review_comment"] or "")])
    elif part == "adjustments":
        w.writerow(["Darbuotojas", "Data", "Neišdirbta pamaina", "Priežastis"])
        for a in report["adjustments"]:
            w.writerow([safe_cell(a["name"]), a["date"], a["shift"], a["reason"]])
    else:
        w.writerow(["Pamainos data", "Pamaina", "Veiksmas", "Iš darbuotojo",
                    "Darbuotojui", "Vadovas", "Priežastis", "Atlikta"])
        for c in report["changes"]:
            w.writerow([c["shift_date"], c["shift_name"],
                        "Pakeista" if c["action"] == "replace" else "Atšaukta",
                        safe_cell(c["from_name"]), safe_cell(c["to_name"] or ""),
                        safe_cell(c["by_name"]), safe_cell(c["reason"] or ""),
                        c["created_at"][:16]])

    return Response(
    codecs.BOM_UTF16_LE + buf.getvalue().encode("utf-16-le"),
    mimetype="text/csv; charset=utf-16",
        headers={"Content-Disposition":
                 f'attachment; filename="laiko-apskaita-{month_key}-{part}.csv"'},
    )