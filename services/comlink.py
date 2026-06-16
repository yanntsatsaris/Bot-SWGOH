"""
services/comlink.py — Client HTTP vers SWGOH Comlink (Protocoles Stricts et Optimisés)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
import aiohttp
from config import COMLINK_URL

log = logging.getLogger(__name__)
_TIMEOUT = aiohttp.ClientTimeout(total=45)

async def _post_raw(endpoint: str, payload: dict, top_level_params: dict = None) -> dict:
    """Effectue un appel POST brut vers Comlink avec le wrapper 'payload'."""
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
    """Récupère la liste brute des unités."""
    # 1. Metadata
    meta = await _post_raw("metadata", {})
    version = meta.get("latestGamedataVersion")
    if not version:
        raise ValueError("Version du jeu introuvable dans /metadata")

    # 2. Data
    payload = {
        "version": version,
        "includePveUnits": True,
        "requestSegment": 0
    }
    data = await _post_raw("data", payload, top_level_params={"enums": False})
    return data.get("units", [])

async def get_localization() -> str:
    """Récupère les textes de localisation."""
    # Note : Le message d'erreur indique que localization ne supporte PAS 'version'
    # et demande un ID de plus de 22 caractères.

    # On cherche l'ID réel dans les metadata
    meta = await _post_raw("metadata", {})

    # On cherche un ID qui ressemble à un bundle (longue chaîne)
    loc_id = "Loc_ENG_TXT" # Valeur par défaut

    # Comlink renvoie souvent une liste de bundles dans 'localization' ou 'strings'
    for loc_item in meta.get("localization", []):
        if loc_item.get("id", "").startswith("Loc_ENG"):
            loc_id = loc_item["id"]
            break

    # Payload STRICT : uniquement l'ID
    try:
        data = await _post_raw("localization", {"id": loc_id})
        return data.get("localizationBundle", "")
    except Exception as e:
        log.warning("Échec récupération localization avec ID %s : %s", loc_id, e)
        # On tente un dernier recours sans ID si possible ou avec le défaut court
        return ""

# ---------------------------------------------------------------------------
# Roster Joueur
# ---------------------------------------------------------------------------

async def get_player_roster(ally_code: str) -> list[dict]:
    """Récupère le roster optimisé d'un joueur."""
    clean = str(ally_code).replace("-", "")
    # Payload STRICT : uniquement allyCode
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
