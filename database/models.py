"""
database/models.py — Schémas SQL des tables SQLite
"""

# Liste des instructions CREATE TABLE exécutées à l'initialisation.
CREATE_TABLES_SQL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS players (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id  TEXT    NOT NULL UNIQUE,
        ally_code   TEXT    NOT NULL UNIQUE,
        username    TEXT    NOT NULL,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_seasons (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        season      TEXT    NOT NULL,
        division    INTEGER,
        league      TEXT,
        rank        INTEGER,
        wins        INTEGER NOT NULL DEFAULT 0,
        losses      INTEGER NOT NULL DEFAULT 0,
        recorded_at TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS characters_cache (
        base_id     TEXT    PRIMARY KEY,
        name        TEXT    NOT NULL,
        data_json   TEXT    NOT NULL,
        cached_at   TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta_teams (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        leader_name  TEXT    NOT NULL,
        members      TEXT    NOT NULL,
        counters     TEXT,
        format       TEXT    NOT NULL CHECK(format IN ('5v5', '3v3')),
        win_rate     REAL,
        usage_rate   REAL,
        source_url   TEXT,
        updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
]
