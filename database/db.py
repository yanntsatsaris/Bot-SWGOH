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
        # On ajoute format='5v5' pour respecter le schéma de la base de données déjà existante sur le serveur
        cursor = await db.execute(
            """
            INSERT INTO gac_rounds (season_id, round_number, player_code, opponent_name, format)
            VALUES (?, ?, ?, ?, '5v5')
            """,
            (season_id, round_number, real_ally_code, opponent_name)
        )
        round_id = cursor.lastrowid
        
        # 3. Insertion des matchs associés
        for match in parsed_data["matches"]:
            attacker_json = json.dumps(match.get("attacker_team", []))
            defender_json = json.dumps(match.get("defender_team", []))
            
            await db.execute(
                """
                INSERT INTO gac_matches 
                (round_id, is_attack, attacker_team, defender_team, banners, outcome)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (round_id, match["is_attack"], attacker_json, defender_json, match["banners"], match["outcome"])
            )
        
        await db.commit()
        log.info(f"✅ {len(parsed_data['matches'])} matchs sauvegardés en BDD pour {real_ally_code} (Round ID: {round_id})")
