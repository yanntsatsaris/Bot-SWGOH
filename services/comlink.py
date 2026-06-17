"""
services/comlink.py — Client HTTP vers SWGOH Comlink (Protocoles Stricts et Optimisés)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
import aiohttp
import json
import base64
import zipfile
import io
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

def _decode_bundle(bundle: str) -> str:
    if not bundle:
        return ""
    
    # Si c'est déjà du texte brut (non base64)
    if "UNIT_" in bundle and "_NAME" in bundle:
        return bundle
        
    try:
        # Décodage base64
        decoded = base64.b64decode(bundle)
        
        # Tentative d'ouverture comme un ZIP
        try:
            with zipfile.ZipFile(io.BytesIO(decoded)) as z:
                for name in z.namelist():
                    return z.read(name).decode("utf-8")
        except zipfile.BadZipFile:
            # Texte brut encodé en base64
            return decoded.decode("utf-8")
    except Exception as e:
        log.warning("Erreur lors du décodage du bundle de localisation : %s", e)
        
    return bundle

async def get_localization() -> str:
    meta = await _post_raw("metadata", {})

    # 1. Recherche d'abord d'un fichier de localisation spécifique dans les métadonnées (ex: Loc_FRE_FR.json)
    for locale in ["FRE_FR", "ENG_US"]:
        loc_id = _find_loc_id(meta, locale)
        if loc_id:
            try:
                log.info("Tentative de récupération de la locale %s avec ID : %s", locale, loc_id)
                # Note: On n'envoie pas le paramètre 'locale' dans le payload car Comlink refuse les propriétés additionnelles
                data = await _post_raw("localization", {"id": loc_id})
                bundle = data.get("localizationBundle", "")
                if bundle:
                    log.info("✓ Localisation %s récupérée avec succès.", locale)
                    return _decode_bundle(bundle)
            except Exception as e:
                log.warning("Échec de récupération de la locale %s (ID: %s) : %s", locale, loc_id, e)

    # 2. Extraction directe via latestLocalizationBundleVersion (version globale)
    loc_id = meta.get("latestLocalizationBundleVersion") or meta.get("latestLocalizationRevision")
    if loc_id:
        try:
            log.info("Tentative de récupération via la version de bundle globale : %s", loc_id)
            data = await _post_raw("localization", {"id": loc_id})
            bundle = data.get("localizationBundle", "")
            if bundle:
                log.info("✓ Localisation par version globale récupérée avec succès.")
                return _decode_bundle(bundle)
        except Exception as e:
            log.warning("Échec de récupération de la version globale %s : %s", loc_id, e)

    # 3. Dernier recours : recherche récursive générique
    loc_id = _find_loc_id(meta)
    if loc_id:
        try:
            log.info("Tentative finale de récupération avec l'ID générique : %s", loc_id)
            data = await _post_raw("localization", {"id": loc_id})
            bundle = data.get("localizationBundle", "")
            return _decode_bundle(bundle)
        except Exception as e:
            log.warning("Erreur localization finale avec ID %s : %s", loc_id, e)

    log.warning("Aucun ID de localisation fonctionnel trouvé.")
    return ""

async def get_player(ally_code: str) -> dict:
    """
    Retourne le profil brut complet d'un joueur depuis Comlink.
    Inclut : name, allyCode, rosterUnit (liste brute), etc.
    L'API Comlink attend allyCode comme entier (pas une chaîne).
    """
    clean = int(str(ally_code).replace("-", ""))
    return await _post_raw("player", {"allyCode": clean})


async def get_player_roster(ally_code: str) -> list[dict]:
    clean = int(str(ally_code).replace("-", ""))
    data = await _post_raw("player", {"allyCode": clean})
    raw_roster = data.get("rosterUnit", [])

    roster = []
    for unit in raw_roster:
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        # L'API Comlink encode le relic tier avec un décalage de +2
        # (currentTier 1 = pas de relic, 3 = R1, 9 = R7)
        # On soustrait 2 pour obtenir le tier réel (0 = pas de relic, 1 = R1...)
        raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
        relic_tier = max(0, raw_relic - 2) if raw_relic >= 2 else 0
        roster.append({
            "base_id":    base_id,
            "rarity":     unit.get("currentRarity", 0),
            "level":      unit.get("currentLevel", 0),
            "gear_tier":  unit.get("currentTier", 0),
            "relic_tier": relic_tier,
        })
    return roster
