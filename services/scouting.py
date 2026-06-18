"""
services/scouting.py — Moteur de Scouting Hybride pour la GAC
"""
import logging
from database.db import get_db
from services.comlink import get_player
from utils.gac_config import get_gac_quotas
from services.gac_meta import GAC_TEAMS, GAC_FLEETS

log = logging.getLogger(__name__)

LEAGUE_MAP = {
    1: "CARBONITE",
    2: "BRONZIUM",
    3: "CHROMIUM",
    4: "AURODIUM",
    5: "KYBER"
}

def _is_gac_ready(unit: dict) -> bool:
    return unit.get("relic_tier", 0) > 0 or unit.get("gear_tier", 0) >= 11

def _build_roster_index(raw_roster: list) -> dict:
    roster = {}
    for unit in raw_roster:
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
        relic_tier = max(0, raw_relic - 2) if raw_relic >= 2 else 0
        roster[base_id] = {
            "base_id": base_id,
            "gear_tier": unit.get("currentTier", 0),
            "relic_tier": relic_tier,
            "rarity": unit.get("currentRarity", 0),
        }
    return roster

def _predict_zones(enemy_index: dict, quotas: dict, fmt: str) -> dict:
    zones = {"North": [], "South": [], "Back": [], "Fleet": []}
    used_base_ids = set()
    
    # 1. PERSONNAGES
    available_teams = []
    for team_id, team_data in GAC_TEAMS.items():
        members = team_data["members"]
        expected_size = 3 if fmt == "3v3" else 5
        members = members[:expected_size]
        
        leader = enemy_index.get(team_id)
        if leader and _is_gac_ready(leader):
            ready_count = sum(1 for m in members if enemy_index.get(m) and _is_gac_ready(enemy_index[m]))
            if ready_count / len(members) >= 0.6:
                score = sum([enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0) for m in members if m in enemy_index])
                available_teams.append({
                    "leader_id": team_id,
                    "members": members,
                    "defense": team_data.get("defense", 5),
                    "score": score
                })
                
    # Trier par score défensif, puis puissance
    available_teams.sort(key=lambda x: (x["defense"], x["score"]), reverse=True)
    
    for zone in ["North", "South", "Back"]:
        q = quotas.get(zone, 0)
        for _ in range(q):
            placed = False
            for t in available_teams:
                if not any(m in used_base_ids for m in t["members"]):
                    zones[zone].append({
                        "leader_id": t["leader_id"],
                        "members_ids": t["members"],
                        "source": "predictive"
                    })
                    used_base_ids.update(t["members"])
                    placed = True
                    break
            if not placed:
                zones[zone].append({"leader_id": None, "members_ids": [], "source": "empty"})

    # 2. FLOTTES
    available_fleets = []
    for cap_id, team_data in GAC_FLEETS.items():
        if enemy_index.get(cap_id) and enemy_index[cap_id].get("rarity", 0) >= 5:
            score = enemy_index[cap_id].get("relic_tier", 0) * 10 + enemy_index[cap_id].get("gear_tier", 0)
            available_fleets.append({
                "leader_id": cap_id,
                "members": team_data["members"],
                "defense": team_data.get("defense", 5),
                "score": score
            })
            
    available_fleets.sort(key=lambda x: (x["defense"], x["score"]), reverse=True)
    
    fleet_quota = quotas.get("Fleet", 1)
    for _ in range(fleet_quota):
        placed = False
        for f in available_fleets:
            if f["leader_id"] not in used_base_ids:
                zones["Fleet"].append({
                    "leader_id": f["leader_id"],
                    "members_ids": f["members"],
                    "source": "predictive"
                })
                used_base_ids.add(f["leader_id"])
                placed = True
                break
        if not placed:
            zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty"})

    return zones

async def get_scout_data(enemy_ally_code: str, fmt: str, my_ally_code: str | None = None) -> dict:
    clean_code = str(enemy_ally_code).replace("-", "").strip()
    profile = await get_player(clean_code)
    
    if not profile:
        raise ValueError(f"Profil introuvable pour {clean_code}")

    enemy_name = profile.get("name", clean_code)
    
    league_name = "CARBONITE"
    season_status = profile.get("seasonStatus", [])
    if season_status:
        last_season = season_status[-1]
        league_val = last_season.get("league", "CARBONITE")
        if isinstance(league_val, str):
            league_name = league_val.split("_")[-1].upper()
        else:
            league_name = LEAGUE_MAP.get(league_val, "CARBONITE")
            
    if league_name not in ["CARBONITE", "BRONZIUM", "CHROMIUM", "AURODIUM", "KYBER"]:
        league_name = "CARBONITE"
        
    quotas = get_gac_quotas(league_name, fmt)
    enemy_index = _build_roster_index(profile.get("rosterUnit", []))
    
    enemy_zones = _predict_zones(enemy_index, quotas, fmt)
    
    result = {
        "enemy_name": enemy_name,
        "league": league_name,
        "format": fmt,
        "source": "Prédiction Offense/Défense",
        "zones": enemy_zones,
        "quotas": quotas
    }
    
    if my_ally_code:
        my_clean = str(my_ally_code).replace("-", "").strip()
        my_profile = await get_player(my_clean)
        if my_profile:
            my_index = _build_roster_index(my_profile.get("rosterUnit", []))
            my_zones = _predict_zones(my_index, quotas, fmt)
            result["my_zones"] = my_zones
            result["my_name"] = my_profile.get("name", my_clean)

    return result
