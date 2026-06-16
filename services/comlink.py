"""
services/comlink.py — Client HTTP vers SWGOH Comlink (Aligné sur Script Shell)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
import aiohttp
from config import COMLINK_URL

log = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=45)

async def _post_raw(endpoint: str, payload: dict, top_level_params: dict = None) -> dict:
    """
    Effectue un appel POST avec wrapper 'payload' et paramètres optionnels au top-level (ex: enums).
    """
    url = f"{COMLINK_URL}/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}

    body = {"payload": payload}
    if top_level_params:
        body.update(top_level_params)

    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.post(url, json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                log.error("Comlink Error %d sur %s: %s", resp.status, endpoint, text)
                resp.raise_for_status()
            return await resp.json()

# ---------------------------------------------------------------------------
# PROTOCOLE : Référentiel Jeu (Metadata -> Data)
# ---------------------------------------------------------------------------

async def get_game_data() -> list[dict]:
    """
    Récupère la liste brute des unités selon la logique validée par ton script shell.
    """
    # 1. Récupérer la version
    meta = await _post_raw("metadata", {})
    version = meta.get("latestGamedataVersion")
    if not version:
        raise ValueError("Version du jeu introuvable dans /metadata")

    # 2. Requêter les données (Aligné sur ton curl)
    payload = {
        "version": version,
        "includePveUnits": True, # On met True car tu filtres ensuite avec jq
        "requestSegment": 0
    }
    # Ajout du paramètre "enums": false au top-level
    data = await _post_raw("data", payload, top_level_params={"enums": False})

    # Ton script jq cherche dans .units[]
    return data.get("units", [])

async def get_localization() -> str:
    """Récupère les textes de localisation."""
    meta = await _post_raw("metadata", {})
    payload = {"id": "Loc_ENG_TXT", "version": meta.get("latestGamedataVersion")}
    data = await _post_raw("localization", payload)
    return data.get("localizationBundle", "")

# ---------------------------------------------------------------------------
# Roster Joueur
# ---------------------------------------------------------------------------

async def get_player_roster(ally_code: str) -> list[dict]:
    """Récupère le roster optimisé."""
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
