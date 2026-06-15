"""
services/comlink.py — Client HTTP asynchrone vers SWGOH Comlink (auto-hébergé)

Endpoints principaux :
    POST /player          → données complètes d'un joueur
    POST /playerArena     → données d'arène + GAC
    POST /guild           → données d'une guilde
    GET  /metadata        → version du jeu / statut
"""
import logging

import aiohttp

from config import COMLINK_URL

log = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)


async def _post(endpoint: str, payload: dict) -> dict:
    """Effectue un POST vers Comlink et retourne le JSON."""
    url = f"{COMLINK_URL}/{endpoint.lstrip('/')}"
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(url, json={"payload": payload}) as resp:
            if resp.status == 404:
                raise ValueError(f"Endpoint introuvable : {endpoint}")
            resp.raise_for_status()
            return await resp.json()


async def get_player(ally_code: str) -> dict:
    """
    Récupère les données complètes d'un joueur.

    Args:
        ally_code: Code allié sans tirets (ex : '123456789').
    """
    clean = ally_code.replace("-", "")
    data = await _post("player", {"allyCode": clean})
    log.debug("Comlink /player reçu pour %s", ally_code)
    return data


async def get_player_arena(ally_code: str) -> dict:
    """
    Récupère les données d'arène et de GAC d'un joueur.

    Args:
        ally_code: Code allié sans tirets.
    """
    clean = ally_code.replace("-", "")
    data = await _post("playerArena", {"allyCode": clean})
    log.debug("Comlink /playerArena reçu pour %s", ally_code)
    return data


async def get_guild(guild_id: str) -> dict:
    """Récupère les données d'une guilde par son ID."""
    data = await _post("guild", {"guildId": guild_id, "includeRecentGuildActivityInfo": True})
    log.debug("Comlink /guild reçu pour %s", guild_id)
    return data


async def get_player_roster(ally_code: str) -> list[dict]:
    """
    Retourne le roster complet d'un joueur sous forme de liste normalisée.
    Chaque entrée contient : base_id, rarity, level, relic_tier, gear_tier.

    Args:
        ally_code: Code allié sans tirets.
    """
    clean = ally_code.replace("-", "")
    data  = await get_player(clean)

    roster = []
    for unit in data.get("rosterUnit", []):
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        if not base_id:
            continue
        roster.append({
            "base_id":   base_id,
            "rarity":    unit.get("currentRarity", 0),
            "level":     unit.get("currentLevel", 0),
            "gear_tier": unit.get("currentTier", 0),
            "relic_tier": unit.get("relic", {}).get("currentTier", 0),
        })
    return roster


async def get_metadata() -> dict:
    """Vérifie que Comlink est joignable via l'endpoint localization."""
    url = f"{COMLINK_URL}/version"
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.get(url) as resp:
            if resp.status == 404:
                # Pas d'endpoint /version sur certaines versions — fallback
                return {"status": "ok"}
            resp.raise_for_status()
            return await resp.json()
