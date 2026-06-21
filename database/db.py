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
