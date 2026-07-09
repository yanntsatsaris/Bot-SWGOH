"""
services/scouting.py — Moteur de Scouting Hybride pour la GAC
"""
import logging
from database.db import get_db
from services.comlink import get_player
from utils.gac_config import get_gac_quotas
from services.gac_meta import GAC_FLEETS

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

async def _predict_zones(enemy_index: dict, quotas: dict, fmt: str, habits: dict = None) -> dict:
    zones = {"North": [], "South": [], "Back": [], "Fleet": []}
    used_base_ids = set()
    expected_size = 3 if fmt == "3v3" else 5
    
    # 0. INJECTION DE L'HISTORIQUE RÉEL
    if habits and habits.get("total_rounds", 0) > 0:
        mapping = {"top": "North", "bottom": "South", "back": "Back", "fleet": "Fleet"}
        for hz, h_name in mapping.items():
            teams = habits["zones"].get(hz, [])
            quota = quotas.get(h_name, 0)
            
            # Prendre les N équipes les plus fréquentes (où N = quota de la zone)
            for t in teams[:quota]:
                leader = t["leader_id"]
                members = t["members"]
                percent = t["percent"]
                
                valid_members = [m for m in members if m not in used_base_ids]
                if leader not in used_base_ids:
                    # Ajout de l'équipe historique
                    zones[h_name].append({
                        "leader_id": leader,
                        "members_ids": valid_members,
                        "source": f"Historique ({percent}%)",
                        "target_size": expected_size if hz != "fleet" else 7
                    })
                    used_base_ids.add(leader)
                    used_base_ids.update(valid_members)
    
    # 1. PERSONNAGES (Via la Meta Dynamique de swgoh.gg)
    # Récupérer les top teams défensives depuis la BDD
    dynamic_teams = []
    import json
    async with get_db() as db:
        async with db.execute(
            "SELECT squad_units, hold_percent, avg_banners FROM gac_global_meta WHERE format = ? AND mode = 'defense' ORDER BY seen DESC LIMIT 150",
            (fmt,)
        ) as cur:
            rows = await cur.fetchall()
            for row in rows:
                units = json.loads(row["squad_units"])
                if not units:
                    continue
                # On utilise une échelle 0-10 basée sur le % de holds pour la défense
                def_score = min(10, int((row["hold_percent"] or 0) / 10))
                dynamic_teams.append({
                    "leader_id": units[0],
                    "core": units, # Tous les membres sont considérés comme "core" (équipe stricte)
                    "defense": def_score,
                    "offense": 0, # Inconnu pour les stats défensives
                    "target_size": len(units)
                })

    available_teams = []
    for team_data in dynamic_teams:
        leader_id = team_data["leader_id"]
        core = team_data.get("core", [])
        
        # Vérifier que l'équipe stricte est présente (au moins X membres)
        if leader_id not in enemy_index or not _is_gac_ready(enemy_index[leader_id]):
            continue
            
        # Vu que ce sont des équipes exactes issues des stats globales, on tolère qu'il manque au maximum 1 membre non-leader,
        # qui sera bouché par les leftovers. Si on exige tout le monde, on risque de rejeter trop d'équipes si le joueur 
        # a mis un perso différent. Mais idéalement, on exige au moins le core minimum.
        core_ready = [m for m in core if m in enemy_index and _is_gac_ready(enemy_index[m])]
        
        # RÈGLE D'OR STRATÉGIQUE : 
        # L'équipe doit avoir au moins (expected_size - 1) membres prêts (ex: 4/5 ou 2/3)
        min_size = expected_size - 1 if expected_size > 3 else expected_size
        if len(core_ready) < min_size:
            continue
            
        # On accepte l'équipe telle quelle
        def_score = team_data.get("defense", 5)
        off_score = team_data.get("offense", 5)
        score = def_score + len(core_ready) # Bonus si équipe très complète
        
        available_teams.append({
            "leader_id": leader_id,
            "members": core_ready,
            "defense": def_score,
            "offense": off_score,
            "score": score,
            "target_size": expected_size,
            "id": leader_id
        })
                
    # Trier par "Biais Défensif" (defense - offense), puis par défense absolue, puis puissance
    available_teams.sort(key=lambda x: (x["defense"] - x["offense"], x["defense"], x["score"]), reverse=True)

    # Filtrer les doublons de leader (si le joueur a les unités pour la Variation 1 et Variation 2)
    filtered_teams = []
    seen_leaders = set()
    for t in available_teams:
        if t["leader_id"] not in seen_leaders:
            filtered_teams.append(t)
            seen_leaders.add(t["leader_id"])
    available_teams = filtered_teams

    # Identification des personnages strictement réservés à l'attaque
    offense_only_chars = set()
    for t in available_teams:
        if t["defense"] <= 2:
            if t["leader_id"]:
                offense_only_chars.add(t["leader_id"])
            for c in t.get("members", []):
                offense_only_chars.add(c)
    
    for zone in ["North", "South", "Back"]:
        q = quotas.get(zone, 0)
        remaining_q = max(0, q - len(zones[zone]))
        for _ in range(remaining_q):
            placed = False
            for t in available_teams:
                # Interdiction de placer une équipe d'Attaque pure (Défense <= 2) en Défense
                if t["defense"] <= 2:
                    continue
                    
                # Vérifier que le leader et les membres sont dispos
                if t["leader_id"] not in used_base_ids and t["leader_id"] != "USED":
                    valid_members = [m for m in t["members"] if m not in used_base_ids]
                    
                    # Règle stricte min_size : l'équipe doit avoir assez de membres disponibles pour atteindre sa taille requise
                    if len(valid_members) + 1 < t["target_size"]:
                        continue
                        
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

    # 1.5 BOUCHAGE DE TROUS (Hole-Filling) INTELLIGENT
    # Tier 1 : Personnages non réservés à l'attaque
    leftovers_t1 = [
        m for m, data in enemy_index.items() 
        if m not in used_base_ids 
        and m not in offense_only_chars
        and data.get("combat_type", 1) == 1
    ]
    # Tier 2 : Personnages réservés à l'attaque (on les utilise en dernier recours plutôt que de laisser un trou)
    leftovers_t2 = [
        m for m, data in enemy_index.items()
        if m not in used_base_ids
        and m in offense_only_chars
        and data.get("combat_type", 1) == 1
    ]
    
    # Trier chaque tier par puissance de base
    leftovers_t1.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)
    leftovers_t2.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)
    
    # Combiner les tiers (T1 d'abord, puis T2)
    leftovers = leftovers_t1 + leftovers_t2
    
    # Construire le graphe de synergie basé sur la méta connue (dynamic_teams)
    synergy_graph = {}
    for team_data in dynamic_teams:
        all_members = team_data.get("core", [])
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
    remaining_fleet_q = max(0, fleet_quota - len(zones["Fleet"]))
    for _ in range(remaining_fleet_q):
        placed = False
        for f in available_fleets:
            if f["leader_id"] not in used_base_ids and f["leader_id"] != "USED":
                valid_members = [m for m in f["members"] if m not in used_base_ids]
                zones["Fleet"].append({
                    "leader_id": f["leader_id"],
                    "members_ids": valid_members,
                    "source": "predictive",
                    "target_size": 7
                })
                used_base_ids.update(valid_members)
                f["leader_id"] = "USED"
                placed = True
                break
        if not placed:
            zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": 7})

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
            
        while len(f["members_ids"]) < f.get("target_size", 7) and leftover_ships:
            filler = leftover_ships.pop(0)
            f["members_ids"].append(filler)
            used_base_ids.add(filler)

    return zones

async def _plan_user_defense(ally_code: str, my_index: dict, quotas: dict, fmt: str) -> dict:
    zones = {"North": [], "South": [], "Back": [], "Fleet": []}
    used_base_ids = set()
    expected_size = 3 if fmt == "3v3" else 5
    
    from services.gac_planner import GacPlanner
    planner = GacPlanner()
    suggestions = await planner.get_team_suggestions(
        ally_code=ally_code,
        format_type=fmt,
        mode="defense",
        min_relic=-1,
        min_gear=12
    )
    
    if not suggestions:
        return await _predict_zones(my_index, quotas, fmt, None)

    # 1. Escouades au sol
    for zone in ["North", "South", "Back"]:
        q = quotas.get(zone, 0)
        remaining_q = max(0, q - len(zones[zone]))
        for _ in range(remaining_q):
            placed = False
            for sugg in suggestions:
                leader_id = sugg["leader"]
                if leader_id not in used_base_ids and leader_id != "USED":
                    # Mettre uniquement les membres valides (qui ont au moins G12)
                    valid_members = [m for m in sugg["valid_members"] if m not in used_base_ids and m != leader_id]
                    
                    zones[zone].append({
                        "leader_id": leader_id,
                        "members_ids": valid_members,
                        "source": "Meta SWGOH.gg",
                        "target_size": expected_size
                    })
                    used_base_ids.add(leader_id)
                    used_base_ids.update(valid_members)
                    sugg["leader"] = "USED" # On marque l'équipe comme consommée
                    placed = True
                    break
            
            if not placed:
                zones[zone].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": expected_size})

    # 1.5 BOUCHAGE DE TROUS (Hole-Filling) INTELLIGENT
    # Tier 1 : Personnages avec combat_type = 1
    leftovers_t1 = [
        m for m, data in my_index.items() 
        if m not in used_base_ids 
        and data.get("combat_type", 1) == 1
    ]
    
    # Trier par puissance de base
    leftovers_t1.sort(key=lambda m: my_index[m].get("relic_tier", 0) * 10 + my_index[m].get("gear_tier", 0), reverse=True)
    
    leftovers = leftovers_t1
    
    # Pour la synergie, on pourrait utiliser les suggestions mais pour aller vite on va juste boucher avec les plus forts
    for zone in ["North", "South", "Back"]:
        for t in zones[zone]:
            target = t.get("target_size", expected_size)
            while len(t["members_ids"]) < target - (1 if t.get("leader_id") else 0) and leftovers:
                if not t.get("leader_id"):
                    # Si c'est une équipe totalement vide
                    filler = leftovers.pop(0)
                    t["leader_id"] = filler
                    t["source"] = "leftover"
                else:
                    filler = leftovers.pop(0)
                    t["members_ids"].append(filler)
                used_base_ids.add(filler)

    # 2. FLOTTES (identique à _predict_zones)
    available_fleets = []
    for cap_id, team_data in GAC_FLEETS.items():
        if my_index.get(cap_id) and my_index[cap_id].get("rarity", 0) >= 5:
            score = my_index[cap_id].get("relic_tier", 0) * 10 + my_index[cap_id].get("gear_tier", 0)
            available_fleets.append({
                "leader_id": cap_id,
                "members": team_data["members"],
                "defense": team_data.get("defense", 5),
                "score": score
            })
            
    available_fleets.sort(key=lambda x: (x["defense"], x["score"]), reverse=True)
    
    fleet_quota = quotas.get("Fleet", 1)
    remaining_fleet_q = max(0, fleet_quota - len(zones["Fleet"]))
    for _ in range(remaining_fleet_q):
        placed = False
        for f in available_fleets:
            if f["leader_id"] not in used_base_ids and f["leader_id"] != "USED":
                valid_members = [m for m in f["members"] if m not in used_base_ids and m in my_index]
                zones["Fleet"].append({
                    "leader_id": f["leader_id"],
                    "members_ids": valid_members,
                    "source": "predictive",
                    "target_size": 7
                })
                used_base_ids.update(valid_members)
                f["leader_id"] = "USED"
                placed = True
                break
        if not placed:
            zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": 7})

    # 2.5 BOUCHAGE FLOTTES
    leftover_capitals = [m for m, data in my_index.items() if m not in used_base_ids and data.get("combat_type", 1) == 2 and "CAPITAL" in m]
    leftover_ships = [m for m, data in my_index.items() if m not in used_base_ids and data.get("combat_type", 1) == 2 and "CAPITAL" not in m]
    
    leftover_capitals.sort(key=lambda m: my_index[m].get("relic_tier", 0) * 10 + my_index[m].get("gear_tier", 0), reverse=True)
    leftover_ships.sort(key=lambda m: my_index[m].get("relic_tier", 0) * 10 + my_index[m].get("gear_tier", 0), reverse=True)
    
    for f in zones["Fleet"]:
        if f["source"] == "empty" and leftover_capitals:
            cap = leftover_capitals.pop(0)
            f["leader_id"] = cap
            f["members_ids"].append(cap)
            used_base_ids.add(cap)
            f["source"] = "leftover"
            
        while len(f["members_ids"]) < f.get("target_size", 7) and leftover_ships:
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
    
    from services.gac_scout_analyzer import GacScoutAnalyzer
    habits = await GacScoutAnalyzer.get_defensive_habits(clean_code, fmt)
    
    enemy_zones = await _predict_zones(enemy_index, quotas, fmt, habits)
    
    has_habits = habits and habits.get("total_rounds", 0) > 0
    result = {
        "enemy_name": enemy_name,
        "league": league_name,
        "format": fmt,
        "source": "Historique + Prédiction" if has_habits else "Prédiction Offense/Défense",
        "zones": enemy_zones,
        "quotas": quotas,
        "roster_index": enemy_index
    }
    
    if my_ally_code:
        my_clean = str(my_ally_code).replace("-", "").strip()
        my_profile = await get_player(my_clean)
        if my_profile:
            my_index = _build_roster_index(my_profile.get("rosterUnit", []), omicron_dict)
            my_zones = await _plan_user_defense(my_clean, my_index, quotas, fmt)
            result["my_zones"] = my_zones
            result["my_name"] = my_profile.get("name", my_clean)
            result["my_roster_index"] = my_index

    return result
