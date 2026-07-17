"""
services/scouting.py — Moteur de Scouting Hybride pour la GAC
"""
import logging
from database.db import get_db
from services.comlink import get_player
from utils.gac_config import get_gac_quotas
from services.gac_meta import GAC_FLEETS, GAC_TEAMS

log = logging.getLogger(__name__)

LEAGUE_MAP = {
    1: "CARBONITE",
    2: "BRONZIUM",
    3: "CHROMIUM",
    4: "AURODIUM",
    5: "KYBER"
}

UNIT_RESTRICTIONS = {
    "EZRABRIDGEREXILE": ["GLAHSOKATANO"],
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

async def get_ship_base_ids() -> set:
    ships = set()
    try:
        async with get_db() as db:
            async with db.execute("SELECT base_id FROM game_characters WHERE type = 'ship'") as cursor:
                async for row in cursor:
                    ships.add(row["base_id"])
    except Exception as e:
        log.warning(f"Erreur chargement des vaisseaux: {e}")
    return ships

def _build_roster_index(raw_roster: list, omicron_dict: dict, ship_base_ids: set) -> dict:
    roster = {}
    for unit in raw_roster:
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
        relic_tier = max(0, raw_relic - 2) if raw_relic >= 2 else 0
        
        has_omicron = False
        if omicron_dict:
            unit_skills = (unit.get("skill") or [])
            for skill in unit_skills:
                skill_id = skill.get("id")
                skill_tier = skill.get("tier", 0)
                if skill_id in omicron_dict and skill_tier >= omicron_dict[skill_id]:
                    has_omicron = True
                    break
                    
        combat_type = 2 if base_id in ship_base_ids else unit.get("combatType", 1)

        roster[base_id] = {
            "base_id": base_id,
            "gear_tier": unit.get("currentTier", 0),
            "relic_tier": relic_tier,
            "rarity": unit.get("currentRarity", 0),
            "has_omicron": has_omicron,
            "combat_type": combat_type
        }
    return roster

async def _predict_zones(enemy_index: dict, quotas: dict, fmt: str, ship_base_ids: set, habits: dict = None) -> dict:
    zones = {"North": [], "South": [], "Back": [], "Fleet": []}
    used_base_ids = set()
    expected_size = 3 if fmt == "3v3" else 5
            
    # 1. PERSONNAGES (Via la Meta Dynamique de swgoh.gg uniquement)
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
                    
                # Sécurité : ignorer les équipes de la meta dont la taille ne correspond pas au format
                expected_max = 3 if fmt == "3v3" else 5
                if len(units) > expected_max:
                    continue
                    
                leader_id = units[0]
                # On utilise une échelle 0-10 basée sur le % de holds pour la défense
                def_score = min(10, int((row["hold_percent"] or 0) / 10))
                dynamic_teams.append({
                    "leader_id": leader_id,
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
        core_ready = []
        for m in core:
            if m in enemy_index and _is_gac_ready(enemy_index[m]):
                if m in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[m]:
                    continue
                core_ready.append(m)
        
        # RÈGLE D'OR STRATÉGIQUE : 
        # L'équipe doit avoir au moins (expected_size - 1) membres prêts (ex: 4/5 ou 2/3)
        min_size = expected_size - 1
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

    # 0. INJECTION DE L'HISTORIQUE RÉEL (Avec logique d'Upgrade)
    if habits and habits.get("total_rounds", 0) > 0:
        mapping = {"top": "North", "bottom": "South", "back": "Back", "fleet": "Fleet"}
        for hz, h_name in mapping.items():
            teams = habits["zones"].get(hz, [])
            quota = quotas.get(h_name, 0)
            
            placed_in_zone = 0
            for t in teams:
                if placed_in_zone >= quota:
                    break
                    
                leader = t["leader_id"]
                members = t["members"]
                percent = t["percent"]
                
                valid_members = []
                for m in members:
                    if m not in used_base_ids:
                        if m in UNIT_RESTRICTIONS and leader not in UNIT_RESTRICTIONS[m]:
                            continue
                        valid_members.append(m)

                if leader not in used_base_ids:
                    
                    # FILTRE ANTI-GARBAGE (Équipes auto-déployées absurdes)
                    if hz != "fleet":
                        # On utilise la BDD dynamique pour juger si la compo est absurde
                        known_meta_for_leader = [mt for mt in dynamic_teams if mt["leader_id"] == leader]
                        if known_meta_for_leader:
                            # Le leader est censé avoir une équipe Meta.
                            has_synergy = False
                            for mt in known_meta_for_leader:
                                meta_members_set = set(mt.get("core", []))
                                overlap = len(set(valid_members).intersection(meta_members_set))
                                if overlap > 0:
                                    has_synergy = True
                                    break
                            
                            # Si c'est une horreur générée auto (0 synergie avec la vraie compo), on la jette !
                            if not has_synergy and len(valid_members) > 0 and percent < 5.0:
                                continue

                    # Logique de remplacement (Upgrade)
                    best_upgrade = None
                    if hz != "fleet":
                        # Chercher si une équipe Meta partage des personnages clés et est plus forte
                        history_set = set([leader] + valid_members)
                        
                        for meta_team in available_teams:
                            if meta_team["leader_id"] in used_base_ids:
                                continue
                                
                            meta_set = set([meta_team["leader_id"]] + meta_team["members"])
                            overlap = len(history_set.intersection(meta_set))
                            
                            # Si on a un chevauchement significatif (au moins 2 persos en 5v5, 1 ou 2 en 3v3)
                            # Ou si le leader est le même mais la compo Meta est meilleure
                            # Et que le score de défense de la Meta est très bon
                            if overlap >= (1 if expected_size == 3 else 2) or leader == meta_team["leader_id"]:
                                # Un upgrade est valide si la Meta a un meilleur score défensif strict
                                # ou si la Meta contient des personnages Premium (GL, Reva, Bane) non présents historiquement
                                premium_units = ["THIRDSISTER", "GLREY", "JEDIMASTERKENOBI", "SUPREMELEADERKYLOREN", "SITHPALPATINE", "JEDIMASTERLUKE", "LORDVADER", "JABBATHEHUTT", "LEIAORGANA", "DARTHBANE", "TARONMALICOS", "BOKATANMANDALOR"]
                                has_new_premium = any(p in meta_set and p not in history_set for p in premium_units)
                                
                                # On simule le score def de l'équipe historique si c'était une Meta
                                # Pour simplifier, on dit que si la Meta a >= 7 en défense ou a un premium, on upgrade.
                                # Sauf si l'historique a déjà un excellent percent (ex: > 80%).
                                if (meta_team["defense"] >= 7 or has_new_premium) and percent < 90:
                                    if best_upgrade is None or meta_team["defense"] > best_upgrade["defense"]:
                                        best_upgrade = meta_team
                                        
                    if best_upgrade:
                        # Remplacement par l'Upgrade
                        upgrade_leader = best_upgrade["leader_id"]
                        upgrade_members = best_upgrade["members"]
                        
                        zones[h_name].append({
                            "leader_id": upgrade_leader,
                            "members_ids": upgrade_members,
                            "source": f"Upgrade (Ancien: {leader})",
                            "target_size": expected_size
                        })
                        used_base_ids.add(upgrade_leader)
                        used_base_ids.update(upgrade_members)
                        placed_in_zone += 1
                        # On retire l'équipe Meta des available_teams pour ne pas la réutiliser
                        best_upgrade["leader_id"] = "USED"
                    else:
                        # Ajout classique de l'équipe historique
                        zones[h_name].append({
                            "leader_id": leader,
                            "members_ids": valid_members,
                            "source": f"Historique ({percent}%)",
                            "target_size": expected_size if hz != "fleet" else 8
                        })
                        used_base_ids.add(leader)
                        used_base_ids.update(valid_members)
                        placed_in_zone += 1
    
    for zone in ["North", "South", "Back"]:
        q = quotas.get(zone, 0)
        remaining_q = max(0, q - len(zones[zone]))
        for _ in range(remaining_q):
            zones[zone].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": expected_size})

    # Construire leader_synergy_map pour le bouchage des trous (Hole-Filling)
    leader_synergy_map = {}
    for team_data in dynamic_teams:
        ldr = team_data["leader_id"]
        if ldr not in leader_synergy_map:
            leader_synergy_map[ldr] = []
        for m in team_data.get("core", []):
            if m != ldr and m not in leader_synergy_map[ldr]:
                leader_synergy_map[ldr].append(m)

    # BOUCHAGE DE TROUS (Hole-Filling) AVEC SYNERGIE
    leftovers = [
        m for m, data in enemy_index.items()
        if m not in used_base_ids
        and data.get("combat_type", 1) == 1
    ]
    leftovers.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)

    for zone in ["North", "South", "Back"]:
        for t in zones[zone]:
            target = t.get("target_size", expected_size)
            leader_id = t.get("leader_id")
            need = target - (1 if leader_id else 0)
            while len(t["members_ids"]) < need:
                if not leader_id:
                    # Équipe totalement vide : prendre le plus fort
                    filler = None
                    for i, l in enumerate(leftovers):
                        if l in UNIT_RESTRICTIONS and not UNIT_RESTRICTIONS[l]: # Si pas de leader valide on passe
                            continue
                        filler = leftovers.pop(i)
                        break
                    if not filler:
                        break
                    t["leader_id"] = filler
                    leader_id = filler
                    t["source"] = "leftover"
                    need = target - 1
                else:
                    filler = None
                    synergy_candidates = leader_synergy_map.get(leader_id, [])
                    for candidate in synergy_candidates:
                        if candidate in leftovers and candidate not in t["members_ids"]:
                            if candidate in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[candidate]:
                                continue
                            filler = candidate
                            leftovers.remove(candidate)
                            break

                    if filler is None and leftovers:
                        for i, l in enumerate(leftovers):
                            if l in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[l]:
                                continue
                            filler = leftovers.pop(i)
                            break

                    if filler is None:
                        break

                    t["members_ids"].append(filler)
                if filler:
                    used_base_ids.add(filler)

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
                    "target_size": 8
                })
                used_base_ids.update(valid_members)
                f["leader_id"] = "USED"
                placed = True
                break
        if not placed:
            zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": 8})

    # 2.5 BOUCHAGE FLOTTES
    # On filtre sur combat_type ET sur ship_base_ids (double sécurité)
    # pour éviter qu'un perso mal typé se retrouve dans la zone Fleet.
    leftover_capitals = [
        m for m, data in enemy_index.items()
        if m not in used_base_ids
        and data.get("combat_type", 1) == 2
        and m in ship_base_ids
        and "CAPITAL" in m
    ]
    leftover_ships = [
        m for m, data in enemy_index.items()
        if m not in used_base_ids
        and data.get("combat_type", 1) == 2
        and m in ship_base_ids
        and "CAPITAL" not in m
        and data.get("combat_type", 1) != 1  # Exclure explicitement les persos
    ]
    
    leftover_capitals.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)
    leftover_ships.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)
    
    for f in zones["Fleet"]:
        if f["source"] == "empty" and leftover_capitals:
            cap = leftover_capitals.pop(0)
            f["leader_id"] = cap
            f["members_ids"].append(cap)
            used_base_ids.add(cap)
            f["source"] = "leftover"
            
        while len(f["members_ids"]) < f.get("target_size", 8) and leftover_ships:
            filler = leftover_ships.pop(0)
            f["members_ids"].append(filler)
            used_base_ids.add(filler)

    return zones

async def _plan_user_defense(ally_code: str, my_index: dict, quotas: dict, fmt: str, ship_base_ids: set, enemy_zones: dict = None) -> dict:
    zones = {"North": [], "South": [], "Back": [], "Fleet": []}
    used_base_ids = set()
    expected_size = 3 if fmt == "3v3" else 5
    
    # --- NOUVEAUTÉ : Réservation des équipes d'attaque ---
    if enemy_zones:
        try:
            from services.gac_attack_planner import get_best_counter_with_memory
            for zone, teams in enemy_zones.items():
                if zone == "Fleet": continue
                for team in teams:
                    leader = team.get("leader_id")
                    members = team.get("members_ids", [])
                    if leader and leader != "USED" and leader != "None":
                        counters = await get_best_counter_with_memory(leader, members, fmt, my_index, used_base_ids)
                        if counters:
                            best_counter = counters[0]
                            used_base_ids.add(best_counter["atk_leader_id"])
                            used_base_ids.update(best_counter.get("atk_members_ids", []))
        except Exception as e:
            log.error(f"Erreur lors de la réservation des équipes d'attaque : {e}")

    
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

    # Capturer la carte de synergie AVANT la boucle de placement (les leaders seront marqués "USED")
    leader_synergy_map = {}
    for sugg in suggestions:
        ldr = sugg.get("leader")
        if ldr and ldr != "USED":
            meta_members = [m for m in sugg.get("valid_members", []) if m != ldr]
            leader_synergy_map[ldr] = meta_members

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

    # Enrichir la leader_synergy_map depuis la BDD pour les leaders placés
    # non couverts par les suggestions initiales (qui étaient limitées à 500 lignes)
    import json as _json
    all_placed_leaders = {
        t.get("leader_id")
        for zone in ["North", "South", "Back"]
        for t in zones[zone]
        if t.get("leader_id")
    }
    missing_leaders = all_placed_leaders - set(leader_synergy_map.keys())
    if missing_leaders:
        async with get_db() as db:
            async with db.execute(
                "SELECT squad_units FROM gac_global_meta WHERE format = ? AND mode = 'defense' ORDER BY hold_percent DESC LIMIT 300",
                (fmt,)
            ) as cur:
                db_rows = await cur.fetchall()
        for row in db_rows:
            try:
                units = _json.loads(row["squad_units"])
            except Exception:
                continue
            if not units:
                continue
            ldr = units[0]
            if ldr in missing_leaders:
                if ldr not in leader_synergy_map:
                    leader_synergy_map[ldr] = []
                for m in units[1:]:
                    if m not in leader_synergy_map[ldr]:
                        leader_synergy_map[ldr].append(m)

    # 1.5 BOUCHAGE DE TROUS (Hole-Filling) AVEC SYNERGIE — 3 niveaux
    # Niveau 1 : Personnage avec synergie méta parmi les leftovers libres
    # Niveau 2 : Personnage avec synergie méta réservé pour l'attaque → libération
    # Niveau 3 : Fallback sur le personnage le plus puissant disponible
    leftovers_t1 = [
        m for m, data in my_index.items()
        if m not in used_base_ids
        and data.get("combat_type", 1) == 1
    ]

    # Trier par puissance de base (fallback niveau 3)
    leftovers_t1.sort(key=lambda m: my_index[m].get("relic_tier", 0) * 10 + my_index[m].get("gear_tier", 0), reverse=True)

    leftovers = leftovers_t1

    for zone in ["North", "South", "Back"]:
        for t in zones[zone]:
            target = t.get("target_size", expected_size)
            leader_id = t.get("leader_id")
            need = target - (1 if leader_id else 0)
            while len(t["members_ids"]) < need:
                if not leader_id:
                    # Équipe totalement vide : prendre le plus fort
                    filler = None
                    for i, l in enumerate(leftovers):
                        if l in UNIT_RESTRICTIONS and not UNIT_RESTRICTIONS[l]:
                            continue
                        filler = leftovers.pop(i)
                        break
                    if not filler:
                        break
                    t["leader_id"] = filler
                    leader_id = filler
                    t["source"] = "leftover"
                    need = target - 1  # Recalcul après avoir trouvé un leader
                else:
                    filler = None
                    synergy_candidates = leader_synergy_map.get(leader_id, [])

                    # Niveau 1 : synergie méta parmi les leftovers libres
                    for candidate in synergy_candidates:
                        if candidate in leftovers and candidate not in t["members_ids"]:
                            if candidate in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[candidate]:
                                continue
                            filler = candidate
                            leftovers.remove(candidate)
                            break

                    # Niveau 2 : libérer un perso réservé pour l'attaque (synergie confirmée)
                    if filler is None:
                        for candidate in synergy_candidates:
                            if (
                                candidate in my_index
                                and candidate in used_base_ids
                                and candidate not in t["members_ids"]
                                and my_index[candidate].get("combat_type", 1) == 1
                            ):
                                if candidate in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[candidate]:
                                    continue
                                filler = candidate
                                used_base_ids.discard(candidate)
                                log.debug(f"[HoleFill] {candidate} libéré de l'attaque → synergie {leader_id}")
                                break

                    # Niveau 3 : fallback — le plus puissant dispo dans les leftovers
                    if filler is None and leftovers:
                        for i, l in enumerate(leftovers):
                            if l in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[l]:
                                continue
                            filler = leftovers.pop(i)
                            break

                    if filler is None:
                        break  # Rien à placer pour cette équipe

                    t["members_ids"].append(filler)

                if filler:
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
                    "target_size": 8
                })
                used_base_ids.update(valid_members)
                f["leader_id"] = "USED"
                placed = True
                break
        if not placed:
            zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": 8})

    # 2.5 BOUCHAGE FLOTTES
    leftover_capitals = [m for m, data in my_index.items() if m not in used_base_ids and data.get("combat_type", 1) == 2 and m in ship_base_ids and "CAPITAL" in m]
    leftover_ships = [m for m, data in my_index.items() if m not in used_base_ids and data.get("combat_type", 1) == 2 and m in ship_base_ids and "CAPITAL" not in m]
    
    leftover_capitals.sort(key=lambda m: my_index[m].get("relic_tier", 0) * 10 + my_index[m].get("gear_tier", 0), reverse=True)
    leftover_ships.sort(key=lambda m: my_index[m].get("relic_tier", 0) * 10 + my_index[m].get("gear_tier", 0), reverse=True)
    
    for f in zones["Fleet"]:
        if f["source"] == "empty" and leftover_capitals:
            cap = leftover_capitals.pop(0)
            f["leader_id"] = cap
            f["members_ids"].append(cap)
            used_base_ids.add(cap)
            f["source"] = "leftover"
            
        while len(f["members_ids"]) < f.get("target_size", 8) and leftover_ships:
            filler = leftover_ships.pop(0)
            f["members_ids"].append(filler)
            used_base_ids.add(filler)

    return zones

async def get_scout_data(enemy_ally_code: str, fmt: str, my_ally_code: str | None = None, progress_callback=None) -> dict:
    clean_code = str(enemy_ally_code).replace("-", "").strip()
    profile = await get_player(clean_code)
    
    if not profile:
        raise ValueError(f"Profil introuvable pour {clean_code}")

    enemy_name = profile.get("name", clean_code)
    
    league_name = "CARBONITE"
    target_code = my_ally_code.replace("-", "").strip() if my_ally_code else clean_code
    
    target_profile = await get_player(target_code) if my_ally_code else profile
    if target_profile:
        season_status = target_profile.get("seasonStatus", [])
        if season_status:
            last_season = season_status[-1]
            league_val = last_season.get("league", "CARBONITE")
            if isinstance(league_val, str):
                league_name = league_val.split("_")[-1].upper()
            else:
                league_name = LEAGUE_MAP.get(league_val, "CARBONITE")
    else:
        from database.db import get_db
        async with get_db() as db:
            cursor = await db.execute("SELECT league FROM gac_rounds WHERE player_code = ? AND league IS NOT NULL ORDER BY id DESC LIMIT 1", (target_code,))
            row = await cursor.fetchone()
            if row and row["league"]:
                league_name = row["league"].upper()
            
    if league_name not in ["CARBONITE", "BRONZIUM", "CHROMIUM", "AURODIUM", "KYBER"]:
        league_name = "CARBONITE"
        
    quotas = get_gac_quotas(league_name, fmt)
    omicron_dict = await get_omicron_dict()
    ship_base_ids = await get_ship_base_ids()
    enemy_index = _build_roster_index(profile.get("rosterUnit", []), omicron_dict, ship_base_ids)
    
    from services.gac_scout_analyzer import GacScoutAnalyzer
    habits = await GacScoutAnalyzer.get_defensive_habits(clean_code, fmt)
    
    enemy_zones = await _predict_zones(enemy_index, quotas, fmt, ship_base_ids, habits)
    
    # ---------------------------------------------------------------------
    # NOUVEAUTÉ : Attente SYCHRONE du scraping des counters manquants
    # ---------------------------------------------------------------------
    if my_ally_code:
        try:
            leaders_to_scrape = {}
            for zone, teams in enemy_zones.items():
                if zone == "Fleet": continue
                for team in teams:
                    if team.get("leader_id"):
                        members = team.get("members_ids", [])
                        members_str = ",".join(members)
                        leaders_to_scrape[team["leader_id"]] = members_str
                        
            if leaders_to_scrape:
                from services.gac_counters_scraper import GacCountersScraper
                scraper = GacCountersScraper()
                
                # Check d'abord combien en ont besoin (pour le message Discord)
                from database.db import get_db
                import datetime
                missing_leaders = []
                async with get_db() as db:
                    for l_id, members_str in leaders_to_scrape.items():
                        if not l_id or l_id in ["USED", "None"]: continue
                        cursor = await db.execute("SELECT last_updated FROM gac_counters WHERE def_leader_id = ? AND format = ? ORDER BY last_updated DESC LIMIT 1", (l_id, fmt))
                        row = await cursor.fetchone()
                        if row:
                            try:
                                age = (datetime.datetime.utcnow() - datetime.datetime.strptime(row["last_updated"], "%Y-%m-%d %H:%M:%S")).days
                                if age > 7: missing_leaders.append(l_id)
                            except: pass
                        else:
                            missing_leaders.append(l_id)
                
                if missing_leaders and progress_callback:
                    await progress_callback(f"⏳ **Optimisation des données** : Calcul des meilleurs contres pour {len(missing_leaders)} équipes ennemies. Cette étape prend environ {len(missing_leaders) * 20} secondes. Merci de patienter...")
                
                await scraper.ensure_counters_available(leaders_to_scrape, fmt, progress_callback=progress_callback)
        except Exception as e:
            log.error(f"Erreur lors de l'attente du scraping des counters: {e}")
    # ---------------------------------------------------------------------
    
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
            my_index = _build_roster_index(my_profile.get("rosterUnit", []), omicron_dict, ship_base_ids)
            my_zones = await _plan_user_defense(my_clean, my_index, quotas, fmt, ship_base_ids, enemy_zones)
            result["my_zones"] = my_zones
            result["my_name"] = my_profile.get("name", my_clean)
            result["my_roster_index"] = my_index

    return result
