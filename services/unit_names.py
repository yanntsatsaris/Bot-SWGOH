"""
services/unit_names.py — Gestion des noms des unités
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

UNITS_DATA_FILE = Path("database/all_units.json")

# Mapping statique de secours (GAC courant)
STATIC_NAMES: dict[str, str] = {
    "SITHPALPATINE": "Sith Eternal Emperor",
    "DARTHVADER": "Darth Vader",
    "JEDIMASTERKENOBI": "Jedi Master Kenobi",
}

_cache: dict[str, str] = {}

def _load_units_data():
    global _cache
    if UNITS_DATA_FILE.exists():
        try:
            with open(UNITS_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _cache = {u["base_id"].upper(): u["name"] for u in data}
        except Exception as e:
            log.error("Erreur chargement all_units.json: %s", e)

async def build_name_cache() -> None:
    """Charge le cache depuis le fichier JSON généré par sync_all_units.py, ou la BDD."""
    global _cache
    try:
        from database.db import get_db
        async with get_db() as db:
            cursor = await db.execute("SELECT base_id, name FROM game_characters")
            rows = await cursor.fetchall()
            if rows:
                _cache = {row["base_id"].upper(): row["name"] for row in rows}
    except Exception as e:
        log.error("Erreur chargement cache noms depuis DB: %s", e)

    if not _cache:
        _load_units_data()
    if not _cache:
        _cache.update(STATIC_NAMES)

def get_name(base_id: str) -> str:
    if not _cache:
        _load_units_data()

    bid_upper = base_id.upper()
    return _cache.get(bid_upper, STATIC_NAMES.get(bid_upper, base_id.replace("_", " ").title()))
