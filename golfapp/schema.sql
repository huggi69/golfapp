CREATE TABLE IF NOT EXISTS players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    active      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS courses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    -- Kommagetrennte Par-Werte, z.B. "4,4,3,5,..." (9 oder 18 Löcher)
    pars        TEXT    NOT NULL
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
    par         INTEGER NOT NULL CHECK (par BETWEEN 3 AND 6),
    -- Gewinner Nearest to the Pin (nur Par-3-Löcher), NULL = niemand auf dem Grün
    ntp_player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
    PRIMARY KEY (round_id, hole)
);

CREATE TABLE IF NOT EXISTS round_players (
    round_id    INTEGER NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE RESTRICT,
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
