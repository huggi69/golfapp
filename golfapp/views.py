import hmac
import sqlite3
from datetime import date
from fractions import Fraction
from functools import wraps

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from .db import get_db
from .scoring import CATEGORIES, evaluate_round, format_points, match_status

bp = Blueprint("main", __name__)

ROUND_TYPES = {"normal": "Normale Runde", "final_four": "Final Four"}
MATCH_BASES = {"net": "Netto (Nettopunkte je Loch)", "gross": "Brutto (Schläge je Loch)"}
DEFAULT_PARS = [4, 4, 3, 5, 4, 4, 3, 4, 5, 4, 4, 3, 5, 4, 4, 3, 4, 5]


# --------------------------------------------------------------------------
# Zugriffsschutz
# --------------------------------------------------------------------------

def _authorized():
    password = current_app.config["APP_PASSWORD"]
    if not password:
        return True
    auth = request.authorization
    return bool(auth and auth.password and hmac.compare_digest(auth.password, password))


def _auth_required():
    return Response(
        "Anmeldung erforderlich.", 401, {"WWW-Authenticate": 'Basic realm="Golf Duell"'}
    )


def write_access(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _authorized():
            return _auth_required()
        return view(*args, **kwargs)

    return wrapped


@bp.before_request
def protect_writes():
    if request.method not in ("GET", "HEAD", "OPTIONS") and not _authorized():
        return _auth_required()


@bp.app_template_filter("points")
def points_filter(value):
    return format_points(value)


@bp.app_template_filter("player_names")
def player_names_filter(ids, names):
    return " / ".join(names.get(i, "?") for i in ids)


@bp.app_template_filter("de_date")
def de_date_filter(value):
    try:
        return date.fromisoformat(value).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return value


@bp.app_context_processor
def inject_globals():
    return {"ROUND_TYPES": ROUND_TYPES, "MATCH_BASES": MATCH_BASES, "CATEGORIES": CATEGORIES}


# --------------------------------------------------------------------------
# Hilfsfunktionen
# --------------------------------------------------------------------------

def _int_or_none(value):
    value = (value or "").strip()
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_pars(text):
    try:
        pars = [int(p) for p in text.replace(";", ",").split(",") if p.strip()]
    except ValueError:
        return None
    if len(pars) not in (9, 18) or any(p < 3 or p > 6 for p in pars):
        return None
    return pars


def load_round(round_id):
    db = get_db()
    rnd = db.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()
    if rnd is None:
        abort(404)
    players = db.execute(
        "SELECT p.* FROM players p JOIN round_players rp ON rp.player_id = p.id "
        "WHERE rp.round_id = ? ORDER BY p.id",
        (round_id,),
    ).fetchall()
    holes = [
        dict(r)
        for r in db.execute(
            "SELECT * FROM round_holes WHERE round_id = ? ORDER BY hole", (round_id,)
        )
    ]
    scores = {
        (r["player_id"], r["hole"]): dict(r)
        for r in db.execute("SELECT * FROM scores WHERE round_id = ?", (round_id,))
    }
    player_ids = [p["id"] for p in players]
    result = evaluate_round(player_ids, holes, scores, rnd["match_basis"])
    names = {p["id"]: p["name"] for p in players}
    status = None
    if result.complete:
        status = match_status(result.categories[0].values, names)
    return {
        "round": rnd,
        "players": players,
        "names": names,
        "holes": holes,
        "scores": scores,
        "result": result,
        "match_status": status,
    }


def _rounds_for_year(year):
    db = get_db()
    return db.execute(
        "SELECT id FROM rounds WHERE played_on BETWEEN ? AND ? ORDER BY played_on, id",
        (f"{year}-01-01", f"{year}-12-31"),
    ).fetchall()


def _empty_standing(players):
    return {
        p["id"]: {
            "player": p,
            "points": Fraction(0),
            "rounds": 0,
            "cats": {key: Fraction(0) for key, _, _ in CATEGORIES},
        }
        for p in players
    }


def _add_to_standing(standing, data):
    for pid in data["names"]:
        if pid not in standing:
            continue
        standing[pid]["rounds"] += 1
        standing[pid]["points"] += data["result"].points[pid]
        for cat in data["result"].categories:
            standing[pid]["cats"][cat.key] += cat.points[pid]


def _sorted_standing(standing):
    rows = [s for s in standing.values() if s["rounds"] or s["player"]["active"]]
    return sorted(rows, key=lambda s: (-s["points"], s["player"]["name"].lower()))


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------

@bp.route("/")
def dashboard():
    db = get_db()
    year = request.args.get("year", type=int) or date.today().year
    years = {date.today().year, year}
    years.update(
        int(r["y"]) for r in db.execute("SELECT DISTINCT substr(played_on, 1, 4) AS y FROM rounds")
    )
    players = db.execute("SELECT * FROM players ORDER BY id").fetchall()
    ff_in_annual = current_app.config["FINAL_FOUR_IN_ANNUAL"]

    annual = _empty_standing(players)
    final_four = _empty_standing(players)
    rounds = []
    ff_count = 0
    for row in _rounds_for_year(year):
        data = load_round(row["id"])
        rounds.append(data)
        is_ff = data["round"]["round_type"] == "final_four"
        ff_count += is_ff
        if not data["result"].complete:
            continue
        if is_ff:
            _add_to_standing(final_four, data)
        if not is_ff or ff_in_annual:
            _add_to_standing(annual, data)

    rounds.reverse()  # neueste zuerst
    return render_template(
        "dashboard.html",
        year=year,
        years=sorted(years, reverse=True),
        annual=_sorted_standing(annual),
        final_four=_sorted_standing(final_four),
        ff_count=ff_count,
        ff_in_annual=ff_in_annual,
        rounds=rounds,
    )


# --------------------------------------------------------------------------
# Runden
# --------------------------------------------------------------------------

@bp.route("/rounds/new", methods=["GET", "POST"])
@write_access
def round_new():
    db = get_db()
    players = db.execute("SELECT * FROM players WHERE active = 1 ORDER BY id").fetchall()
    courses = db.execute("SELECT * FROM courses ORDER BY name").fetchall()
    form = request.form

    if request.method == "POST":
        played_on = form.get("played_on", "")
        course_name = form.get("course_name", "").strip()
        round_type = form.get("round_type", "normal")
        match_basis = form.get("match_basis", "net")
        pars = parse_pars(form.get("pars", ""))
        player_ids = [int(p) for p in form.getlist("players") if p.isdigit()]

        errors = []
        try:
            date.fromisoformat(played_on)
        except ValueError:
            errors.append("Bitte ein gültiges Datum angeben.")
        if not course_name:
            errors.append("Bitte einen Platz angeben.")
        if round_type not in ROUND_TYPES:
            errors.append("Ungültiger Rundentyp.")
        if match_basis not in MATCH_BASES:
            errors.append("Ungültige Lochspiel-Wertung.")
        if pars is None:
            errors.append("Par-Werte: 9 oder 18 Zahlen zwischen 3 und 6, durch Komma getrennt.")
        valid_ids = {p["id"] for p in players}
        if len(set(player_ids) & valid_ids) < 2:
            errors.append("Bitte mindestens zwei Spieler auswählen.")

        if not errors:
            cur = db.execute(
                "INSERT INTO rounds (played_on, course_name, round_type, match_basis, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (played_on, course_name, round_type, match_basis, form.get("notes", "").strip()),
            )
            round_id = cur.lastrowid
            db.executemany(
                "INSERT INTO round_holes (round_id, hole, par) VALUES (?, ?, ?)",
                [(round_id, i + 1, par) for i, par in enumerate(pars)],
            )
            db.executemany(
                "INSERT INTO round_players (round_id, player_id) VALUES (?, ?)",
                [(round_id, pid) for pid in sorted(set(player_ids) & valid_ids)],
            )
            db.commit()
            flash("Runde angelegt – jetzt die Ergebnisse erfassen.", "ok")
            return redirect(url_for("main.round_edit", round_id=round_id))
        for e in errors:
            flash(e, "error")

    default_course = courses[0] if courses else None
    return render_template(
        "round_new.html",
        players=players,
        courses=courses,
        form=form,
        today=date.today().isoformat(),
        default_pars=default_course["pars"] if default_course else ",".join(map(str, DEFAULT_PARS)),
        default_course=default_course["name"] if default_course else "",
    )


@bp.route("/rounds/<int:round_id>")
def round_view(round_id):
    return render_template("round_view.html", **load_round(round_id))


@bp.route("/rounds/<int:round_id>/edit", methods=["GET", "POST"])
@write_access
def round_edit(round_id):
    data = load_round(round_id)
    if request.method == "POST":
        db = get_db()
        form = request.form
        played_on = form.get("played_on", "")
        try:
            date.fromisoformat(played_on)
        except ValueError:
            flash("Ungültiges Datum.", "error")
            return render_template("round_edit.html", **data)
        round_type = form.get("round_type")
        match_basis = form.get("match_basis")
        if round_type not in ROUND_TYPES or match_basis not in MATCH_BASES:
            abort(400)
        db.execute(
            "UPDATE rounds SET played_on = ?, course_name = ?, round_type = ?, match_basis = ?, "
            "notes = ? WHERE id = ?",
            (
                played_on,
                form.get("course_name", "").strip() or data["round"]["course_name"],
                round_type,
                match_basis,
                form.get("notes", "").strip(),
                round_id,
            ),
        )

        player_ids = {p["id"] for p in data["players"]}
        warnings = []
        for h in data["holes"]:
            hole = h["hole"]
            par = _int_or_none(form.get(f"par_{hole}"))
            if par is None or not 3 <= par <= 6:
                par = h["par"]
            ntp = _int_or_none(form.get(f"ntp_{hole}"))
            if par != 3 or ntp not in player_ids:
                ntp = None
            db.execute(
                "UPDATE round_holes SET par = ?, ntp_player_id = ? WHERE round_id = ? AND hole = ?",
                (par, ntp, round_id, hole),
            )
            for pid in player_ids:
                strokes = _int_or_none(form.get(f"s_{pid}_{hole}"))
                putts = _int_or_none(form.get(f"p_{pid}_{hole}"))
                net = _int_or_none(form.get(f"n_{pid}_{hole}"))
                if strokes is not None and strokes < 1:
                    strokes = None
                if putts is not None and putts < 0:
                    putts = None
                if net is not None and net < 0:
                    net = None
                if strokes is not None and putts is not None and putts >= strokes:
                    warnings.append(
                        f"Loch {hole}, {data['names'][pid]}: mehr Putts als Schläge?"
                    )
                db.execute(
                    "INSERT INTO scores (round_id, player_id, hole, strokes, putts, net_points) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(round_id, player_id, hole) DO UPDATE SET "
                    "strokes = excluded.strokes, putts = excluded.putts, "
                    "net_points = excluded.net_points",
                    (round_id, pid, hole, strokes, putts, net),
                )
        db.commit()
        for w in warnings:
            flash(w, "warn")
        data = load_round(round_id)
        if data["result"].complete:
            flash("Gespeichert – die Runde ist vollständig und wurde ausgewertet.", "ok")
            if not warnings:
                return redirect(url_for("main.round_view", round_id=round_id))
        else:
            flash(
                f"Zwischenstand gespeichert. Es fehlen noch {data['result'].missing} Eingaben.",
                "ok",
            )
    return render_template("round_edit.html", **data)


@bp.route("/rounds/<int:round_id>/delete", methods=["POST"])
def round_delete(round_id):
    db = get_db()
    db.execute("DELETE FROM rounds WHERE id = ?", (round_id,))
    db.commit()
    flash("Runde gelöscht.", "ok")
    return redirect(url_for("main.dashboard"))


# --------------------------------------------------------------------------
# Spieler
# --------------------------------------------------------------------------

@bp.route("/players", methods=["GET", "POST"])
@write_access
def players():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        pid = request.form.get("id", type=int)
        name = request.form.get("name", "").strip()
        try:
            if action == "add" and name:
                db.execute("INSERT INTO players (name) VALUES (?)", (name,))
            elif action == "rename" and name and pid:
                db.execute("UPDATE players SET name = ? WHERE id = ?", (name, pid))
            elif action == "toggle" and pid:
                db.execute("UPDATE players SET active = 1 - active WHERE id = ?", (pid,))
            elif action == "delete" and pid:
                db.execute("DELETE FROM players WHERE id = ?", (pid,))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            if action == "delete":
                flash("Spieler hat bereits Runden gespielt – bitte stattdessen deaktivieren.", "error")
            else:
                flash("Diesen Namen gibt es bereits.", "error")
        return redirect(url_for("main.players"))

    rows = db.execute(
        "SELECT p.*, (SELECT COUNT(*) FROM round_players rp WHERE rp.player_id = p.id) AS n_rounds "
        "FROM players p ORDER BY p.id"
    ).fetchall()
    return render_template("players.html", players=rows)


# --------------------------------------------------------------------------
# Plätze
# --------------------------------------------------------------------------

@bp.route("/courses", methods=["GET", "POST"])
@write_access
def courses():
    db = get_db()
    if request.method == "POST":
        action = request.form.get("action")
        cid = request.form.get("id", type=int)
        name = request.form.get("name", "").strip()
        if action == "delete" and cid:
            db.execute("DELETE FROM courses WHERE id = ?", (cid,))
            db.commit()
            return redirect(url_for("main.courses"))
        pars = parse_pars(request.form.get("pars", ""))
        if not name or pars is None:
            flash("Name und 9 oder 18 Par-Werte (3–6, kommagetrennt) angeben.", "error")
            return redirect(url_for("main.courses"))
        pars_text = ",".join(map(str, pars))
        try:
            if action == "add":
                db.execute("INSERT INTO courses (name, pars) VALUES (?, ?)", (name, pars_text))
            elif action == "update" and cid:
                db.execute(
                    "UPDATE courses SET name = ?, pars = ? WHERE id = ?", (name, pars_text, cid)
                )
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            flash("Diesen Platz gibt es bereits.", "error")
        return redirect(url_for("main.courses"))

    rows = db.execute("SELECT * FROM courses ORDER BY name").fetchall()
    return render_template(
        "courses.html", courses=rows, default_pars=",".join(map(str, DEFAULT_PARS))
    )


@bp.route("/healthz")
def healthz():
    get_db().execute("SELECT 1")
    return "ok"
