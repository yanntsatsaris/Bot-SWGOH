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
        # Pour l'instant, on n'a pas le season_id ou le nom de l'adversaire extrait,
        # donc on met des valeurs par défaut qu'on pourra raffiner plus tard.
        season_id = "UNKNOWN"
        opponent_name = "UNKNOWN"
        round_number = 1 # Sera raffiné plus tard par l'URL
        
        # 2. Insertion du Round
        cursor = await db.execute(
            """
            INSERT INTO gac_rounds (season_id, round_number, player_code, opponent_name)
            VALUES (?, ?, ?, ?)
            """,
            (season_id, round_number, ally_code, opponent_name)
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
        log.info(f"✅ {len(parsed_data['matches'])} matchs sauvegardés en BDD pour {ally_code} (Round ID: {round_id})")
