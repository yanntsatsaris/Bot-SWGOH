"""
services/comlink.py — Client HTTP vers SWGOH Comlink (Format POST + Payload)
"""
import logging
import aiohttp
from config import COMLINK_URL

log = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Cache pour la version du jeu
_version_cache = {
    "version": None,
    "last_check": 0
}

async def _get_game_version() -> str:
    """Récupère la latestGamedataVersion via /metadata."""
    if _version_cache["version"]:
        return _version_cache["version"]

    url = f"{COMLINK_URL}/metadata"
    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        # Comme tu l'as précisé : POST avec payload vide
        async with session.post(url, json={"payload": {}}, headers={"Content-Type": "application/json"}) as resp:
            if resp.status == 200:
                data = await resp.json()
                v = data.get("latestGamedataVersion", "")
                _version_cache["version"] = v
                return v
    return ""

async def _post(endpoint: str, payload_data: dict) -> dict:
    """Effectue un POST vers Comlink avec le wrapper 'payload' et la version."""
    version = await _get_game_version()

    # Injection de la version si non présente
    if version and "version" not in payload_data:
        payload_data["version"] = version

    full_payload = {"payload": payload_data}
    url = f"{COMLINK_URL}/{endpoint.lstrip('/')}"

    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(url, json=full_payload, headers={"Content-Type": "application/json"}) as resp:
            if resp.status == 404:
                raise ValueError(f"Endpoint introuvable : {endpoint}")
            resp.raise_for_status()
            return await resp.json()

async def get_player(ally_code: str) -> dict:
    clean = str(ally_code).replace("-", "")
    return await _post("player", {"allyCode": clean})

async def get_player_arena(ally_code: str) -> dict:
    clean = str(ally_code).replace("-", "")
    return await _post("playerArena", {"allyCode": clean})

async def get_guild(guild_id: str) -> dict:
    return await _post("guild", {"guildId": guild_id, "includeRecentGuildActivityInfo": True})

async def get_player_gac_history(ally_code: str) -> dict:
    clean = str(ally_code).replace("-", "")
    try:
        return await _post("playerGac", {"allyCode": clean})
    except:
        return await get_player(clean)

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
