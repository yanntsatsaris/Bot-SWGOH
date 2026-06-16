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

def _find_loc_id(obj, target_locale: str | None = None, min_len=20) -> str | None:
    """Recherche récursive exhaustive pour trouver un ID de localisation valide."""
    if isinstance(obj, str):
        if len(obj) >= min_len:
            # Suffixes de locale valides
            locales = [target_locale] if target_locale else [
                "ENG_US", "FRE_FR", "GER_DE", "SPA_ES", "ITA_IT", 
                "CHS_CN", "CHT_CN", "DAN_DK", "DUT_NL", "FIN_FI", 
                "JPN_JP", "KOR_KR", "NOR_NO", "POR_BR", "RUS_RU", 
                "SPA_MX", "SWE_SE"
            ]
            # On cherche un ID qui contient "Loc_" ou ".json" ET une locale valide
            if ("Loc_" in obj or ".json" in obj) and any(loc in obj for loc in locales):
                return obj
    elif isinstance(obj, dict):
        # Priorité aux clés 'id' ou 'bundle'
        for k in ["id", "bundle", "localizationId"]:
            if k in obj and isinstance(obj[k], str) and len(obj[k]) >= min_len:
                locales = [target_locale] if target_locale else ["ENG_US", "FRE_FR"]
                if any(loc in obj[k] for loc in locales):
                    return obj[k]
        for v in obj.values():
            res = _find_loc_id(v, target_locale, min_len)
            if res: return res
    elif isinstance(obj, list):
        for v in obj:
            res = _find_loc_id(v, target_locale, min_len)
            if res: return res
    return None

async def get_localization() -> str:
    meta = await _post_raw("metadata", {})

    # 1. Extraction directe via latestLocalizationBundleVersion (méthode officielle recommandée)
    loc_id = meta.get("latestLocalizationBundleVersion")
    if not loc_id:
        loc_id = meta.get("latestLocalizationRevision")

    # 2. Recherche ciblée dans les listes structurées de metadata
    if not loc_id:
        target_locales = ["FRE_FR", "ENG_US"]
        for key in ["localization", "strings", "localizationBundle"]:
            items = meta.get(key, [])
            if isinstance(items, list):
                # Chercher d'abord FRE_FR, puis ENG_US
                for target_loc in target_locales:
                    for item in items:
                        if isinstance(item, dict):
                            curr_locale = item.get("locale") or item.get("language")
                            curr_id = item.get("id", "")
                            if (curr_locale == target_loc) or (target_loc in curr_id):
                                loc_id = curr_id
                                break
                    if loc_id:
                        break
                if loc_id:
                    break
                
                # Fallback sur n'importe quel ID ayant un format valide dans la liste
                for item in items:
                    if isinstance(item, dict):
                        curr_id = item.get("id", "")
                        if curr_id and len(curr_id) >= 15:
                            loc_id = curr_id
                            break
                if loc_id:
                    break

    # 3. Recherche récursive ciblée si non trouvé dans les clés standard
    if not loc_id:
        for target_loc in ["FRE_FR", "ENG_US"]:
            loc_id = _find_loc_id(meta, target_loc)
            if loc_id:
                break

    # 4. Dernier recours : recherche récursive générique
    if not loc_id:
        loc_id = _find_loc_id(meta)

    if not loc_id:
        log.warning("Aucun ID de localisation trouvé. Clés meta : %s", list(meta.keys()))
        return ""

    # Tente d'abord de récupérer en français (FRE_FR) puis en anglais (ENG_US)
    for locale in ["FRE_FR", "ENG_US"]:
        try:
            log.info("Tentative de récupération de la locale %s (ID: %s)...", locale, loc_id)
            data = await _post_raw("localization", {"id": loc_id, "locale": locale})
            bundle = data.get("localizationBundle", "")
            if bundle:
                log.info("✓ Locale %s récupérée avec succès.", locale)
                return bundle
        except Exception as e:
            log.warning("Échec de récupération pour la locale %s : %s", locale, e)

    # Dernier recours sans spécifier de locale
    try:
        data = await _post_raw("localization", {"id": loc_id})
        return data.get("localizationBundle", "")
    except Exception as e:
        log.warning("Erreur localization finale avec ID %s : %s", loc_id, e)
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
