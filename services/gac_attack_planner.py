"""
services/gac_attack_planner.py
Planification et filtrage des counters.
"""
import logging
from database.db import get_counters_from_db, get_counter_feedback_stats

log = logging.getLogger(__name__)

def filter_counters_by_roster(counters: list[dict], my_roster_index: dict, format_type: str, min_relic: int = 5, min_gear: int = 13) -> list[dict]:
    """
    Filtre et enrichit les counters selon le roster du joueur.
    """
    result = []
    
    for counter in counters:
        max_atk_members = 2 if format_type == "3v3" else 4
        all_ids = [counter["atk_leader_id"]] + counter.get("atk_members_ids", [])[:max_atk_members]
        
        available = []
        missing = []
        for unit_id in all_ids:
            unit = my_roster_index.get(unit_id.upper())
            if unit and (unit.get("relic_tier", 0) >= min_relic or unit.get("gear_tier", 0) >= min_gear):
                available.append(unit_id)
            else:
                missing.append(unit_id)
        
        availability = len(available) / max(len(all_ids), 1)
        
        # 60% pour 5v5, 100% pour 3v3
        min_availability = 1.0 if format_type == "3v3" else 0.6
        
        if availability >= min_availability:
            result.append({
                **counter,
                "roster_availability": availability,
                "all_members_ready": availability == 1.0,
                "missing": missing,
                "composite_score": counter.get("win_pct", 0) * availability,
            })
    
    result.sort(key=lambda c: c.get("composite_score", 0), reverse=True)
    
    dedup = []
    seen = set()
    for c in result:
        if c["atk_leader_id"] not in seen:
            seen.add(c["atk_leader_id"])
            dedup.append(c)
            
    return dedup

async def get_best_counter_with_memory(def_leader_id: str, def_members_ids: list[str], format_type: str, my_roster_index: dict, excluded_chars: set = None) -> list[dict]:
    """
    Sélectionne les meilleurs counters en intégrant l'historique de feedback.
    """
    counters = await get_counters_from_db(def_leader_id, format_type)
    
    # -------------------------------------------------------------
    # Filtrage par composition exacte de l'ennemi (si on a les membres)
    # -------------------------------------------------------------
    if def_members_ids:
        def_set = set(m.upper() for m in def_members_ids)
        filtered_by_def = []
        for c in counters:
            c_def_set = set(m.upper() for m in c.get("def_members_ids", []))
            
            # On cherche une correspondance stricte ou quasi-stricte (tolérance d'1 perso différent)
            # Car les stats swgoh.gg peuvent lister plusieurs variations
            if len(def_set.intersection(c_def_set)) >= max(1, len(def_set) - 1):
                filtered_by_def.append(c)
                
        # S'il a trouvé des counters spécifiques à CETTE équipe exacte, on les priorise
        if filtered_by_def:
            counters = filtered_by_def
    # -------------------------------------------------------------
    
    for counter in counters:
        feedback = await get_counter_feedback_stats(counter["atk_leader_id"], def_leader_id, format_type)
        counter["feedback_wins"] = feedback["wins"]
        counter["feedback_total"] = feedback["total"]
        counter["feedback_win_rate"] = feedback["win_rate"]
        
        swgoh_score = counter.get("win_pct", 0) / 100
        feedback_score = counter["feedback_win_rate"] if counter["feedback_win_rate"] is not None else swgoh_score
        confidence_weight = min(feedback["total"] / 10, 0.5)
        
        counter["final_score"] = (swgoh_score * (1 - confidence_weight) + feedback_score * confidence_weight)
    
    if excluded_chars:
        counters = [
            c for c in counters
            if not set([c["atk_leader_id"]] + c["atk_members_ids"]).intersection(excluded_chars)
        ]
        
    filtered = filter_counters_by_roster(counters, my_roster_index, format_type)
    
    # Recalculate composite_score using final_score
    for c in filtered:
        c["composite_score"] = c["final_score"] * c["roster_availability"]
        
    filtered.sort(key=lambda c: c["composite_score"], reverse=True)
    return filtered
