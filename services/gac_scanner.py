"""
services/gac_scanner.py
Scan complet des brackets GAC (toutes ligues, toutes divisions).
"""
import asyncio
import logging
from database.db import get_db
from services.comlink import comlink_client, _post_raw

log = logging.getLogger(__name__)

LEAGUES = {
    "CARBONITE": 20,
    "BRONZIUM":  40,
    "CHROMIUM":  60,
    "AURODIUM":  80,
    "KYBER":     100,
}
DIVISIONS = {25: 1, 20: 2, 15: 3, 10: 4, 5: 5}

# ─── PHASE 1 : Trouver le GAC actif ────────────────────────────────────────

async def get_active_gac_event() -> dict | None:
    """Retourne l'eventInstanceId du GAC en cours, ou None si aucun."""
    try:
        data = await comlink_client.get_events()
    except Exception as e:
        log.warning("Impossible d'utiliser get_events du wrapper, fallback _post_raw: %s", e)
        data = await _post_raw("getEvents", {})
        
    for event in data.get("gameEvent", []):
        eid = event.get("id", "")
        if "CHAMPIONSHIPS" in eid and "GRAND_ARENA" in eid:
            for instance in event.get("instance", []):
                iid = instance.get("id", "")
                if iid:
                    return {
                        "event_id":          eid,
                        "instance_id":       iid,
                        "event_instance_id": f"{eid}:{iid}",
                        "season_id":         eid,
                    }
    return None

# ─── PHASE 2 : Scanner tous les brackets d'une ligue ───────────────────────

async def scan_brackets_for_league(
    event_instance_id: str,
    league_name: str,
) -> list[dict]:
    """
    Énumère tous les brackets d'une ligue.
    Retourne une liste de dicts {player_id, ally_code, name, league, division, skill_rating}.
    """
    players = []
    bracket_num = 0

    while True:
        group_id = f"{event_instance_id}:{league_name}:{bracket_num}"
        try:
            # Type 4 = Event Leaderboard
            data = await _post_raw("getLeaderboard", {
                "leaderboardType": 4,
                "eventInstanceId": event_instance_id,
                "groupId":         group_id,
            })
            entries = data.get("player") or data.get("leaderboardEntry") or []
            if not entries:
                break

            for p in entries:
                players.append({
                    "player_id":    p.get("playerId") or p.get("id"),
                    "ally_code":    p.get("allyCode"),
                    "name":         p.get("name"),
                    "league":       LEAGUES.get(league_name, 0),
                    "division":     p.get("divisionId", 25),
                    "skill_rating": p.get("score") or p.get("skillRating", 0),
                })

            bracket_num += 1
            await asyncio.sleep(0.1)

        except Exception as e:
            log.debug(f"Fin brackets {league_name} à #{bracket_num}: {e}")
            break

    log.info(f"[{league_name}] {len(players)} joueurs dans {bracket_num} brackets")
    return players

# ─── PHASE 3 : Récupérer et stocker les rosters ────────────────────────────

async def fetch_and_store_roster(
    player_info: dict,
    season_id: str,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Récupère le roster d'un joueur et le stocke en BDD."""
    async with semaphore:
        try:
            ally_code = player_info.get("ally_code")
            player_id = player_info.get("player_id")
            
            if ally_code:
                profile = await comlink_client.get_player(allycode=str(ally_code).replace("-", ""))
            elif player_id:
                profile = await comlink_client.get_player(player_id=player_id)
            else:
                return False

            if not profile:
                return False

            roster = profile.get("rosterUnit", [])

            async with get_db() as db:
                cursor = await db.execute("""
                    INSERT OR IGNORE INTO gac_roster_snapshots
                        (player_id, ally_code, player_name, guild_id,
                         league, division, skill_rating, season_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    player_info["player_id"],
                    player_info.get("ally_code"),
                    profile.get("name"),
                    profile.get("guildId"),
                    player_info.get("league", 0),
                    player_info.get("division", 25),
                    player_info.get("skill_rating", 0),
                    season_id,
                ))
                snapshot_id = cursor.lastrowid

                if snapshot_id:
                    for unit in roster:
                        def_id  = unit.get("definitionId", "")
                        unit_id = def_id.split(":")[0] if ":" in def_id else def_id
                        raw_rel = (unit.get("relic") or {}).get("currentTier", 0)
                        relic   = max(0, raw_rel - 2) if raw_rel >= 2 else 0

                        await db.execute("""
                            INSERT INTO gac_roster_units
                                (snapshot_id, unit_id, relic_tier, gear_tier,
                                 stars, combat_type)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            snapshot_id,
                            unit_id,
                            relic,
                            unit.get("currentTier", 0),
                            unit.get("currentRarity", 7),
                            unit.get("combatType", 1),
                        ))

                await db.commit()
            return True

        except Exception as e:
            log.warning(f"Erreur roster {player_info.get('player_id')}: {e}")
            return False
        finally:
            await asyncio.sleep(0.033)

# ─── SCAN PRINCIPAL ─────────────────────────────────────────────────────────

async def run_full_gac_scan(
    concurrency: int = 30,
    leagues: list[str] | None = None,
) -> dict:
    """
    Lance le scan complet de tous les brackets GAC.
    """
    import time
    start = time.time()

    gac = await get_active_gac_event()
    if not gac:
        log.error("Aucun GAC actif ! Le scan bracket ne peut pas démarrer.")
        return {"error": "Aucun GAC actif"}

    event_instance_id = gac["event_instance_id"]
    season_id         = gac["season_id"]
    log.info(f"GAC actif : {season_id}")

    target_leagues = leagues or list(LEAGUES.keys())
    all_players: list[dict] = []
    seen_ids: set[str] = set()

    for league in target_leagues:
        players = await scan_brackets_for_league(event_instance_id, league)
        for p in players:
            pid = p.get("player_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                all_players.append(p)

    log.info(f"Phase 1 terminée : {len(all_players)} joueurs uniques")

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        fetch_and_store_roster(p, season_id, semaphore)
        for p in all_players
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    success = sum(1 for r in results if r is True)
    errors  = len(results) - success
    duration = round(time.time() - start)

    log.info(f"Scan terminé : {success}/{len(all_players)} OK en {duration}s")
    return {
        "season_id":     season_id,
        "total_players": len(all_players),
        "success":       success,
        "errors":        errors,
        "duration_sec":  duration,
    }

# ─── SCAN TOP 50 (toujours disponible) ─────────────────────────────────────

async def run_top50_scan() -> dict:
    import time
    start = time.time()

    all_players = []
    seen_ids: set[str] = set()

    for league_val in LEAGUES.values():
        for div_val in DIVISIONS.keys():
            try:
                data = await _post_raw("getLeaderboard", {
                    "leaderboardType": 6,
                    "league":          league_val,
                    "division":        div_val,
                })
                entries = data.get("leaderboardEntry") or data.get("player") or []
                if not entries and "leaderboard" in data:
                    for lb in data["leaderboard"]:
                        entries.extend(lb.get("player") or lb.get("leaderboardEntry") or [])

                for entry in entries:
                    pid = entry.get("playerId") or entry.get("id")
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        all_players.append({
                            "player_id":    pid,
                            "ally_code":    entry.get("allyCode"),
                            "name":         entry.get("name"),
                            "league":       league_val,
                            "division":     div_val,
                            "skill_rating": entry.get("score", 0),
                        })
                await asyncio.sleep(0.1)
            except Exception as e:
                log.warning(f"Erreur Top50 {league_val}/{div_val}: {e}")

    log.info(f"Top50 scan : {len(all_players)} joueurs uniques")

    semaphore = asyncio.Semaphore(20)
    results = await asyncio.gather(
        *[fetch_and_store_roster(p, "TOP50_DAILY", semaphore) for p in all_players],
        return_exceptions=True
    )

    return {
        "total_players": len(all_players),
        "success":       sum(1 for r in results if r is True),
        "duration_sec":  round(time.time() - start),
    }
