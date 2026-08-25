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
    CREATE TABLE IF NOT EXISTS game_characters (
        base_id            TEXT    PRIMARY KEY,
        name               TEXT    NOT NULL,
        type               TEXT    NOT NULL CHECK(type IN ('character', 'ship')),
        thumbnail_name     TEXT,
        image_path         TEXT,
        is_image_valid     BOOLEAN,
        alignment          TEXT,
        role               TEXT,
        factions           TEXT,
        is_galactic_legend BOOLEAN DEFAULT 0,
        is_leader          BOOLEAN DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacron_sets (
        set_id          INTEGER PRIMARY KEY,
        name            TEXT    NOT NULL,
        is_active       BOOLEAN NOT NULL DEFAULT 1,
        expiration_date TEXT,
        icon_url        TEXT,
        updated_at      TEXT    DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacron_templates (
        template_id           TEXT    PRIMARY KEY,
        set_id                INTEGER NOT NULL REFERENCES datacron_sets(set_id) ON DELETE CASCADE,
        title                 TEXT,
        is_focused            BOOLEAN NOT NULL DEFAULT 0,
        target_character_id   TEXT,
        target_character_name TEXT,
        target_character_icon TEXT,
        max_tiers             INTEGER NOT NULL DEFAULT 3,
        icon_url              TEXT,
        tiers_data            TEXT,
        updated_at            TEXT    DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacron_affixes (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        template_id          TEXT    NOT NULL REFERENCES datacron_templates(template_id) ON DELETE CASCADE,
        tier                 INTEGER NOT NULL,
        scope                INTEGER NOT NULL,
        scope_name           TEXT,
        target_unit_id       TEXT,
        target_alignment     TEXT,
        target_faction       TEXT,
        target_role          TEXT,
        stat_type            TEXT,
        stat_value           REAL,
        ability_id           TEXT,
        description          TEXT,
        icon_url             TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_datacron_affixes_unit ON datacron_affixes(target_unit_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_datacron_affixes_tpl ON datacron_affixes(template_id, tier)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_datacron_affixes_faction ON datacron_affixes(target_faction)
    """,
    """
    CREATE TABLE IF NOT EXISTS game_omicrons (
        skill_id      TEXT    PRIMARY KEY,
        omicron_tier  INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_valid_omicrons (
        base_id       TEXT NOT NULL,
        ability_name  TEXT NOT NULL,
        skill_id      TEXT,
        icon_url      TEXT,
        updated_at    TEXT DEFAULT (datetime('now')),
        PRIMARY KEY (base_id, ability_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_zetas (
        skill_id      TEXT    PRIMARY KEY,
        zeta_tier     INTEGER NOT NULL
    )
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
        league           TEXT,
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
        format         TEXT    CHECK(format IN ('3v3','5v5')),
        zone           TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gac_rounds_player ON gac_rounds(player_code, format)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gac_matches_round ON gac_matches(round_id)
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
    CREATE TABLE IF NOT EXISTS active_round_units (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id  TEXT    NOT NULL,
        base_id     TEXT    NOT NULL,
        used_type   TEXT    NOT NULL DEFAULT 'defense',
        zone        TEXT,
        slot_index  INTEGER,
        created_at  TEXT    DEFAULT (datetime('now')),
        UNIQUE(discord_id, base_id, used_type)
    )

    """,
    """
    CREATE INDEX IF NOT EXISTS idx_active_units_user ON active_round_units(discord_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS active_sector_status (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id     TEXT    NOT NULL,
        zone           TEXT    NOT NULL,
        slot_index     INTEGER NOT NULL,
        status         TEXT    NOT NULL DEFAULT 'OPEN',
        counter_offset INTEGER NOT NULL DEFAULT 0,
        created_at     TEXT    DEFAULT (datetime('now')),
        UNIQUE(discord_id, zone, slot_index)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS active_gac_session (
        discord_id        TEXT PRIMARY KEY,
        enemy_code        TEXT,
        enemy_name        TEXT,
        my_name           TEXT,
        league            TEXT,
        format            TEXT,
        enemy_roster_json TEXT,
        updated_at        TEXT DEFAULT (datetime('now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS unit_aliases (
        alias       TEXT PRIMARY KEY,
        base_id     TEXT NOT NULL,
        created_at  TEXT DEFAULT (datetime('now'))
    )
    """,
]

# Liste des instructions CREATE TABLE pour PostgreSQL.
CREATE_TABLES_PG_SQL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS players (
        id          SERIAL PRIMARY KEY,
        discord_id  TEXT    NOT NULL UNIQUE,
        ally_code   TEXT    NOT NULL UNIQUE,
        username    TEXT    NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS meta_teams (
        id           SERIAL PRIMARY KEY,
        leader_name  TEXT    NOT NULL,
        members      TEXT    NOT NULL,
        counters     TEXT,
        format       TEXT    NOT NULL CHECK(format IN ('5v5', '3v3')),
        league       TEXT    NOT NULL DEFAULT 'KYBER',
        win_rate     REAL,
        usage_rate   REAL,
        source_url   TEXT,
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_characters (
        base_id            TEXT    PRIMARY KEY,
        name               TEXT    NOT NULL,
        type               TEXT    NOT NULL CHECK(type IN ('character', 'ship')),
        thumbnail_name     TEXT,
        image_path         TEXT,
        is_image_valid     BOOLEAN,
        alignment          TEXT,
        role               TEXT,
        factions           TEXT,
        is_galactic_legend BOOLEAN DEFAULT FALSE,
        is_leader          BOOLEAN DEFAULT FALSE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacron_sets (
        set_id          INTEGER PRIMARY KEY,
        name            TEXT    NOT NULL,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        expiration_date TIMESTAMPTZ,
        icon_url        TEXT,
        updated_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacron_templates (
        template_id           TEXT    PRIMARY KEY,
        set_id                INTEGER NOT NULL REFERENCES datacron_sets(set_id) ON DELETE CASCADE,
        title                 TEXT,
        is_focused            BOOLEAN NOT NULL DEFAULT FALSE,
        target_character_id   TEXT,
        target_character_name TEXT,
        target_character_icon TEXT,
        max_tiers             INTEGER NOT NULL DEFAULT 3,
        icon_url              TEXT,
        tiers_data            TEXT,
        updated_at            TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS datacron_affixes (
        id                   SERIAL PRIMARY KEY,
        template_id          TEXT    NOT NULL REFERENCES datacron_templates(template_id) ON DELETE CASCADE,
        tier                 INTEGER NOT NULL,
        scope                INTEGER NOT NULL,
        scope_name           TEXT,
        target_unit_id       TEXT,
        target_alignment     TEXT,
        target_faction       TEXT,
        target_role          TEXT,
        stat_type            TEXT,
        stat_value           REAL,
        ability_id           TEXT,
        description          TEXT,
        icon_url             TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_datacron_affixes_unit ON datacron_affixes(target_unit_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_datacron_affixes_tpl ON datacron_affixes(template_id, tier)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_datacron_affixes_faction ON datacron_affixes(target_faction)
    """,
    """
    CREATE TABLE IF NOT EXISTS game_omicrons (
        skill_id      TEXT    PRIMARY KEY,
        omicron_tier  INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_valid_omicrons (
        base_id       TEXT NOT NULL,
        ability_name  TEXT NOT NULL,
        skill_id      TEXT,
        icon_url      TEXT,
        updated_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (base_id, ability_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_zetas (
        skill_id      TEXT    PRIMARY KEY,
        zeta_tier     INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_meta_squads (
        id             SERIAL PRIMARY KEY,
        leader_id      TEXT    NOT NULL,
        format         TEXT    NOT NULL,
        members        TEXT    NOT NULL,
        win_rate       REAL    DEFAULT 0.0,
        defense_holds  REAL    DEFAULT 0.0,
        season         TEXT,
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gac_meta_squads_leader ON gac_meta_squads(leader_id, format)
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_rounds (
        id               SERIAL PRIMARY KEY,
        season_id        TEXT    NOT NULL,
        round_number     INTEGER NOT NULL,
        player_code      TEXT    NOT NULL,
        opponent_code    TEXT,
        opponent_name    TEXT,
        result           TEXT    CHECK(result IN ('win','loss','draw')),
        player_banners   INTEGER,
        opponent_banners INTEGER,
        format           TEXT    NOT NULL DEFAULT '5v5' CHECK(format IN ('3v3','5v5')),
        league           TEXT,
        recorded_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_matches (
        id             SERIAL PRIMARY KEY,
        round_id       INTEGER NOT NULL REFERENCES gac_rounds(id) ON DELETE CASCADE,
        is_attack      BOOLEAN NOT NULL,
        attacker_team  TEXT    NOT NULL,
        defender_team  TEXT    NOT NULL,
        banners        INTEGER NOT NULL DEFAULT 0,
        outcome        TEXT    NOT NULL,
        format         TEXT    CHECK(format IN ('3v3','5v5')),
        zone           TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gac_rounds_player ON gac_rounds(player_code, format)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_gac_matches_round ON gac_matches(round_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_round_teams (
        id             SERIAL PRIMARY KEY,
        round_id       INTEGER NOT NULL REFERENCES gac_rounds(id) ON DELETE CASCADE,
        side           TEXT    NOT NULL CHECK(side IN ('offense', 'defense')),
        owner          TEXT    NOT NULL CHECK(owner IN ('player', 'opponent')),
        zone           TEXT,
        leader_id      TEXT    NOT NULL,
        members_ids    TEXT    NOT NULL,
        banners        INTEGER,
        success        BOOLEAN NOT NULL DEFAULT TRUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_global_meta (
        id           SERIAL PRIMARY KEY,
        season_id    TEXT NOT NULL,
        format       TEXT CHECK(format IN ('3v3', '5v5')),
        mode         TEXT CHECK(mode IN ('attack', 'defense')),
        squad_units  TEXT NOT NULL,
        seen         INTEGER,
        hold_percent REAL,
        avg_banners  REAL,
        updated_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS gac_counters (
        id              SERIAL PRIMARY KEY,
        season_id       TEXT    NOT NULL,
        format          TEXT    NOT NULL,
        def_leader_id   TEXT    NOT NULL,
        def_members_ids TEXT    NOT NULL,
        atk_leader_id   TEXT    NOT NULL,
        atk_members_ids TEXT    NOT NULL,
        seen            INTEGER DEFAULT 0,
        win_pct         REAL    DEFAULT 0.0,
        avg_banners     REAL    DEFAULT 0.0,
        last_updated    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
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
        id              SERIAL PRIMARY KEY,
        def_leader_id   TEXT    NOT NULL,
        def_members_ids TEXT    NOT NULL,
        format          TEXT    NOT NULL,
        atk_leader_id   TEXT    NOT NULL,
        atk_members_ids TEXT    NOT NULL,
        outcome         TEXT    NOT NULL CHECK(outcome IN ('win', 'loss')),
        player_discord_id TEXT,
        avg_relic_tier  REAL,
        recorded_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_feedback_def ON counter_feedback(def_leader_id, format)
    """,
    """
    CREATE TABLE IF NOT EXISTS active_round_units (
        id          SERIAL PRIMARY KEY,
        discord_id  TEXT    NOT NULL,
        base_id     TEXT    NOT NULL,
        used_type   TEXT    NOT NULL DEFAULT 'defense',
        zone        TEXT,
        slot_index  INTEGER,
        created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(discord_id, base_id, used_type)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_active_units_user ON active_round_units(discord_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS active_sector_status (
        id             SERIAL PRIMARY KEY,
        discord_id     TEXT    NOT NULL,
        zone           TEXT    NOT NULL,
        slot_index     INTEGER NOT NULL,
        status         TEXT    NOT NULL DEFAULT 'OPEN',
        counter_offset INTEGER NOT NULL DEFAULT 0,
        created_at     TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(discord_id, zone, slot_index)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS active_gac_session (
        discord_id        TEXT PRIMARY KEY,
        enemy_code        TEXT,
        enemy_name        TEXT,
        my_name           TEXT,
        league            TEXT,
        format            TEXT,
        enemy_roster_json TEXT,
        updated_at        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS unit_aliases (
        alias       TEXT PRIMARY KEY,
        base_id     TEXT NOT NULL,
        created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


