"""
database/db.py — Gestion de la connexion SQLite asynchrone
"""
import json
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
            
        # Migration : Supprimer la contrainte CHECK de active_round_units si elle existe
        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS active_round_units_new (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    discord_id  TEXT    NOT NULL,
                    base_id     TEXT    NOT NULL,
                    used_type   TEXT    NOT NULL DEFAULT 'defense',
                    zone        TEXT,
                    slot_index  INTEGER,
                    created_at  TEXT    DEFAULT (datetime('now')),
                    UNIQUE(discord_id, base_id)
                )
            """)
            await db.execute("INSERT OR IGNORE INTO active_round_units_new SELECT * FROM active_round_units")
            await db.execute("DROP TABLE active_round_units")
            await db.execute("ALTER TABLE active_round_units_new RENAME TO active_round_units")
        except Exception:
            pass

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
        detected_league = parsed_data.get("league")
        
        cursor = await db.execute(
            """
            INSERT INTO gac_rounds (season_id, round_number, player_code, opponent_name, format, league)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (season_id, round_number, real_ally_code, opponent_name, detected_format, detected_league)
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
    max_atk_members = 2 if format_type == "3v3" else 4  # leader + N members
    for row in rows:
        atk_members = json.loads(row["atk_members_ids"])
        # Filtrer strictement : un contre 5v5 ne doit pas apparaitre en 3v3 et vice-versa
        if len(atk_members) > max_atk_members:
            continue
        results.append({
            "season_id": row["season_id"],
            "def_leader_id": def_leader_id,
            "def_members_ids": json.loads(row["def_members_ids"]),
            "atk_leader_id": row["atk_leader_id"],
            "atk_members_ids": atk_members,
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

async def add_used_units(discord_id: str, base_ids: list[str], used_type: str = "attack", zone: str = None, slot_index: int = None):
    """Enregistre une liste d'unités comme brûlées/utilisées pour le round en cours."""
    if not base_ids or not discord_id:
        return
    async with get_db() as db:
        for bid in base_ids:
            if not bid or bid in ["USED", "None", "EMPTY"]:
                continue
            await db.execute(
                """
                INSERT INTO active_round_units (discord_id, base_id, used_type, zone, slot_index)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(discord_id, base_id) DO UPDATE SET
                    used_type = excluded.used_type,
                    zone = excluded.zone,
                    slot_index = excluded.slot_index
                """,
                (discord_id, bid.upper(), used_type, zone, slot_index)
            )
        await db.commit()

async def get_used_units(discord_id: str) -> set[str]:
    """Retourne l'ensemble des base_ids des personnages brûlés/utilisés par le joueur dans le round actif."""
    if not discord_id:
        return set()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT base_id FROM active_round_units WHERE discord_id = ?",
            (discord_id,)
        )
        rows = await cursor.fetchall()
    return {row["base_id"].upper() for row in rows}

async def clear_used_units(discord_id: str | None = None):
    """Réinitialise les unités brûlées et les états de secteurs pour un joueur ou pour tous les joueurs."""
    async with get_db() as db:
        if discord_id:
            await db.execute("DELETE FROM active_round_units WHERE discord_id = ?", (discord_id,))
            await db.execute("DELETE FROM active_sector_status WHERE discord_id = ?", (discord_id,))
        else:
            await db.execute("DELETE FROM active_round_units")
            await db.execute("DELETE FROM active_sector_status")
        await db.commit()
    log.info(f"Unités brûlées et secteurs réinitialisés ({'joueur ' + discord_id if discord_id else 'tous les joueurs'}).")

async def set_sector_status(discord_id: str, zone: str, slot_index: int, status: str, counter_offset: int | None = None):
    """Met à jour le statut d'un secteur (OPEN, CLEARED, FAILED) et optionnellement son offset de contre."""
    async with get_db() as db:
        if counter_offset is not None:
            await db.execute(
                """
                INSERT INTO active_sector_status (discord_id, zone, slot_index, status, counter_offset)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(discord_id, zone, slot_index) DO UPDATE SET
                    status = excluded.status,
                    counter_offset = excluded.counter_offset
                """,
                (discord_id, zone, slot_index, status, counter_offset)
            )
        else:
            await db.execute(
                """
                INSERT INTO active_sector_status (discord_id, zone, slot_index, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(discord_id, zone, slot_index) DO UPDATE SET
                    status = excluded.status
                """,
                (discord_id, zone, slot_index, status)
            )
        await db.commit()

async def cycle_sector_counter_offset(discord_id: str, zone: str, slot_index: int) -> int:
    """Incrémente l'offset du contre pour ce secteur (Option #1 -> Option #2...) et retourne la nouvelle valeur."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT counter_offset FROM active_sector_status WHERE discord_id = ? AND zone = ? AND slot_index = ?",
            (discord_id, zone, slot_index)
        )
        row = await cursor.fetchone()
        current_offset = row["counter_offset"] if row else 0
        new_offset = (current_offset + 1) % 5
        
        await db.execute(
            """
            INSERT INTO active_sector_status (discord_id, zone, slot_index, status, counter_offset)
            VALUES (?, ?, ?, 'OPEN', ?)
            ON CONFLICT(discord_id, zone, slot_index) DO UPDATE SET
                counter_offset = excluded.counter_offset
            """,
            (discord_id, zone, slot_index, new_offset)
        )
        await db.commit()
    return new_offset

async def get_active_sector_statuses(discord_id: str) -> dict:
    """Retourne un dictionnaire {(zone, slot_index): {'status': status, 'counter_offset': offset}}."""
    if not discord_id:
        return {}
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT zone, slot_index, status, counter_offset FROM active_sector_status WHERE discord_id = ?",
            (discord_id,)
        )
        rows = await cursor.fetchall()
    return {(row["zone"], row["slot_index"]): {"status": row["status"], "counter_offset": row["counter_offset"]} for row in rows}


async def save_user_defense_slot(discord_id: str, zone: str, slot_index: int, leader_id: str, members_ids: list[str]):
    """Remplace l'équipe posée sur un emplacement (zone + slot_index) spécifique."""
    async with get_db() as db:
        await db.execute(
            "DELETE FROM active_round_units WHERE discord_id = ? AND zone = ? AND slot_index = ? AND used_type = 'defense'",
            (discord_id, zone, slot_index)
        )
        all_units = [leader_id] + [m for m in members_ids if m]
        for bid in all_units:
            if not bid or bid in ["USED", "None", "EMPTY"]:
                continue
            await db.execute(
                """
                INSERT INTO active_round_units (discord_id, base_id, used_type, zone, slot_index)
                VALUES (?, ?, 'defense', ?, ?)
                ON CONFLICT(discord_id, base_id) DO UPDATE SET
                    used_type = 'defense',
                    zone = excluded.zone,
                    slot_index = excluded.slot_index
                """,
                (discord_id, bid.upper(), zone, slot_index)
            )
        await db.commit()


async def save_user_defense_zones(discord_id: str, zones_dict: dict, used_type: str = "defense"):

    """Enregistre l'ensemble des zones de défense (joueur ou ennemie) dans active_round_units."""
    async with get_db() as db:
        await db.execute(
            "DELETE FROM active_round_units WHERE discord_id = ? AND used_type = ?",
            (discord_id, used_type)
        )
        for zone, teams in zones_dict.items():
            for idx, team in enumerate(teams, 1):
                leader = team.get("leader_id")
                members = team.get("members_ids", [])
                all_units = [leader] + [m for m in members if m]
                for bid in all_units:
                    if not bid or bid in ["USED", "None", "EMPTY"]:
                        continue
                    await db.execute(
                        """
                        INSERT INTO active_round_units (discord_id, base_id, used_type, zone, slot_index)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(discord_id, base_id) DO UPDATE SET
                            used_type = excluded.used_type,
                            zone = excluded.zone,
                            slot_index = excluded.slot_index
                        """,
                        (discord_id, bid.upper(), used_type, zone, idx)
                    )
        await db.commit()

async def load_user_defense_zones(discord_id: str, used_type: str = "defense") -> dict:
    """Reconstruit le dictionnaire de zones (North, South, Back, Fleet) depuis active_round_units."""
    zones = {"North": [], "South": [], "Back": [], "Fleet": []}
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT zone, slot_index, base_id
            FROM active_round_units
            WHERE discord_id = ? AND used_type = ?
            ORDER BY zone, slot_index
            """,
            (discord_id, used_type)
        )
        rows = await cursor.fetchall()
        
    slots_map = {}
    for r in rows:
        key = (r["zone"], r["slot_index"])
        if key not in slots_map:
            slots_map[key] = []
        slots_map[key].append(r["base_id"])
        
    for (z, s_idx), units in slots_map.items():
        if z in zones:
            leader = units[0] if units else None
            members = units[1:] if len(units) > 1 else []
            zones[z].append({
                "leader_id": leader,
                "members_ids": members,
                "slot_index": s_idx
            })
    return zones
