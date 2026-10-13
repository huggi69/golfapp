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
from .handicap import playing_handicap, stableford_points, strokes_received
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


@bp.app_template_filter("hcp")
def hcp_filter(value):
    return format_hcp_index(value)


@bp.app_template_filter("decimal")
def decimal_filter(value):
    if value is None:
        return ""
    return f"{value:g}".replace(".", ",")


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


def parse_float(value):
    """Zahl mit Komma oder Punkt ('18,4' / '18.4'), leer -> None."""
    value = (value or "").strip().replace(",", ".")
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_hcp_index(value):
    """Handicap-Index; Plus-Handicaps als '+2,1' oder '-2,1' (beides = -2,1)."""
    value = (value or "").strip()
    plus = value.startswith("+")
    number = parse_float(value.lstrip("+"))
    if number is None or not -10 <= number <= 54:
        return None
    return -abs(number) if plus else number


def format_hcp_index(value):
    if value is None:
        return ""
    text = f"{abs(value):.1f}".replace(".", ",")
    return f"+{text}" if value < 0 else text


def parse_stroke_index(text, n):
    """Handicap-Reihenfolge: n verschiedene Zahlen von 1 bis 18; leer -> [] (unbekannt)."""
    text = (text or "").replace(";", ",").strip()
    if not text:
        return []
    try:
        values = [int(v) for v in text.split(",") if v.strip()]
    except ValueError:
        return None
    if len(values) != n or len(set(values)) != n or any(v < 1 or v > 18 for v in values):
        return None
    return values


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
        "SELECT p.id, p.name, p.active, rp.hcp_index, rp.tee_name, rp.course_rating, rp.slope "
        "FROM players p JOIN round_players rp ON rp.player_id = p.id "
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
    handicaps, auto_net = round_handicaps(players, holes)
    if auto_net:
        # Nettopunkte ergeben sich aus den Schlägen – berechnete Werte haben Vorrang.
        for (pid, hole), sc in scores.items():
            h = next((x for x in holes if x["hole"] == hole), None)
            if h is not None and pid in handicaps:
                sc["net_points"] = stableford_points(
                    h["par"], handicaps[pid]["received"][hole], sc["strokes"]
                )
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
        "handicaps": handicaps,
        "auto_net": auto_net,
    }


def round_handicaps(players, holes):
    """Spielvorgabe und Vorgabeschläge je Spieler.

    Rückgabe: ({player_id: {"phcp": int|None, "received": {hole: n}}}, auto_net)
    auto_net ist True, wenn für alle Spieler und Löcher genug Daten vorliegen, um die
    Nettopunkte aus den Schlägen zu berechnen.
    """
    pars_known = all(h["par"] is not None for h in holes)
    par_total = sum(h["par"] for h in holes) if pars_known else None
    si_known = pars_known and bool(holes) and all(h.get("stroke_index") for h in holes)
    si = {h["hole"]: h["stroke_index"] for h in holes} if si_known else {}
    result = {}
    auto = si_known and bool(players)
    for p in players:
        phcp = playing_handicap(
            p["hcp_index"], p["course_rating"], p["slope"], par_total, len(holes)
        )
        if phcp is None:
            auto = False
        result[p["id"]] = {
            "phcp": phcp,
            "received": strokes_received(phcp, si) if si_known else {},
        }
    return result, auto


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
    ff_in_annual = season_ff_in_annual(year)

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


def season_ff_in_annual(year):
    """Zählen Final-Four-Runden in diesem Jahr zur Jahreswertung?"""
    row = get_db().execute("SELECT ff_in_annual FROM seasons WHERE year = ?", (year,)).fetchone()
    if row is None:
        return current_app.config["FINAL_FOUR_IN_ANNUAL"]
    return bool(row["ff_in_annual"])


@bp.route("/seasons/<int:year>", methods=["POST"])
def season_update(year):
    db = get_db()
    db.execute(
        "INSERT INTO seasons (year, ff_in_annual) VALUES (?, ?) "
        "ON CONFLICT(year) DO UPDATE SET ff_in_annual = excluded.ff_in_annual",
        (year, 1 if request.form.get("ff_in_annual") else 0),
    )
    db.commit()
    return redirect(url_for("main.dashboard", year=year))


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
        stroke_index = parse_stroke_index(form.get("stroke_index"), len(pars or []))
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
        elif stroke_index is None:
            errors.append(
                f"Handicap-Reihenfolge: {len(pars)} verschiedene Zahlen von 1 bis 18 oder leer lassen."
            )
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
                "INSERT INTO round_holes (round_id, hole, par, stroke_index) VALUES (?, ?, ?, ?)",
                [
                    (round_id, i + 1, par, stroke_index[i] if stroke_index else None)
                    for i, par in enumerate(pars)
                ],
            )
            for pid in sorted(set(player_ids) & valid_ids):
                hcp_index = parse_hcp_index(form.get(f"hcp_{pid}"))
                db.execute(
                    "INSERT INTO round_players "
                    "(round_id, player_id, hcp_index, tee_name, course_rating, slope) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        round_id,
                        pid,
                        hcp_index,
                        form.get(f"tee_{pid}", "").strip(),
                        parse_float(form.get(f"cr_{pid}")),
                        _int_or_none(form.get(f"slope_{pid}")),
                    ),
                )
                if hcp_index is not None:
                    # Aktuellen Handicap-Index als Vorschlag für die nächste Runde merken
                    db.execute("UPDATE players SET hcp_index = ? WHERE id = ?", (hcp_index, pid))
            db.commit()
            flash("Runde angelegt – jetzt die Ergebnisse erfassen.", "ok")
            return redirect(url_for("main.round_edit", round_id=round_id))
        for e in errors:
            flash(e, "error")

    tees = {}
    for t in db.execute("SELECT * FROM course_tees ORDER BY course_id, name"):
        tees.setdefault(t["course_id"], []).append(
            {"name": t["name"], "cr": t["course_rating"], "slope": t["slope"]}
        )
    course_data = [
        {
            "id": c["id"],
            "name": c["name"],
            "pars": c["pars"],
            "stroke_index": c["stroke_index"],
            "tees": tees.get(c["id"], []),
        }
        for c in courses
    ]
    return render_template(
        "round_new.html",
        players=players,
        courses=course_data,
        form=form,
        today=date.today().isoformat(),
        default_pars=",".join(map(str, DEFAULT_PARS)),
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
        for pid in player_ids:
            slope = _int_or_none(form.get(f"slope_{pid}"))
            if slope is not None and not 55 <= slope <= 155:
                slope = None
            db.execute(
                "UPDATE round_players SET hcp_index = ?, tee_name = ?, course_rating = ?, slope = ? "
                "WHERE round_id = ? AND player_id = ?",
                (
                    parse_hcp_index(form.get(f"hcp_{pid}")),
                    form.get(f"tee_{pid}", "").strip(),
                    parse_float(form.get(f"cr_{pid}")),
                    slope,
                    round_id,
                    pid,
                ),
            )

        stroke_index = parse_stroke_index(
            ",".join(form.get(f"si_{h['hole']}", "") for h in data["holes"]).strip(","),
            len(data["holes"]),
        )
        if stroke_index is None:
            flash("Handicap-Reihenfolge ungültig (jede Zahl nur einmal, 1–18) – nicht übernommen.", "warn")
            stroke_index = [h["stroke_index"] for h in data["holes"]]
        elif not stroke_index:
            stroke_index = [None] * len(data["holes"])

        warnings = []
        for i, h in enumerate(data["holes"]):
            hole = h["hole"]
            par = _int_or_none(form.get(f"par_{hole}"))
            if par is None or not 3 <= par <= 6:
                par = h["par"]
            ntp = _int_or_none(form.get(f"ntp_{hole}"))
            if par not in (3, None) or ntp not in player_ids:
                ntp = None
            db.execute(
                "UPDATE round_holes SET par = ?, ntp_player_id = ?, stroke_index = ? "
                "WHERE round_id = ? AND hole = ?",
                (par, ntp, stroke_index[i], round_id, hole),
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
        if data["auto_net"]:
            # Berechnete Nettopunkte auch in der Datenbank ablegen
            db.executemany(
                "UPDATE scores SET net_points = ? WHERE round_id = ? AND player_id = ? AND hole = ?",
                [
                    (sc["net_points"], round_id, pid, hole)
                    for (pid, hole), sc in data["scores"].items()
                ],
            )
            db.commit()
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
        hcp_index = parse_hcp_index(request.form.get("hcp_index"))
        try:
            if action == "add" and name:
                db.execute(
                    "INSERT INTO players (name, hcp_index) VALUES (?, ?)", (name, hcp_index)
                )
            elif action == "update" and name and pid:
                db.execute(
                    "UPDATE players SET name = ?, hcp_index = ? WHERE id = ?",
                    (name, hcp_index, pid),
                )
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

def _save_course_fields(db, form, course_id=None):
    """Prüft Name, Par und Handicap-Reihenfolge; legt an oder aktualisiert. Gibt die id zurück."""
    name = form.get("name", "").strip()
    pars = parse_pars(form.get("pars", ""))
    if not name or pars is None:
        flash("Name und 9 oder 18 Par-Werte (3–6, kommagetrennt) angeben.", "error")
        return None
    stroke_index = parse_stroke_index(form.get("stroke_index"), len(pars))
    if stroke_index is None:
        flash(
            f"Handicap-Reihenfolge: {len(pars)} verschiedene Zahlen von 1 bis 18 oder leer lassen.",
            "error",
        )
        return None
    values = (name, ",".join(map(str, pars)), ",".join(map(str, stroke_index)))
    try:
        if course_id is None:
            course_id = db.execute(
                "INSERT INTO courses (name, pars, stroke_index) VALUES (?, ?, ?)", values
            ).lastrowid
        else:
            db.execute(
                "UPDATE courses SET name = ?, pars = ?, stroke_index = ? WHERE id = ?",
                (*values, course_id),
            )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash("Diesen Platz gibt es bereits.", "error")
        return None
    return course_id


@bp.route("/courses", methods=["GET", "POST"])
@write_access
def courses():
    db = get_db()
    if request.method == "POST":
        course_id = _save_course_fields(db, request.form)
        if course_id is not None:
            flash("Platz angelegt – jetzt die Abschläge mit Course Rating und Slope eintragen.", "ok")
            return redirect(url_for("main.course_edit", course_id=course_id))
        return redirect(url_for("main.courses"))

    rows = db.execute(
        "SELECT c.*, (SELECT COUNT(*) FROM course_tees t WHERE t.course_id = c.id) AS n_tees "
        "FROM courses c ORDER BY c.name"
    ).fetchall()
    return render_template(
        "courses.html", courses=rows, default_pars=",".join(map(str, DEFAULT_PARS))
    )


@bp.route("/courses/<int:course_id>", methods=["GET", "POST"])
@write_access
def course_edit(course_id):
    db = get_db()
    course = db.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if course is None:
        abort(404)
    if request.method == "POST":
        form = request.form
        action = form.get("action")
        if action == "delete":
            db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            db.commit()
            flash("Platz gelöscht.", "ok")
            return redirect(url_for("main.courses"))
        if action == "update":
            if _save_course_fields(db, form, course_id) is not None:
                flash("Platz gespeichert.", "ok")
        elif action in ("add_tee", "update_tee"):
            tee_name = form.get("tee_name", "").strip()
            cr = parse_float(form.get("course_rating"))
            slope = _int_or_none(form.get("slope"))
            if not tee_name or cr is None or not 20 <= cr <= 90 or slope is None or not 55 <= slope <= 155:
                flash("Abschlag: Name, Course Rating (z.B. 71,9) und Slope (55–155) angeben.", "error")
            else:
                try:
                    if action == "add_tee":
                        db.execute(
                            "INSERT INTO course_tees (course_id, name, course_rating, slope) "
                            "VALUES (?, ?, ?, ?)",
                            (course_id, tee_name, cr, slope),
                        )
                    else:
                        db.execute(
                            "UPDATE course_tees SET name = ?, course_rating = ?, slope = ? "
                            "WHERE id = ? AND course_id = ?",
                            (tee_name, cr, slope, form.get("tee_id", type=int), course_id),
                        )
                    db.commit()
                except sqlite3.IntegrityError:
                    db.rollback()
                    flash("Diesen Abschlag gibt es bereits.", "error")
        elif action == "delete_tee":
            db.execute(
                "DELETE FROM course_tees WHERE id = ? AND course_id = ?",
                (form.get("tee_id", type=int), course_id),
            )
            db.commit()
        return redirect(url_for("main.course_edit", course_id=course_id))

    tees = db.execute(
        "SELECT * FROM course_tees WHERE course_id = ? ORDER BY name", (course_id,)
    ).fetchall()
    pars = [int(p) for p in course["pars"].split(",")]
    return render_template("course_edit.html", course=course, tees=tees, par_total=sum(pars))


@bp.route("/healthz")
def healthz():
    get_db().execute("SELECT 1")
    return "ok"
