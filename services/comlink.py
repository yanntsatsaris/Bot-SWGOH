"""
services/comlink.py — Client HTTP vers SWGOH Comlink utilisant le wrapper officiel (swgoh-comlink)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
import asyncio
import base64
import zipfile
import io
import json

from swgoh_comlink import SwgohComlinkAsync
from config import COMLINK_URL

log = logging.getLogger(__name__)

# Initialisation du client officiel
comlink_client = SwgohComlinkAsync(url=COMLINK_URL)

async def _post_raw(endpoint: str, payload: dict, top_level_params: dict = None) -> dict:
    """
    Conserve une méthode _post_raw pour la compatibilité avec les requêtes spécifiques
    qui ne seraient pas exposées nativement par le wrapper (comme les leaderboards complexes).
    """
    import aiohttp
    url = f"{COMLINK_URL}/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    body = {"payload": payload}
    if top_level_params:
        body.update(top_level_params)

    timeout = aiohttp.ClientTimeout(total=45)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                log.error("Comlink Error %d sur %s: %s", resp.status, endpoint, text)
                raise aiohttp.ClientResponseError(
                    resp.request_info,
                    resp.history,
                    status=resp.status,
                    message=f"{resp.reason} — {text[:300]}",
                    headers=resp.headers,
                )
            return await resp.json()

async def get_game_data() -> list[dict]:
    # Utilisation du wrapper si possible, sinon on garde la méthode custom
    try:
        data = await comlink_client.get_game_data(version="", include_pve_units=True, request_segment=0)
        return data.get("units", [])
    except Exception as e:
        log.warning("get_game_data via wrapper échoué, fallback sur _post_raw: %s", e)
        meta = await _post_raw("metadata", {})
        version = meta.get("latestGamedataVersion")
        if not version: raise ValueError("Version du jeu introuvable")

        payload = {"version": version, "includePveUnits": True, "requestSegment": 0}
        data = await _post_raw("data", payload, top_level_params={"enums": False})
        return data.get("units", [])

def _decode_bundle(bundle: str) -> str:
    if not bundle:
        return ""
    if "UNIT_" in bundle and "_NAME" in bundle:
        return bundle
    try:
        decoded = base64.b64decode(bundle)
        try:
            with zipfile.ZipFile(io.BytesIO(decoded)) as z:
                for name in z.namelist():
                    return z.read(name).decode("utf-8")
        except zipfile.BadZipFile:
            return decoded.decode("utf-8")
    except Exception as e:
        log.warning("Erreur lors du décodage du bundle de localisation : %s", e)
    return bundle

async def get_localization() -> str:
    payload_meta = {
        "clientSpecs": {
            "locale": "FRE_FR",
            "platform": "Android"
        }
    }
    meta = await _post_raw("metadata", payload_meta)
    loc_id = meta.get("latestLocalizationBundleVersion") or meta.get("latestLocalizationRevision")
    if loc_id:
        try:
            log.info("Tentative de récupération via la version de bundle FR : %s", loc_id)
            data = await _post_raw("localization", {"id": loc_id, "unzip": True})
            bundle = data.get("localizationBundle", "")
            if bundle:
                log.info("✓ Localisation Française récupérée avec succès.")
                return _decode_bundle(bundle)
        except Exception as e:
            log.warning("Échec de récupération de la version FR %s : %s", loc_id, e)

    log.warning("Aucun bundle de localisation valide trouvé.")
    return ""

async def get_player(ally_code: str | None = None, player_id: str | None = None) -> dict:
    """
    Retourne le profil brut complet d'un joueur depuis Comlink via le wrapper.
    """
    if ally_code:
        clean_code = str(ally_code).replace("-", "").strip()
        # On cast en int si possible, car certains serveurs Comlink rejettent les strings avec HTTP 400
        ally_int = int(clean_code) if clean_code.isdigit() else clean_code
        return await comlink_client.get_player(allycode=ally_int)
    elif player_id:
        return await comlink_client.get_player(player_id=player_id)
    else:
        raise ValueError("ally_code ou player_id doit être fourni")

async def get_player_roster(ally_code: str) -> list[dict]:
    clean = str(ally_code).replace("-", "").strip()
    ally_int = int(clean) if clean.isdigit() else clean
    data = await comlink_client.get_player(allycode=ally_int)
    raw_roster = data.get("rosterUnit", [])

    roster = []
    for unit in raw_roster:
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
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

async def check_health() -> dict:
    return await comlink_client.get_game_metadata()

async def get_player_arena(ally_code: str) -> dict:
    clean = str(ally_code).replace("-", "").strip()
    ally_int = int(clean) if clean.isdigit() else clean
    return await comlink_client.get_player_arena(allycode=ally_int)

async def scan_all_leaderboards(leagues: list[int] | None = None, divisions: list[int] | None = None) -> list[dict]:
    leagues = leagues or [20, 40, 60, 80, 100]
    divisions = divisions or [5, 10, 15, 20, 25]
    
    all_players = []
    for league in leagues:
        for division in divisions:
            try:
                data = await _post_raw("getLeaderboard", {
                    "leaderboardType": 6,
                    "league": league,
                    "division": division,
                })
                entries = data.get("player") or data.get("leaderboardEntry") or []
                if not entries and "leaderboard" in data:
                    for lb in data["leaderboard"]:
                        entries.extend(lb.get("player") or lb.get("leaderboardEntry") or [])
                
                for entry in entries:
                    all_players.append(entry)
                    
                log.info(f"L{league} D{division} : {len(entries)} joueurs récupérés")
                await asyncio.sleep(0.1)
            except Exception as e:
                log.warning("Erreur scan_all_leaderboards (L%s D%s): %s", league, division, e)
                continue
    return all_players
