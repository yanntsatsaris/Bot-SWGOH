"""
services/gac_lock_service.py — Service de Verrouillage (Lock) Automatique des Rosters & Datacrons GAC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gère le snapshot figé des 8 joueurs d'une poule de GAC au moment du Lock.
"""
import logging
import asyncio
import re

from database.db import (
    save_locked_roster,
    get_locked_roster,
    save_bracket_opponents,
    get_bracket_opponents,
    get_all_registered_players,
)
from services.comlink import get_player

log = logging.getLogger(__name__)


def _extract_season_id_from_profile(profile: dict) -> str:
    """Extrait le season_id actif depuis le profil Comlink d'un joueur."""
    season_status = profile.get("seasonStatus", [])
    if season_status:
        last_s = season_status[-1]
        sid = last_s.get("seasonId") or last_s.get("eventInstanceId")
        if sid:
            return str(sid)
    return "CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_CURRENT"


async def lock_single_player(ally_code: str, season_id: str = None) -> dict | None:
    """
    Télécharge et verrouille le profil d'un joueur (roster + datacrons) pour la saison GAC.
    """
    clean_code = str(ally_code).replace("-", "").strip()
    try:
        profile = await get_player(clean_code)
        if not profile:
            log.warning(f"[GacLock] Impossible de récupérer le profil Comlink pour {clean_code}")
            return None

        p_name = profile.get("name", clean_code)
        actual_season = season_id or _extract_season_id_from_profile(profile)

        await save_locked_roster(
            ally_code=clean_code,
            player_name=p_name,
            season_id=actual_season,
            event_id="GAC_LOCK",
            profile_dict=profile
        )
        log.info(f"[GacLock] 🔒 Snapshot verrouillé enregistré pour {p_name} ({clean_code}) - Saison {actual_season}")
        return profile
    except Exception as e:
        log.warning(f"[GacLock] Erreur lock_single_player({clean_code}): {e}")
        return None



def parse_bracket_html(html_content: str, owner_ally_code: str) -> list[str]:
    """
    Extrait les ally codes des 7 adversaires depuis le HTML de la page /gac-bracket/ de swgoh.gg.
    """
    clean_owner = str(owner_ally_code).replace("-", "").strip()
    opponents = []

    # 1. Matcher les divs d'ally codes exactes : <div class="compare-players__nameplate-ally-code">739-671-686</div>
    codes = re.findall(r'class="compare-players__nameplate-ally-code">\s*([\d-]+)\s*<', html_content)
    for c in codes:
        clean = c.replace("-", "").strip()
        if len(clean) == 9 and clean != clean_owner and clean not in opponents:
            opponents.append(clean)

    # 2. Fallback regex : liens de profil /p/123456789/
    if len(opponents) < 7:
        links = re.findall(r'/p/(\d{9})/', html_content)
        for c in links:
            if c != clean_owner and c not in opponents:
                opponents.append(c)

    return opponents[:7]


async def fetch_bracket_from_swgoh_gg(ally_code: str) -> list[str]:
    """
    Tente de récupérer la page de bracket swgoh.gg et d'en extraire les 7 adversaires.
    """
    clean_code = str(ally_code).replace("-", "").strip()
    target_url = f"https://swgoh.gg/p/{clean_code}/gac-bracket/"
    
    # 1. Essai direct HTTP rapide avec User-Agent
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }) as client:
            resp = await client.get(target_url)
            if resp.status_code == 200:
                opps = parse_bracket_html(resp.text, clean_code)
                if opps:
                    log.info(f"[GacLock] 🎯 {len(opps)} adversaires extraits via HTTP pour {clean_code}")
                    return opps
    except Exception as e:
        log.debug(f"[GacLock] HTTP direct echoue pour bracket {clean_code}: {e}")

    # 2. Si protection Cloudflare, passage par le scraper SeleniumBase
    try:
        import sys
        import os
        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        worker_path = os.path.join(project_dir, "scripts", "sb_worker.py")
        temp_html = os.path.join(project_dir, "temp_bracket.html")

        process = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_path,
            target_url,
            temp_html,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_dir
        )
        await process.communicate()
        if os.path.exists(temp_html):
            content = open(temp_html, "r", encoding="utf-8", errors="ignore").read()
            try:
                os.remove(temp_html)
            except:
                pass
            opps = parse_bracket_html(content, clean_code)
            if opps:
                log.info(f"[GacLock] 🎯 {len(opps)} adversaires extraits via SB pour {clean_code}")
                return opps
    except Exception as e:
        log.warning(f"[GacLock] Erreur scraping bracket {clean_code}: {e}")

    return []


async def lock_player_and_bracket(owner_ally_code: str, opponent_codes: list[str] = None) -> dict:
    """
    Verrouille le profil du joueur enregistré ainsi que tous ses adversaires de poule GAC.
    """
    clean_owner = str(owner_ally_code).replace("-", "").strip()
    owner_profile = await lock_single_player(clean_owner)
    if not owner_profile:
        return {"success": False, "locked_count": 0, "opponents": []}

    season_id = _extract_season_id_from_profile(owner_profile)
    opponents_to_lock = []

    # 1. Si des codes d'adversaires sont fournis explicitement
    if opponent_codes:
        opponents_to_lock = [str(c).replace("-", "").strip() for c in opponent_codes if str(c).replace("-", "").strip() != clean_owner]

    # 2. Extraction automatique depuis le bracket swgoh.gg live
    if not opponents_to_lock:
        scraped_opps = await fetch_bracket_from_swgoh_gg(clean_owner)
        if scraped_opps:
            opponents_to_lock = scraped_opps

    # 3. Fallback : vérifier si on a déjà des adversaires enregistrés en BDD pour cette saison
    if not opponents_to_lock:
        existing_bracket = await get_bracket_opponents(clean_owner, season_id)
        if existing_bracket:
            opponents_to_lock = [r["opponent_code"] for r in existing_bracket]

    locked_opponents = []
    for opp_code in opponents_to_lock:
        opp_prof = await lock_single_player(opp_code, season_id=season_id)
        if opp_prof:
            opp_name = opp_prof.get("name", opp_code)
            locked_opponents.append({"ally_code": opp_code, "name": opp_name})
        await asyncio.sleep(0.2)

    if locked_opponents:
        await save_bracket_opponents(clean_owner, season_id, round_num=1, opponents=locked_opponents)

    total_locked = 1 + len(locked_opponents)
    log.info(f"[GacLock] ✅ Poule GAC verrouillée pour {clean_owner} : {total_locked} joueurs au total (Saison {season_id})")
    return {
        "success": True,
        "owner": clean_owner,
        "season_id": season_id,
        "locked_count": total_locked,
        "opponents": locked_opponents
    }


async def auto_lock_all_registered_players() -> dict:
    """
    Tâche automatique : parcourt tous les joueurs enregistrés sur le bot et verrouille leurs profils.
    """
    players = await get_all_registered_players()
    log.info(f"[GacAutoLock] 🚀 Démarrage du verrouillage automatique pour {len(players)} joueurs enregistrés...")
    
    results = {}
    for p in players:
        ac = p.get("ally_code")
        if not ac:
            continue
        res = await lock_player_and_bracket(ac)
        results[ac] = res
        await asyncio.sleep(0.5)

    log.info(f"[GacAutoLock] ✅ Verrouillage automatique terminé pour {len(results)} joueurs.")
    return results
