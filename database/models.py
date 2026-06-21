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
        league       TEXT    NOT NULL DEFAULT 'KYBER',
        win_rate     REAL,
        usage_rate   REAL,
        source_url   TEXT,
        updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        enemy_id        TEXT    NOT NULL,
        format          TEXT    NOT NULL CHECK(format IN ('3v3', '5v5', 'fleet')),
        zone            TEXT    NOT NULL CHECK(zone IN ('North', 'South', 'Back', 'Fleet')),
        leader_id       TEXT    NOT NULL,
        members_ids     TEXT    NOT NULL,
        date_scanned    TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS counter_performance (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        enemy_leader    TEXT    NOT NULL,
        enemy_members   TEXT    NOT NULL,
        player_leader   TEXT    NOT NULL,
        player_members  TEXT    NOT NULL,
        wins            INTEGER NOT NULL DEFAULT 0,
        losses          INTEGER NOT NULL DEFAULT 0,
        target_enemy_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_characters (
        base_id        TEXT    PRIMARY KEY,
        name           TEXT    NOT NULL,
        type           TEXT    NOT NULL CHECK(type IN ('character', 'ship')),
        thumbnail_name TEXT,
        image_path     TEXT,
        is_image_valid BOOLEAN
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_omicrons (
        skill_id      TEXT    PRIMARY KEY,
        omicron_tier  INTEGER NOT NULL
    )
    """,
]
