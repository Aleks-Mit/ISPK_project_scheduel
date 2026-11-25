from datetime import date

from flask import g, render_template, request, session, url_for

from config import (DAY_NAMES, DAY_SHORT, DEMO_ANNOUNCEMENTS, MAX_MONTH_OFFSET,
                    MAX_WEEK_OFFSET, MONTHS_GENITIVE, SCHEDULE_VIEWS, SHIFT_TYPES)
from core import app, get_db, login_required
from schedule_utils import build_month, build_week, user_shift_map




@app.route("/schedule")
@login_required
def schedule():
    today = date.today()
    shifts = user_shift_map(g.user["id"], today)

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
        cells, title, shift_count = build_month(today, shifts, offset)
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
    week, monday, sunday = build_week(today, shifts, offset)
    week_shifts = [d for d in week if d["shift"]]
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
        shift_count=len(week_shifts),
        total_hours=len(week_shifts) * 8,  # kiekviena pamaina - 8 val.
        shift_types=SHIFT_TYPES,
    )



@app.route("/dashboard")
@login_required
def dashboard():
    today = date.today()

    pending_requests = get_db().execute(
        "SELECT COUNT(*) FROM requests WHERE user_id = ? AND status = 'submitted'",
        (g.user["id"],),
    ).fetchone()[0]

    shifts = user_shift_map(g.user["id"], today)
    week, monday, sunday = build_week(today, shifts)

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
        {"label": "Laukiantys prašymai", "value": pending_requests, "note": "Laukia vadovo patvirtinimo",
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
    
