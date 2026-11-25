import calendar
from datetime import date, timedelta

from config import (DAY_NAMES, DAY_SHORT, MONTHS_GENITIVE, MONTHS_NOMINATIVE,
                    SHIFT_TYPES, WEEK_PATTERNS)
from core import get_db




def published_until(today):
    """Paskutinė diena, iki kurios tvarkaraštis paskelbtas (kito mėnesio pabaiga)."""
    next_year = today.year + (1 if today.month == 12 else 0)
    next_month = today.month % 12 + 1
    return date(next_year, next_month, calendar.monthrange(next_year, next_month)[1])


ANCHOR_MONDAY = date(2024, 1, 1)   # pirmadienis; demonstracinio ciklo atskaitos taškas


def demo_shift_key(day, user_id):
    """Demonstracinių pamainų generatorius. Kiekvienas naudotojas gauna
    skirtingą ciklo poslinkį, todėl tvarkaraščiai nesutampa."""
    day_monday = day - timedelta(days=day.weekday())
    n = (day_monday - ANCHOR_MONDAY).days // 7 + user_id

    if n % 5 == 3:                      # kas penkta savaitė - laisva
        return None
    return WEEK_PATTERNS[n % 3][day.weekday()]


def user_shift_map(user_id, today):
    """Grąžina {data: pamainos raktas} naudotojo pamainoms.
    Demonstracinės pamainos generuojamos tik NAUJOMS dienoms (shift_seed seka, iki kada
    jau sugeneruota), todėl vadovų pakeistos ar atšauktos pamainos nebegrįžta."""
    db = get_db()
    end = published_until(today)

    seed = db.execute("SELECT seeded_until FROM shift_seed WHERE user_id = ?",
                      (user_id,)).fetchone()
    if seed is None:
        start = today - timedelta(days=220)
    else:
        start = date.fromisoformat(seed["seeded_until"]) + timedelta(days=1)

    if start <= end:
        rows = []
        day = start
        while day <= end:
            key = demo_shift_key(day, user_id)
            if key:
                rows.append((user_id, day.isoformat(), key))
            day += timedelta(days=1)
        db.executemany(
            "INSERT OR IGNORE INTO shifts (user_id, shift_date, shift_type) VALUES (?, ?, ?)",
            rows,
        )
        db.execute("INSERT OR REPLACE INTO shift_seed (user_id, seeded_until) VALUES (?, ?)",
                   (user_id, end.isoformat()))
        db.commit()

    found = db.execute(
        "SELECT shift_date, shift_type FROM shifts WHERE user_id = ?", (user_id,)
    ).fetchall()
    return {date.fromisoformat(r["shift_date"]): r["shift_type"] for r in found}

def make_shift(key):
    """Pamainos žodynas šablonui (arba None, jei pamainos nėra)."""
    if not key:
        return None
    name, start, end = SHIFT_TYPES[key]
    return {"key": key, "name": name, "start": start, "end": end,
            "time": f"{start}–{end}", "ends_next_day": end < start}


def build_week(today, shifts, offset=0):
    """Pasirinktos savaitės dienos su naudotojo pamainomis.
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
            "shift": make_shift(shifts.get(day)),
            "day_obj": day,
        })
    return week, monday, monday + timedelta(days=6)


def build_month(today, shifts, offset=0):
    """Mėnesio kalendoriaus langeliai su naudotojo pamainomis."""
    index = today.year * 12 + (today.month - 1) + offset
    year, month = index // 12, index % 12 + 1
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])

    day = first - timedelta(days=first.weekday())
    end = last + timedelta(days=6 - last.weekday())

    cells = []
    while day <= end:
        cells.append({
            "day": day.day,
            "in_month": day.month == month,
            "is_today": day == today,
            "shift": make_shift(shifts.get(day)),
        })
        day += timedelta(days=1)

    shift_count = sum(1 for c in cells if c["in_month"] and c["shift"])
    return cells, f"{MONTHS_NOMINATIVE[month - 1]} {year}", shift_count






