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

async def get_omicron_dict() -> dict:
    omicrons = {}
    try:
        async with get_db() as db:
            async with db.execute("SELECT skill_id, omicron_tier FROM game_omicrons") as cursor:
                async for row in cursor:
                    omicrons[row["skill_id"]] = row["omicron_tier"]
    except Exception as e:
        log.warning(f"Erreur chargement omicrons: {e}")
    return omicrons

def _is_gac_ready(unit: dict) -> bool:
    return unit.get("relic_tier", 0) > 0 or unit.get("gear_tier", 0) >= 11

def _build_roster_index(raw_roster: list, omicron_dict: dict) -> dict:
    roster = {}
    for unit in raw_roster:
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
        relic_tier = max(0, raw_relic - 2) if raw_relic >= 2 else 0
        
        has_omicron = False
        for sk in unit.get("skill", []):
            sid = sk.get("id")
            tier = sk.get("tier", 0)
            req_tier = omicron_dict.get(sid)
            if req_tier and tier >= req_tier:
                has_omicron = True
                break
                
        roster[base_id] = {
            "base_id": base_id,
            "gear_tier": unit.get("currentTier", 0),
            "relic_tier": relic_tier,
            "rarity": unit.get("currentRarity", 0),
            "has_omicron": has_omicron,
            "combat_type": unit.get("combatType", 1)
        }
    return roster

def _predict_zones(enemy_index: dict, quotas: dict, fmt: str) -> dict:
    zones = {"North": [], "South": [], "Back": [], "Fleet": []}
    used_base_ids = set()
    
    # 1. PERSONNAGES
    available_teams = []
    for team_id, team_data in GAC_TEAMS.items():
        if team_data.get("format") and team_data["format"] != fmt:
            continue
            
        leader_id = team_data.get("leader_id", team_id)
        if not leader_id:
            continue
            
        core = team_data.get("core", [])
        subs = team_data.get("subs", [])
        
        # Vérifier que le core est présent et ready (au moins 60% du core ou leader mandatory)
        if leader_id not in enemy_index or not _is_gac_ready(enemy_index[leader_id]):
            continue
            
        core_ready = [m for m in core if m in enemy_index and _is_gac_ready(enemy_index[m])]
        # On exige tout le core (c'est le principe du core)
        if len(core_ready) < len(core):
            continue
            
        req_omis = team_data.get("requires_omicron", [])
        missing_omi = False
        for req in req_omis:
            if req in enemy_index and not enemy_index[req].get("has_omicron"):
                missing_omi = True
                break
        if missing_omi:
            continue
            
        expected_size = 3 if fmt == "3v3" else 5
        min_size = team_data.get("min_size", expected_size)
        slots_left = expected_size - len(core_ready)
        
        # Récupérer les subs dispos et les trier par puissance
        ready_subs = [m for m in subs if m in enemy_index and _is_gac_ready(enemy_index[m])]
        ready_subs.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)
        
        # Prendre les meilleurs subs pour remplir l'équipe
        assembled_members = list(core_ready)
        assembled_members.extend(ready_subs[:slots_left])
        
        # RÈGLE D'OR STRATÉGIQUE : 
        # Si le joueur n'a pas assez de "core + subs" pour atteindre la taille 
        # minimale de l'équipe (par ex: 5 membres pour un 5v5), on NE LA FORME PAS.
        # Un joueur ne placera jamais une équipe avec un énorme trou en défense.
        if len(assembled_members) < min_size:
            continue
            
        # On accepte l'équipe telle quelle (même si incomplète), on la remplira à la fin
        score = sum([enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0) for m in assembled_members])
        
        def_score = team_data.get("defense", 5)
        off_score = team_data.get("offense", 5)
        if team_data.get("role") == "offense":
            def_score -= 100 # Pénalité extrême pour ne l'utiliser qu'en dernier recours
            
        available_teams.append({
            "leader_id": leader_id,
            "members": assembled_members,
            "defense": def_score,
            "offense": off_score,
            "score": score,
            "target_size": team_data.get("min_size", expected_size),
            "id": team_id
        })
                
    # Trier par "Biais Défensif" (defense - offense), puis par défense absolue, puis puissance
    available_teams.sort(key=lambda x: (x["defense"] - x["offense"], x["defense"], x["score"]), reverse=True)

    # Identification des personnages strictement réservés à l'attaque
    offense_only_chars = set()
    for t in available_teams:
        if t["defense"] <= 2:
            if t["leader_id"]:
                offense_only_chars.add(t["leader_id"])
            for c in t.get("members", []):
                team_data = GAC_TEAMS.get(t["id"], {})
                core_members = team_data.get("core", [])
                if c in core_members:
                    offense_only_chars.add(c)
    
    for zone in ["North", "South", "Back"]:
        q = quotas.get(zone, 0)
        for _ in range(q):
            placed = False
            for t in available_teams:
                # Interdiction de placer une équipe d'Attaque pure (Défense <= 2) en Défense
                if t["defense"] <= 2:
                    continue
                    
                # Vérifier que le leader et les membres sont dispos
                if t["leader_id"] not in used_base_ids and t["leader_id"] != "USED":
                    valid_members = [m for m in t["members"] if m not in used_base_ids]
                    
                    zones[zone].append({
                        "leader_id": t["leader_id"],
                        "members_ids": valid_members,
                        "source": "predictive",
                        "target_size": t["target_size"]
                    })
                    used_base_ids.update(valid_members)
                    t["leader_id"] = "USED" # On marque l'équipe comme consommée
                    placed = True
                    break
            if not placed:
                zones[zone].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": expected_size})

    # 1.5 BOUCHAGE DE TROUS (Hole-Filling) INTELLIGENT (Graphe de Synergie)
    leftovers = [
        m for m, data in enemy_index.items() 
        if m not in used_base_ids 
        and m not in offense_only_chars
        and _is_gac_ready(data) 
        and data.get("combat_type", 1) == 1
    ]
    # Trier par puissance de base
    leftovers.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)
    
    # Construire le graphe de synergie basé sur la méta connue
    synergy_graph = {}
    for team_id, team_data in GAC_TEAMS.items():
        all_members = [team_data["leader_id"]] + team_data.get("core", []) + team_data.get("subs", [])
        all_members = [m for m in all_members if m] # Filtrer les None
        for m1 in all_members:
            if m1 not in synergy_graph:
                synergy_graph[m1] = set()
            for m2 in all_members:
                if m1 != m2:
                    synergy_graph[m1].add(m2)
    
    for zone in ["North", "South", "Back"]:
        for t in zones[zone]:
            target = t.get("target_size", expected_size)
            while len(t["members_ids"]) < target and leftovers:
                if len(t["members_ids"]) == 0:
                    # Le premier membre est le plus fort disponible
                    filler = leftovers.pop(0)
                else:
                    # Choisir le personnage ayant la meilleure synergie avec le reste de l'équipe
                    best_filler = None
                    best_score = -1
                    best_idx = 0
                    
                    for i, cand in enumerate(leftovers):
                        cand_synergy = synergy_graph.get(cand, set())
                        # 1 point de synergie par membre de l'équipe actuelle avec qui il est connecté dans la méta
                        synergy_score = sum(1 for m in t["members_ids"] if m in cand_synergy)
                        
                        # Pondération : La synergie est reine. En cas d'égalité, on prend celui avec le plus de GP (l'index i le plus bas)
                        weighted_score = synergy_score * 1000 - i
                        
                        if weighted_score > best_score:
                            best_score = weighted_score
                            best_filler = cand
                            best_idx = i
                            
                    filler = leftovers.pop(best_idx)

                t["members_ids"].append(filler)
                used_base_ids.add(filler)
                
            if t["source"] == "empty" and t["members_ids"]:
                t["leader_id"] = t["members_ids"][0]
                t["source"] = "leftover"

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
            if f["leader_id"] not in used_base_ids and f["leader_id"] != "USED":
                valid_members = [m for m in f["members"] if m not in used_base_ids]
                zones["Fleet"].append({
                    "leader_id": f["leader_id"],
                    "members_ids": valid_members,
                    "source": "predictive",
                    "target_size": 5
                })
                used_base_ids.update(valid_members)
                f["leader_id"] = "USED"
                placed = True
                break
        if not placed:
            zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": 5})

    # 2.5 BOUCHAGE FLOTTES
    leftover_capitals = [m for m, data in enemy_index.items() if m not in used_base_ids and data.get("combat_type", 1) == 2 and "CAPITAL" in m]
    leftover_ships = [m for m, data in enemy_index.items() if m not in used_base_ids and data.get("combat_type", 1) == 2 and "CAPITAL" not in m]
    
    leftover_capitals.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)
    leftover_ships.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)
    
    for f in zones["Fleet"]:
        if f["source"] == "empty" and leftover_capitals:
            cap = leftover_capitals.pop(0)
            f["leader_id"] = cap
            f["members_ids"].append(cap)
            used_base_ids.add(cap)
            f["source"] = "leftover"
            
        while len(f["members_ids"]) < f.get("target_size", 5) and leftover_ships:
            filler = leftover_ships.pop(0)
            f["members_ids"].append(filler)
            used_base_ids.add(filler)

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
    omicron_dict = await get_omicron_dict()
    enemy_index = _build_roster_index(profile.get("rosterUnit", []), omicron_dict)
    
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
            my_index = _build_roster_index(my_profile.get("rosterUnit", []), omicron_dict)
            my_zones = _predict_zones(my_index, quotas, fmt)
            result["my_zones"] = my_zones
            result["my_name"] = my_profile.get("name", my_clean)

    return result
