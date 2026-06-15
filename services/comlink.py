"""
services/comlink.py — Client HTTP asynchrone vers SWGOH Comlink (auto-hébergé)
"""
import logging
import aiohttp
from config import COMLINK_URL

log = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=30)

async def _post(endpoint: str, payload: dict) -> dict:
    url = f"{COMLINK_URL}/{endpoint.lstrip('/')}"
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(url, json={"payload": payload}) as resp:
            if resp.status == 404:
                raise ValueError(f"Endpoint introuvable : {endpoint}")
            resp.raise_for_status()
            return await resp.json()

async def get_player(ally_code: str) -> dict:
    clean = ally_code.replace("-", "")
    data = await _post("player", {"allyCode": clean})
    return data

async def get_player_arena(ally_code: str) -> dict:
    clean = ally_code.replace("-", "")
    data = await _post("playerArena", {"allyCode": clean})
    return data

async def get_guild(guild_id: str) -> dict:
    data = await _post("guild", {"guildId": guild_id, "includeRecentGuildActivityInfo": True})
    return data

async def get_player_roster(ally_code: str) -> list[dict]:
    data = await get_player(ally_code)
    roster = []
    for unit in data.get("rosterUnit", []):
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        if not base_id: continue
        roster.append({
            "base_id":   base_id,
            "rarity":    unit.get("currentRarity", 0),
            "level":     unit.get("currentLevel", 0),
            "gear_tier": unit.get("currentTier", 0),
            "relic_tier": unit.get("relic", {}).get("currentTier", 0),
        })
    return roster

async def get_metadata() -> dict:
    url = f"{COMLINK_URL}/version"
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.get(url) as resp:
            if resp.status == 404: return {"status": "ok"}
            resp.raise_for_status()
            return await resp.json()

async def get_player_gac_history(ally_code: str) -> dict:
    """Récupère l'historique GAC via /playerGac ou /player en fallback."""
    clean = ally_code.replace("-", "")
    try:
        return await _post("playerGac", {"allyCode": clean})
    except Exception:
        return await get_player(clean)
