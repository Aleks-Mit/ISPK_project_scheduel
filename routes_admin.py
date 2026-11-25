from flask import flash, g, redirect, render_template, request, url_for

from config import ROLES
from core import app, get_db, login_required, role_required



@app.route("/settings")
@login_required
def settings():
    return render_template("placeholder.html", title="Nustatymai")



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