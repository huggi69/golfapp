import sqlite3
from pathlib import Path

from flask import current_app, g


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


# Spalten, die nach der ersten Version hinzugekommen sind: (Tabelle, Spalte, Definition)
MIGRATIONS = [
    ("players", "hcp_index", "REAL"),
    ("players", "password_hash", "TEXT"),
    ("courses", "stroke_index", "TEXT NOT NULL DEFAULT ''"),
    ("round_holes", "stroke_index", "INTEGER"),
    ("round_players", "hcp_index", "REAL"),
    ("round_players", "tee_name", "TEXT NOT NULL DEFAULT ''"),
    ("round_players", "course_rating", "REAL"),
    ("round_players", "slope", "INTEGER"),
]


def _migrate(conn):
    # round_holes.par war anfangs NOT NULL – für importierte Runden ohne Par-Angabe lockern.
    par = [r for r in conn.execute("PRAGMA table_info(round_holes)") if r[1] == "par"]
    if par and par[0][3]:  # notnull
        conn.executescript("""
            PRAGMA foreign_keys = OFF;
            ALTER TABLE round_holes RENAME TO round_holes_old;
            CREATE TABLE round_holes (
                round_id    INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
                hole        INTEGER NOT NULL,
                par         INTEGER CHECK (par IS NULL OR par BETWEEN 3 AND 6),
                ntp_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
                stroke_index  INTEGER,
                PRIMARY KEY (round_id, hole)
            );
        """)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(round_holes_old)")}
        si = "stroke_index" if "stroke_index" in cols else "NULL"
        conn.execute(
            "INSERT INTO round_holes (round_id, hole, par, ntp_player_id, stroke_index) "
            f"SELECT round_id, hole, par, ntp_player_id, {si} FROM round_holes_old"
        )
        conn.executescript("DROP TABLE round_holes_old; PRAGMA foreign_keys = ON;")
    for table, column, definition in MIGRATIONS:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db(app):
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(app.config["DATABASE"])
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(schema)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
    app.teardown_appcontext(close_db)
