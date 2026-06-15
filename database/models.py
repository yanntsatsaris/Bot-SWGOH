"""
database/models.py — Schémas SQL des tables SQLite
"""

# Liste des instructions CREATE TABLE exécutées à l'initialisation.
# Toujours utiliser CREATE TABLE IF NOT EXISTS pour l'idempotence.
CREATE_TABLES_SQL: list[str] = [
    # ------------------------------------------------------------------
    # Joueurs enregistrés (liaison Discord ↔ SWGOH)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS players (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_id  TEXT    NOT NULL UNIQUE,          -- Snowflake Discord
        ally_code   TEXT    NOT NULL UNIQUE,          -- Code allié SWGOH (9 chiffres)
        username    TEXT    NOT NULL,
        created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
        updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------
    # Historique des saisons GAC par joueur
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS gac_seasons (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        player_id   INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        season      TEXT    NOT NULL,          -- Ex : "S52"
        division    INTEGER,                   -- 1 à 5 (5 = Kyber)
        league      TEXT,                      -- Ex : "Kyber", "Aurodium"
        rank        INTEGER,
        wins        INTEGER NOT NULL DEFAULT 0,
        losses      INTEGER NOT NULL DEFAULT 0,
        recorded_at TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------
    # Cache des données de personnages (TTL géré applicativement)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS characters_cache (
        base_id     TEXT    PRIMARY KEY,       -- Ex : "DARTHREVAN"
        name        TEXT    NOT NULL,
        data_json   TEXT    NOT NULL,          -- Payload JSON brut de l'API
        cached_at   TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,

    # ------------------------------------------------------------------
    # Équipes méta GAC (alimentée par sync_meta.py via cron)
    # ------------------------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS meta_teams (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        leader_name  TEXT    NOT NULL,
        members      TEXT    NOT NULL,   -- JSON array de noms de personnages
        counters     TEXT,               -- JSON array de leader_name adverses
        format       TEXT    NOT NULL CHECK(format IN ('5v5', '3v3')),
        win_rate     REAL,               -- 0.0 à 1.0  (ex : 0.72 = 72%)
        usage_rate   REAL,               -- popularité relative
        source_url   TEXT,               -- URL source pour traçabilité
        updated_at   TEXT    NOT NULL DEFAULT (datetime('now'))
    )
    """,
]
