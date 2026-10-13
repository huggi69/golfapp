"""Login der Spieler.

Ohne Login ist nichts erreichbar (außer Login-Seite, Healthcheck und statischen Dateien).
Alle eingeloggten Spieler haben die gleichen Rechte.

Solange noch kein Spieler ein Passwort hat, zeigt die Login-Seite die Ersteinrichtung:
Name und Passwort eingeben – der Spieler wird angelegt bzw. bekommt das Passwort.
"""

import time

from flask import (
    Blueprint,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

MIN_PASSWORD_LENGTH = 6
PUBLIC_ENDPOINTS = {"auth.login", "main.healthz", "static"}


def hash_password(password):
    return generate_password_hash(password)


def password_problem(password, repeat=None):
    """Fehlermeldung für ein ungeeignetes Passwort oder None."""
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen haben."
    if repeat is not None and password != repeat:
        return "Die beiden Passwörter stimmen nicht überein."
    return None


def setup_needed():
    """True, solange noch kein Spieler ein Passwort hat."""
    return get_db().execute(
        "SELECT 1 FROM players WHERE password_hash IS NOT NULL LIMIT 1"
    ).fetchone() is None


def _safe_next(target):
    # Nur relative Pfade innerhalb der App – keine Weiterleitung auf fremde Seiten
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.dashboard")


def _login(player_id):
    session.clear()
    session.permanent = True  # bleibt auch auf dem Handy über Tage angemeldet
    session["player_id"] = player_id


def load_user():
    g.user = None
    pid = session.get("player_id")
    if pid is not None:
        g.user = get_db().execute(
            "SELECT id, name FROM players WHERE id = ? AND active = 1 AND password_hash IS NOT NULL",
            (pid,),
        ).fetchone()
        if g.user is None:
            session.clear()


def require_login():
    load_user()
    if g.user is not None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if request.is_json or (request.path.startswith("/rounds/") and "/holes/" in request.path):
        return jsonify(error="Nicht angemeldet"), 401
    return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


@bp.app_context_processor
def inject_user():
    return {"current_user": g.get("user")}


@bp.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    setup = setup_needed()
    if g.get("user") is not None and not setup:
        return redirect(_safe_next(request.args.get("next")))

    if request.method == "POST":
        name = " ".join(request.form.get("name", "").split())
        password = request.form.get("password", "")
        if setup:
            problem = password_problem(password, request.form.get("password2", ""))
            if not name:
                problem = "Bitte deinen Namen angeben."
            if problem:
                flash(problem, "error")
            else:
                row = db.execute(
                    "SELECT id FROM players WHERE name = ? COLLATE NOCASE", (name,)
                ).fetchone()
                pid = row["id"] if row else db.execute(
                    "INSERT INTO players (name) VALUES (?)", (name,)
                ).lastrowid
                db.execute(
                    "UPDATE players SET password_hash = ?, active = 1 WHERE id = ?",
                    (hash_password(password), pid),
                )
                db.commit()
                _login(pid)
                flash("Willkommen! Lege unter „Spieler“ die Passwörter für deine Mitspieler fest.", "ok")
                return redirect(url_for("main.players"))
        else:
            row = db.execute(
                "SELECT id, password_hash FROM players "
                "WHERE name = ? COLLATE NOCASE AND active = 1 AND password_hash IS NOT NULL",
                (name,),
            ).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                _login(row["id"])
                return redirect(_safe_next(request.args.get("next")))
            time.sleep(0.5)  # bremst Durchprobieren von Passwörtern
            flash("Name oder Passwort falsch.", "error")

    # Ersteinrichtung: alle aktiven Spieler zur Auswahl, sonst nur die mit Login
    query = "SELECT name FROM players WHERE active = 1"
    if not setup:
        query += " AND password_hash IS NOT NULL"
    names = [r["name"] for r in db.execute(query + " ORDER BY name")]
    return render_template("login.html", setup=setup, names=names, name=request.form.get("name", ""))


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/account", methods=["GET", "POST"])
def account():
    if request.method == "POST":
        db = get_db()
        row = db.execute("SELECT password_hash FROM players WHERE id = ?", (g.user["id"],)).fetchone()
        new = request.form.get("new_password", "")
        problem = password_problem(new, request.form.get("new_password2", ""))
        if not check_password_hash(row["password_hash"], request.form.get("old_password", "")):
            problem = "Das bisherige Passwort ist falsch."
        if problem:
            flash(problem, "error")
        else:
            db.execute(
                "UPDATE players SET password_hash = ? WHERE id = ?", (hash_password(new), g.user["id"])
            )
            db.commit()
            flash("Passwort geändert.", "ok")
            return redirect(url_for("main.dashboard"))
    return render_template("account.html")
