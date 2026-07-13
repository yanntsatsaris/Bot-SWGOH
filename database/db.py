"""
database/db.py — Gestion de la connexion SQLite asynchrone
"""
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

from config import DATABASE_PATH

log = logging.getLogger(__name__)


async def init_db() -> None:
    """Crée le dossier si nécessaire puis initialise toutes les tables."""
    from database.models import CREATE_TABLES_SQL

    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")   # Meilleures perf. en concurrence
        await db.execute("PRAGMA foreign_keys = ON")
        for sql in CREATE_TABLES_SQL:
            await db.execute(sql)
            
        # Migration : Ajouter 'league' à 'meta_teams' si elle n'existe pas
        try:
            await db.execute("ALTER TABLE meta_teams ADD COLUMN league TEXT NOT NULL DEFAULT 'KYBER'")
            log.info("Migration: colonne 'league' ajoutée à meta_teams.")
        except aiosqlite.OperationalError:
            pass  # La colonne existe déjà

        # Migrations GAC Rounds et Matches
        migrations = [
            "ALTER TABLE gac_rounds ADD COLUMN opponent_code TEXT",
            "ALTER TABLE gac_rounds ADD COLUMN result TEXT",
            "ALTER TABLE gac_rounds ADD COLUMN player_banners INTEGER",
            "ALTER TABLE gac_rounds ADD COLUMN opponent_banners INTEGER",
            "ALTER TABLE gac_rounds ADD COLUMN format TEXT NOT NULL DEFAULT '5v5'",
            "ALTER TABLE gac_matches ADD COLUMN format TEXT",
            "ALTER TABLE gac_matches ADD COLUMN zone TEXT"
        ]
        for migration in migrations:
            try:
                await db.execute(migration)
                log.info(f"Migration appliquée : {migration}")
            except aiosqlite.OperationalError:
                pass # Colonne existante
            
        await db.commit()

    log.info("Base de données initialisée : %s", DATABASE_PATH)


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """
    Gestionnaire de contexte asynchrone pour obtenir une connexion.

    Usage :
        async with get_db() as db:
            await db.execute(...)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise

import json

async def save_gac_history_to_db(parsed_data: dict, ally_code: str):
    """
    Sauvegarde l'historique scrapé en base de données SQLite.
    Insère un round et ses matchs associés.
    """
    if not parsed_data.get("matches"):
        return
        
    async with get_db() as db:
        # 1. On détermine le Round, la Saison et l'adversaire (à partir du 1er match)
        first_match = parsed_data["matches"][0]
        season_id = "UNKNOWN"
        opponent_name = "UNKNOWN"
        round_number = 1
        
        # L'ally_code passé ici est le target_url (ex: https://swgoh.gg/p/266539582/gac-history/O1782248400000/1/)
        # On extrait les vraies valeurs
        real_ally_code = ally_code
        if "swgoh.gg/p/" in ally_code:
            parts = [p for p in ally_code.split("/") if p]
            try:
                # ex: ['https:', 'swgoh.gg', 'p', '266539582', 'gac-history', 'O1782248400000', '1']
                p_index = parts.index("p")
                real_ally_code = parts[p_index + 1]
                
                hist_index = parts.index("gac-history")
                season_id = parts[hist_index + 1]
                round_number = int(parts[hist_index + 2])
            except:
                pass
                
        # Vérification des doublons : on regarde si ce round exact a déjà été enregistré
        cursor = await db.execute(
            "SELECT id FROM gac_rounds WHERE player_code = ? AND season_id = ? AND round_number = ?",
            (real_ally_code, season_id, round_number)
        )
        existing = await cursor.fetchone()
        
        if existing:
            log.info(f"⏭️ Historique déjà présent en BDD pour {real_ally_code} (Saison: {season_id}, Round: {round_number}). On ignore.")
            return
        
        # 2. Insertion du Round
        # On utilise le format détecté dans _parse_html (défaut '5v5')
        detected_format = parsed_data.get("format", "5v5")
        cursor = await db.execute(
            """
            INSERT INTO gac_rounds (season_id, round_number, player_code, opponent_name, format)
            VALUES (?, ?, ?, ?, ?)
            """,
            (season_id, round_number, real_ally_code, opponent_name, detected_format)
        )
        round_id = cursor.lastrowid
        
        # 3. Insertion des matchs associés
        for match in parsed_data["matches"]:
            attacker_json = json.dumps(match.get("attacker_team", []))
            defender_json = json.dumps(match.get("defender_team", []))
            
            await db.execute(
                """
                INSERT INTO gac_matches 
                (round_id, is_attack, attacker_team, defender_team, banners, outcome, format, zone)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (round_id, match["is_attack"], attacker_json, defender_json, 
                 match.get("banners", 0), match.get("outcome", "Unknown"), detected_format, match.get("zone", "unknown"))
            )
        
        await db.commit()
        log.info(f"✅ {len(parsed_data['matches'])} matchs sauvegardés en BDD pour {real_ally_code} (Round ID: {round_id})")

async def save_counters_to_db(season_id: str, format_type: str, def_leader_id: str, counters_data: list[dict]):
    """
    Sauvegarde les counters extraits de swgoh.gg en base de données.
    """
    async with get_db() as db:
        for counter in counters_data:
            def_members_json = json.dumps(counter.get("def_members_ids", []))
            atk_leader_id = counter.get("atk_leader_id", "")
            atk_members_json = json.dumps(counter.get("atk_members_ids", []))
            
            # Upsert
            await db.execute(
                """
                INSERT INTO gac_counters (
                    season_id, format, def_leader_id, def_members_ids,
                    atk_leader_id, atk_members_ids, seen, win_pct, avg_banners, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(season_id, format, def_leader_id, def_members_ids, atk_leader_id, atk_members_ids)
                DO UPDATE SET
                    seen = excluded.seen,
                    win_pct = excluded.win_pct,
                    avg_banners = excluded.avg_banners,
                    last_updated = excluded.last_updated
                """,
                (
                    season_id, format_type, def_leader_id, def_members_json,
                    atk_leader_id, atk_members_json, counter.get("seen", 0),
                    counter.get("win_pct", 0.0), counter.get("avg_banners", 0.0)
                )
            )
        await db.commit()

async def get_counters_from_db(def_leader_id: str, format_type: str) -> list[dict]:
    """
    Récupère tous les counters pour un leader défensif donné.
    Retourne les données aggrégées/les plus récentes.
    """
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT season_id, def_members_ids, atk_leader_id, atk_members_ids, seen, win_pct, avg_banners
            FROM gac_counters
            WHERE def_leader_id = ? AND format = ?
            ORDER BY seen DESC
            """,
            (def_leader_id, format_type)
        )
        rows = await cursor.fetchall()
        
    results = []
    for row in rows:
        results.append({
            "season_id": row["season_id"],
            "def_leader_id": def_leader_id,
            "def_members_ids": json.loads(row["def_members_ids"]),
            "atk_leader_id": row["atk_leader_id"],
            "atk_members_ids": json.loads(row["atk_members_ids"]),
            "seen": row["seen"],
            "win_pct": row["win_pct"],
            "avg_banners": row["avg_banners"]
        })
    return results

async def record_counter_feedback(def_leader_id: str, def_members_ids: list[str], atk_leader_id: str, atk_members_ids: list[str], format_type: str, outcome: str, player_discord_id: str):
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO counter_feedback (
                def_leader_id, def_members_ids, format,
                atk_leader_id, atk_members_ids, outcome, player_discord_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                def_leader_id, json.dumps(sorted(def_members_ids)), format_type,
                atk_leader_id, json.dumps(sorted(atk_members_ids)), outcome, player_discord_id
            )
        )
        await db.commit()

async def get_counter_feedback_stats(atk_leader_id: str, def_leader_id: str, format_type: str) -> dict:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN outcome = 'win' THEN 1 ELSE 0 END) as wins
            FROM counter_feedback
            WHERE atk_leader_id = ? AND def_leader_id = ? AND format = ?
            """,
            (atk_leader_id, def_leader_id, format_type)
        )
        row = await cursor.fetchone()
        
    total = row["total"] if row else 0
    wins = row["wins"] if row else 0
    win_rate = (wins / total) if total > 0 else None
    
    return {
        "total": total,
        "wins": wins,
        "win_rate": win_rate
    }
