"""
services/gac_attack_planner.py
Planification et filtrage des counters.
"""
import logging
from database.db import get_counters_from_db, get_counter_feedback_stats

log = logging.getLogger(__name__)


# Personnages dont l'Omicron GAC est indispensable pour leur efficacité.
# Si le joueur n'a pas activé leur omicron, un badge ⚠️ s'affiche sur le counter.
NEEDS_GAC_OMICRON = {
    "WAMPA", "SAVAGEOPRESS", "QUIGONJINN", "IDENVERSIOEMPIRE", 
    "CAPTAINREX", "DARTHTRAYA", "ZAMWESELL", "ZORIIBLISS", "DASHRENDAR"
}

def filter_counters_by_roster(
    counters: list[dict], 
    my_roster_index: dict, 
    format_type: str, 
    min_relic: int = 0, 
    min_gear: int = 12
) -> list[dict]:
    """
    Filtre et enrichit les counters selon le roster du joueur.
    Classe les équipes 100% complètes en priorité absolue,
    puis par niveau de relique/gear des personnages du joueur, puis par win rate.
    """
    result = []
    
    for counter in counters:
        max_atk_members = 2 if format_type == "3v3" else 4
        all_ids = [counter["atk_leader_id"]] + counter.get("atk_members_ids", [])[:max_atk_members]
        
        available = []
        missing = []
        missing_omicron = []  # Personnages présents mais sans leur omicron GAC
        roster_power = 0
        
        for unit_id in all_ids:
            unit = my_roster_index.get(unit_id.upper())
            r_tier = unit.get("relic_tier", 0) if unit else 0
            g_tier = unit.get("gear_tier", 0) if unit else 0
            rarity = unit.get("rarity", 0) if unit else 0
            
            # Une unité n'est prête que si elle a 7 étoiles ET (au moins Relique 1+ OU Gear 12+)
            unit_ready = False
            if unit and rarity == 7:
                if r_tier > 0:
                    unit_ready = (min_relic <= 0 or r_tier >= min_relic)
                else:
                    unit_ready = (g_tier >= min_gear)
            
            if unit_ready:
                available.append(unit_id)
                # Score de puissance basé sur le niveau réel du joueur
                roster_power += (r_tier * 10) + g_tier
                
                # Vérifier si ce personnage a besoin d'un omicron GAC
                if unit_id.upper() in NEEDS_GAC_OMICRON and not (unit.get("has_omicron") or unit.get("omicrons", 0) > 0):
                    missing_omicron.append(unit_id)
            else:
                missing.append(unit_id)

        
        availability = len(available) / max(len(all_ids), 1)
        all_ready = (len(available) == len(all_ids))
        
        # On demande au moins 50% de présence, mais les équipes incomplètes passeront toujours APRES les complètes
        if availability >= 0.5:
            win_pct = counter.get("win_pct", 0)
            final_score = counter.get("final_score", win_pct / 100 if win_pct > 1 else win_pct)
            
            result.append({
                **counter,
                "roster_availability": availability,
                "all_members_ready": all_ready,
                "roster_power": roster_power,
                "missing": missing,
                "missing_omicron": missing_omicron,
                "needs_omicron": len(missing_omicron) > 0,
                "composite_score": final_score * (1.5 if all_ready else availability),
            })
    
    # Si au moins un contre est 100% prêt, on ne garde QUE les contres 100% prêts !
    complete_results = [c for c in result if c["all_members_ready"]]
    if complete_results:
        result = complete_results

    # Tri multi-critères :
    # 1. Équipes 100% complètes en PREMIER
    # 2. Correspondance compo ennemie exacte
    # 3. Disponibilité du roster
    # 4. Puissance des persos du joueur (persos les plus montés)
    # 5. Score final (win rate / feedback)
    result.sort(key=lambda c: (
        1 if c["all_members_ready"] else 0,
        c.get("is_def_match", 0),
        c["roster_availability"],
        c["roster_power"],
        c.get("final_score", 0),
    ), reverse=True)
    
    # Déduplication par leader d'attaque : conserve la MEILLEURE compo pour ce leader
    dedup = []
    seen_leaders = set()
    for c in result:
        if c["atk_leader_id"] not in seen_leaders:
            seen_leaders.add(c["atk_leader_id"])
            dedup.append(c)
            
    return dedup


async def get_best_counter_with_memory(
    def_leader_id: str, 
    def_members_ids: list[str], 
    format_type: str, 
    my_roster_index: dict, 
    excluded_chars: set = None
) -> list[dict]:
    """
    Sélectionne les meilleurs counters en intégrant l'historique de feedback et le roster du joueur.
    """
    counters = await get_counters_from_db(def_leader_id, format_type)
    if not counters:
        return []
    
    # -------------------------------------------------------------
    # Évaluation de la correspondance de la défense
    # (Bonus aux contres spécifiques, mais SANS supprimer les autres contres)
    # -------------------------------------------------------------
    def_set = set(m.upper() for m in def_members_ids) if def_members_ids else set()
    for counter in counters:
        c_def_set = set(m.upper() for m in counter.get("def_members_ids", []))
        if def_set and len(def_set.intersection(c_def_set)) >= max(1, len(def_set) - 1):
            counter["is_def_match"] = 1
        else:
            counter["is_def_match"] = 0
            
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
    return filtered

