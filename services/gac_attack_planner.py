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

# Relic max accessible selon le nombre d'étoiles du personnage
# (en dessous de 7★, le relic max est limité mais le perso EST utilisable en GAC)
MAX_RELIC_BY_RARITY = {
    7: 9,   # 7★ : R1 → R9 (aucune limite)
    6: 5,   # 6★ : R1 → R5
    5: 4,   # 5★ : R1 → R4
    4: 3,   # 4★ : R1 → R3
    3: 2,   # 3★ : R1 → R2
    2: 1,   # 2★ : R1
    1: 0,   # 1★ : pas de relic
}

# Seuils d'aptitude au combat adaptés par ligue.
# min_gear   : niveau de gear minimum pour être considéré "utilisable"
# min_rarity : nombre d'étoiles minimum (0 = toutes acceptées si relic présent)
# require_relic_or_g12 : True = exige G12 OU Relic (désactivé pour les petits comptes)
LEAGUE_THRESHOLDS = {
    "CARBONITE": {"min_gear": 6,  "min_rarity": 4, "require_g12_or_relic": False},
    "BRONZIUM":  {"min_gear": 8,  "min_rarity": 5, "require_g12_or_relic": False},
    "CHROMIUM":  {"min_gear": 10, "min_rarity": 6, "require_g12_or_relic": True },
    "AURODIUM":  {"min_gear": 12, "min_rarity": 7, "require_g12_or_relic": True },
    "KYBER":     {"min_gear": 12, "min_rarity": 7, "require_g12_or_relic": True },
}

def filter_counters_by_roster(
    counters: list[dict], 
    my_roster_index: dict, 
    format_type: str, 
    league: str = "KYBER",
) -> list[dict]:
    """
    Filtre et enrichit les counters selon le roster du joueur.

    Règle absolue : un contre qui nécessite un personnage NON POSSÉDÉ est
    immédiatement éliminé — peu importe le win rate ou la disponibilité.

    Niveaux de priorité (du plus élevé au plus bas) :
      1. Tous les membres sont prêts (seuils league) → priorité absolue
      2. Tous les membres sont possédés mais certains pas encore au niveau requis
      3. Fallback (seulement si rien de mieux)

    Particularités :
    - Un perso 6★ à R5 EST considéré prêt (il est à son relic max).
    - Les seuils varient selon la ligue (Carbonite très permissif, Kyber strict).
    """
    thresh = LEAGUE_THRESHOLDS.get(league.upper(), LEAGUE_THRESHOLDS["KYBER"])
    min_gear             = thresh["min_gear"]
    min_rarity           = thresh["min_rarity"]
    require_g12_or_relic = thresh["require_g12_or_relic"]

    result = []
    
    for counter in counters:
        max_atk_members = 2 if format_type == "3v3" else 4
        all_ids = [counter["atk_leader_id"]] + counter.get("atk_members_ids", [])[:max_atk_members]
        
        available = []       # Possédés ET prêts (seuils league)
        owned_not_ready = [] # Possédés mais pas encore au niveau requis
        missing = []         # Complètement non possédés → éliminatoire
        missing_omicron = []
        roster_power = 0

        for unit_id in all_ids:
            unit = my_roster_index.get(unit_id.upper())

            if unit is None:
                missing.append(unit_id)
                continue

            r_tier = unit.get("relic_tier", 0)
            g_tier = unit.get("gear_tier", 0)
            rarity = unit.get("rarity", 0)
            level  = unit.get("level", 85)

            # ── Règle anti-perso "Pas Monté" (Niveau 1 / Gear très bas) ───────
            # Un personnage non-relique avec un Gear < min_playable_gear ou Level < 60
            # n'est pas utilisable en combat -> éliminatoire pour l'équipe
            min_playable_gear = max(6, min_gear - 2) if not require_g12_or_relic else 9
            is_unbuilt = (r_tier == 0) and (g_tier < min_playable_gear or level < 60)

            if is_unbuilt:
                missing.append(unit_id)
                continue

            # ── Logique de disponibilité adaptée par étoiles + league ─────────
            # Rarity minimale selon la league
            meets_rarity = rarity >= min_rarity

            # Un perso AVEC RELIC est utilisable même sans 7★,
            # tant qu'il est à son relic max (ex: 6★ à R5 = cap)
            max_relic_for_rarity = MAX_RELIC_BY_RARITY.get(rarity, 0)
            has_relic = r_tier >= 1
            at_relic_cap = has_relic and (rarity < 7) and (r_tier >= max_relic_for_rarity)
            is_7star = rarity == 7

            if require_g12_or_relic:
                # Ligues élevées : exige G12+ OU Relic
                # Exception : perso < 7★ mais à son relic max = accepté
                if has_relic:
                    # Perso Relic : toujours accepté (même < 7★ si à son cap)
                    unit_ready = meets_rarity or at_relic_cap
                elif is_7star:
                    unit_ready = g_tier >= min_gear
                else:
                    # < 7★ sans relic dans une haute ligue = pas prêt
                    unit_ready = False
            else:
                # Ligues basses (Carbonite/Bronzium) : gear minimum suffit
                unit_ready = (rarity >= min_rarity) and (g_tier >= min_gear or has_relic)

            if unit_ready:
                available.append(unit_id)
                roster_power += (r_tier * 10) + g_tier
                if unit_id.upper() in NEEDS_GAC_OMICRON and not (
                    unit.get("has_omicron") or unit.get("omicrons", 0) > 0
                ):
                    missing_omicron.append(unit_id)
            else:
                owned_not_ready.append(unit_id)
                roster_power += g_tier

        # ── Règle absolue : aucun perso non-possédé toléré ──────────────────
        if missing:
            continue

        all_ready    = len(owned_not_ready) == 0
        availability = len(available) / max(len(all_ids), 1)

        win_pct     = counter.get("win_pct", 0)
        final_score = counter.get("final_score", win_pct / 100 if win_pct > 1 else win_pct)

        result.append({
            **counter,
            "roster_availability": availability,
            "all_members_ready":   all_ready,
            "all_members_owned":   True,
            "roster_power":        roster_power,
            "missing":             owned_not_ready,
            "missing_omicron":     missing_omicron,
            "needs_omicron":       len(missing_omicron) > 0,
            "composite_score":     final_score * (1.5 if all_ready else availability),
        })

    # Priorité aux équipes 100% prêtes selon les seuils de la ligue
    complete_results = [c for c in result if c["all_members_ready"]]
    if complete_results:
        result = complete_results

    result.sort(key=lambda c: (
        1 if c["all_members_ready"] else 0,
        c.get("is_def_match", 0),
        c["roster_availability"],
        c["roster_power"],
        c.get("final_score", 0),
    ), reverse=True)

    dedup = []
    seen_leaders = set()
    for c in result:
        if c["atk_leader_id"] not in seen_leaders:
            seen_leaders.add(c["atk_leader_id"])
            dedup.append(c)

    has_positive_winrate = any(c.get("win_pct", 0) > 0 for c in dedup)
    if has_positive_winrate:
        dedup = [c for c in dedup if c.get("win_pct", 0) > 0]

    return dedup


async def get_best_counter_with_memory(
    def_leader_id: str, 
    def_members_ids: list[str], 
    format_type: str, 
    my_roster_index: dict, 
    excluded_chars: set = None,
    league: str = "KYBER",
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
        
    filtered = filter_counters_by_roster(counters, my_roster_index, format_type, league=league)
    
    # ── Fallback progressif si aucun contre strict n'est trouvé pour le roster ──────
    if not filtered and league.upper() not in ["BRONZIUM", "CARBONITE"]:
        log.info(f"Aucun contre strict en {league} pour {def_leader_id}, tentative de fallback Bronzium...")
        filtered = filter_counters_by_roster(counters, my_roster_index, format_type, league="BRONZIUM")
        
    if not filtered and league.upper() != "CARBONITE":
        log.info(f"Tentative de fallback Carbonite pour {def_leader_id}...")
        filtered = filter_counters_by_roster(counters, my_roster_index, format_type, league="CARBONITE")
        
    return filtered
