CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    active      INTEGER NOT NULL DEFAULT 1,
    hcp_index   REAL,                          -- aktueller Handicap-Index (Vorschlag für neue Runden)
    password_hash TEXT                         -- NULL = kein Login
);

CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    -- Kommagetrennte Par-Werte, z.B. "4,4,3,5,..." (9 oder 18 Löcher)
    pars        TEXT    NOT NULL,
    -- Kommagetrennte Handicap-Reihenfolge je Loch (1 = schwerstes Loch), leer = unbekannt
    stroke_index TEXT   NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS course_tees (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id     INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    name          TEXT    NOT NULL,            -- z.B. "Gelb Herren"
    course_rating REAL    NOT NULL,
    slope         INTEGER NOT NULL CHECK (slope BETWEEN 55 AND 155),
    UNIQUE (course_id, name)
);

CREATE TABLE IF NOT EXISTS rounds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    played_on   TEXT    NOT NULL,              -- ISO-Datum YYYY-MM-DD
    course_name TEXT    NOT NULL,
    round_type  TEXT    NOT NULL DEFAULT 'normal'
                CHECK (round_type IN ('normal', 'final_four')),
    -- Grundlage für das Lochspiel: 'net' = Nettopunkte je Loch, 'gross' = Schläge je Loch
    match_basis TEXT    NOT NULL DEFAULT 'net'
                CHECK (match_basis IN ('net', 'gross')),
    notes       TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS round_holes (
    round_id    INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    hole        INTEGER NOT NULL,
    par         INTEGER CHECK (par IS NULL OR par BETWEEN 3 AND 6),  -- NULL = unbekannt
    -- Gewinner Nearest to the Pin (nur Par-3-Löcher), NULL = niemand auf dem Grün
    ntp_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    stroke_index  INTEGER,                     -- Handicap-Reihenfolge, NULL = unbekannt
    PRIMARY KEY (round_id, hole)
);

CREATE TABLE IF NOT EXISTS round_players (
    round_id    INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    -- Werte zum Zeitpunkt der Runde; sind alle gesetzt, werden Nettopunkte berechnet
    hcp_index     REAL,
    tee_name      TEXT    NOT NULL DEFAULT '',
    course_rating REAL,
    slope         INTEGER,
    PRIMARY KEY (round_id, player_id)
);

CREATE TABLE IF NOT EXISTS scores (
    round_id    INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
    hole        INTEGER NOT NULL,
    strokes     INTEGER CHECK (strokes IS NULL OR strokes >= 1),
    putts       INTEGER CHECK (putts IS NULL OR putts >= 0),
    net_points  INTEGER CHECK (net_points IS NULL OR net_points >= 0),
    PRIMARY KEY (round_id, player_id, hole)
);

CREATE INDEX IF NOT EXISTS idx_rounds_played_on ON rounds(played_on);

-- Einstellungen je Saison (Jahr); fehlt ein Eintrag, gilt der Standard aus der Konfiguration
CREATE TABLE IF NOT EXISTS seasons (
    year          INTEGER PRIMARY KEY,
    ff_in_annual  INTEGER NOT NULL CHECK (ff_in_annual IN (0, 1))
);
