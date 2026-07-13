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
    """
    CREATE TABLE IF NOT EXISTS gac_roster_snapshots (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id    TEXT    NOT NULL,
        ally_code    TEXT,
        player_name  TEXT,
        guild_id     TEXT,
        league       INTEGER,
        division     INTEGER,
        skill_rating INTEGER,
        season_id    TEXT    NOT NULL,
        scanned_at   TEXT    NOT NULL DEFAULT (datetime('now')),
        UNIQUE(player_id, season_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_roster_units (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id INTEGER NOT NULL REFERENCES gac_roster_snapshots(id) ON DELETE CASCADE,
        unit_id     TEXT    NOT NULL,
        relic_tier  INTEGER DEFAULT 0,
        gear_tier   INTEGER DEFAULT 0,
        stars       INTEGER DEFAULT 7,
        has_omicron INTEGER DEFAULT 0,
        combat_type INTEGER DEFAULT 1
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_snapshots_season ON gac_roster_snapshots(season_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_snapshots_league ON gac_roster_snapshots(league, division)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_units_snapshot ON gac_roster_units(snapshot_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_units_unit ON gac_roster_units(unit_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gac_history_enemy ON gac_history(enemy_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_meta_squads (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        leader_id      TEXT    NOT NULL,
        format         TEXT    NOT NULL,
        members        TEXT    NOT NULL,
        win_rate       REAL    DEFAULT 0.0,
        defense_holds  REAL    DEFAULT 0.0,
        season         TEXT,
        updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gac_meta_squads_leader ON gac_meta_squads(leader_id, format)
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_rounds (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        season_id        TEXT    NOT NULL,
        round_number     INTEGER NOT NULL,
        player_code      TEXT    NOT NULL,
        opponent_code    TEXT,
        opponent_name    TEXT,
        result           TEXT    CHECK(result IN ('win','loss','draw')),
        player_banners   INTEGER,
        opponent_banners INTEGER,
        format           TEXT    NOT NULL DEFAULT '5v5' CHECK(format IN ('3v3','5v5')),
        recorded_at      TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_matches (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        round_id       INTEGER NOT NULL REFERENCES gac_rounds(id) ON DELETE CASCADE,
        is_attack      BOOLEAN NOT NULL,
        attacker_team  TEXT    NOT NULL,
        defender_team  TEXT    NOT NULL,
        banners        INTEGER NOT NULL DEFAULT 0,
        outcome        TEXT    NOT NULL,
        format         TEXT    CHECK(format IN ('3v3','5v5'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_round_teams (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        round_id       INTEGER NOT NULL REFERENCES gac_rounds(id) ON DELETE CASCADE,
        side           TEXT    NOT NULL CHECK(side IN ('offense', 'defense')),
        owner          TEXT    NOT NULL CHECK(owner IN ('player', 'opponent')),
        zone           TEXT,
        leader_id      TEXT    NOT NULL,
        members_ids    TEXT    NOT NULL,
        banners        INTEGER,
        success        BOOLEAN NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_global_meta (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        season_id    TEXT NOT NULL,
        format       TEXT CHECK(format IN ('3v3', '5v5')),
        mode         TEXT CHECK(mode IN ('attack', 'defense')),
        squad_units  TEXT NOT NULL,
        seen         INTEGER,
        hold_percent REAL,
        avg_banners  REAL,
        updated_at   TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_counters (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        season_id       TEXT    NOT NULL,
        format          TEXT    NOT NULL,
        def_leader_id   TEXT    NOT NULL,
        def_members_ids TEXT    NOT NULL,
        atk_leader_id   TEXT    NOT NULL,
        atk_members_ids TEXT    NOT NULL,
        seen            INTEGER DEFAULT 0,
        win_pct         REAL    DEFAULT 0.0,
        avg_banners     REAL    DEFAULT 0.0,
        last_updated    TEXT    NOT NULL DEFAULT (datetime('now')),
        UNIQUE(season_id, format, def_leader_id, def_members_ids, atk_leader_id, atk_members_ids)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_counters_def    ON gac_counters(def_leader_id, format, season_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_counters_season ON gac_counters(season_id, format)
    """,
    """
    CREATE TABLE IF NOT EXISTS counter_feedback (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        def_leader_id   TEXT    NOT NULL,
        def_members_ids TEXT    NOT NULL,
        format          TEXT    NOT NULL,
        atk_leader_id   TEXT    NOT NULL,
        atk_members_ids TEXT    NOT NULL,
        outcome         TEXT    NOT NULL CHECK(outcome IN ('win', 'loss')),
        player_discord_id TEXT,
        avg_relic_tier  REAL,
        recorded_at     TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_feedback_def ON counter_feedback(def_leader_id, format)
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_unit_slugs (
        base_id     TEXT PRIMARY KEY,
        swgoh_slug  TEXT NOT NULL,
        FOREIGN KEY(base_id) REFERENCES game_characters(base_id)
    )
    """
]
