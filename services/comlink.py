"""
services/comlink.py — Client HTTP vers SWGOH Comlink (Protocoles Stricts et Optimisés)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
import aiohttp
import json
from config import COMLINK_URL

log = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=45)

async def _post_raw(endpoint: str, payload: dict, top_level_params: dict = None) -> dict:
    url = f"{COMLINK_URL}/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    body = {"payload": payload}
    if top_level_params: body.update(top_level_params)

    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(url, json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                log.error("Comlink Error %d sur %s: %s", resp.status, endpoint, text)
                resp.raise_for_status()
            return await resp.json()

async def get_game_data() -> list[dict]:
    meta = await _post_raw("metadata", {})
    version = meta.get("latestGamedataVersion")
    if not version: raise ValueError("Version du jeu introuvable")

    payload = {"version": version, "includePveUnits": True, "requestSegment": 0}
    data = await _post_raw("data", payload, top_level_params={"enums": False})
    return data.get("units", [])

def _find_loc_id(obj, min_len=20):
    """Recherche récursive exhaustive pour trouver un ID de localisation valide."""
    if isinstance(obj, str):
        # On cherche un ID qui contient Loc, json ou ENG
        if len(obj) >= min_len and ("Loc_" in obj or ".json" in obj or "ENG" in obj):
            return obj
    elif isinstance(obj, dict):
        # Priorité aux clés 'id' ou 'bundle'
        for k in ["id", "bundle", "localizationId"]:
            if k in obj and isinstance(obj[k], str) and len(obj[k]) >= min_len:
                return obj[k]
        for v in obj.values():
            res = _find_loc_id(v, min_len)
            if res: return res
    elif isinstance(obj, list):
        for v in obj:
            res = _find_loc_id(v, min_len)
            if res: return res
    return None

async def get_localization() -> str:
    meta = await _post_raw("metadata", {})

    # Tentative 1 : Recherche récursive
    loc_id = _find_loc_id(meta)

    # Tentative 2 : Patterns standards si la récursion échoue
    if not loc_id:
        for key in ["localization", "strings", "localizationBundle"]:
            items = meta.get(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        curr = item.get("id", "")
                        if len(curr) >= 15: # On baisse la garde sur la longueur
                            loc_id = curr
                            break
            elif isinstance(items, dict):
                loc_id = items.get("id")
            if loc_id: break

    if not loc_id:
        log.warning("Aucun ID de localisation trouvé. Clés meta : %s", list(meta.keys()))
        return ""

    try:
        data = await _post_raw("localization", {"id": loc_id})
        return data.get("localizationBundle", "")
    except Exception as e:
        log.warning("Erreur localization avec ID %s : %s", loc_id, e)
        return ""

async def get_player_roster(ally_code: str) -> list[dict]:
    clean = str(ally_code).replace("-", "")
    data = await _post_raw("player", {"allyCode": clean})
    raw_roster = data.get("rosterUnit", [])

    roster = []
    for unit in raw_roster:
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        roster.append({
            "base_id":    base_id,
            "rarity":     unit.get("currentRarity", 0),
            "level":      unit.get("currentLevel", 0),
            "gear_tier":  unit.get("currentTier", 0),
            "relic_tier": (unit.get("relic") or {}).get("currentTier", 0),
        })
    return roster
