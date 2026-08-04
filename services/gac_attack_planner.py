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

# Personnages ou leaders capables de battre des défenses même avec un fort déficit de reliques (Relic Delta négatif)
HARD_COUNTERS_BYPASS_DELTA = {
    "WAMPA", "SAVAGEOPRESS", "DARTHBANE"
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


# Leaders/Unités dont le Zéta est absolument indispensable pour l'efficacité du contre
ZETA_DEPENDENT_LEADERS = {
    "COMMANDERLUKESKYWALKER", "JEDIKNIGHTREVAN", "VEERS", "BOSSK", "DARTHTRAYA",
    "EMPERORPALPATINE", "SUPREMELEADERKYLOREN", "SITHPALPATINE", "IDENVERSIOEMPIRE",
    "GENERALHUX", "FINN", "PADMEAMIDALA", "MOTHERTALZIN", "GARSAXON", "MANDALORIAN",
    "GREEFCARGA", "GEONOSIANBROODALPHA", "HEROAMIRAL", "JEDIMASTERKENOBI", "MARAJADE", "JANGOFETT"
}

def filter_counters_by_roster(
    counters: list[dict], 
    my_roster_index: dict, 
    format_type: str, 
    league: str = "KYBER",
    enemy_roster_index: dict = None,
) -> list[dict]:

    """
    Filtre et enrichit les counters selon le roster du joueur.

    Prend en compte le Relic Delta et les Zétas/Omicrons vitaux pour garantir
    des propositions de contres fiables avec un DPS suffisant.
    """
    thresh = LEAGUE_THRESHOLDS.get(league.upper(), LEAGUE_THRESHOLDS["KYBER"])
    min_gear             = thresh["min_gear"]
    min_rarity           = thresh["min_rarity"]
    require_g12_or_relic = thresh["require_g12_or_relic"]

    result = []
    
    for counter in counters:
        max_atk_members = 2 if format_type == "3v3" else 4
        all_ids = [counter["atk_leader_id"]] + counter.get("atk_members_ids", [])[:max_atk_members]
        
        # ── Calcul préalable de la puissance relique ennemie ──────────────
        def_ids = [counter.get("def_leader_id")] + counter.get("def_members_ids", [])
        def_relics = []
        if enemy_roster_index:
            for duid in def_ids:
                if duid and duid.upper() in enemy_roster_index:
                    def_relics.append(enemy_roster_index[duid.upper()].get("relic_tier", 0))
        def_relic_avg = (sum(def_relics) / max(len(def_relics), 1)) if def_relics else 3.0

        available = []       # Possédés ET prêts (seuils league)
        owned_not_ready = [] # Possédés mais pas encore au niveau requis
        missing = []         # Complètement non possédés ou incompatibles → éliminatoire
        missing_omicron = []
        missing_zeta = []
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
            has_omi = unit.get("has_omicron") or unit.get("omicrons", 0) > 0
            z_count = unit.get("zetas", 0)

            # ── Règle absolue 100% Reliques contre défenses Reliques ──────────
            # Si l'adversaire a des reliques (def_relic_avg >= 1.0), interdire strictement
            # tout membre d'attaque non-relique (r_tier == 0 / G12) sauf s'il s'agit d'un hard solo (Wampa/Bane)
            is_hard_counter = unit_id.upper() in HARD_COUNTERS_BYPASS_DELTA or counter.get("atk_leader_id", "").upper() in HARD_COUNTERS_BYPASS_DELTA
            if def_relic_avg >= 1.0 and r_tier == 0 and not is_hard_counter:
                missing.append(unit_id)
                continue

            # ── Règle anti-perso "Pas Monté" (Niveau 1 / Gear très bas) ───────
            min_playable_gear = max(6, min_gear - 2) if not require_g12_or_relic else 9
            is_unbuilt = (r_tier == 0) and (g_tier < min_playable_gear or level < 60) and not has_omi

            if is_unbuilt:
                missing.append(unit_id)
                continue

            # ── Logique de disponibilité adaptée par étoiles, omicrons & league ─
            meets_rarity = rarity >= min_rarity
            max_relic_for_rarity = MAX_RELIC_BY_RARITY.get(rarity, 0)
            has_relic = r_tier >= 1
            at_relic_cap = has_relic and (rarity < 7) and (r_tier >= max_relic_for_rarity)
            is_7star = rarity == 7

            if require_g12_or_relic:
                if has_relic or has_omi:
                    unit_ready = meets_rarity or at_relic_cap or has_omi
                elif is_7star:
                    unit_ready = g_tier >= min_gear
                else:
                    unit_ready = False
            else:
                unit_ready = (rarity >= min_rarity) and (g_tier >= min_gear or has_relic or has_omi)

            # Vérification si le leader/membre a 0 Zéta alors qu'il est zéta-dépendant
            if unit_id.upper() in ZETA_DEPENDENT_LEADERS and z_count == 0:
                missing_zeta.append(unit_id)

            if unit_ready:
                available.append(unit_id)
                roster_power += (r_tier * 10) + g_tier
                if unit_id.upper() in NEEDS_GAC_OMICRON and not has_omi:
                    missing_omicron.append(unit_id)
            else:
                owned_not_ready.append(unit_id)
                roster_power += g_tier

        # ── Règle absolue : aucun perso non-possédé ni Zéta essentiel manquant ──
        if missing or missing_zeta:
            continue

        # Une équipe avec des Zétas essentiels manquants n'est PAS considérée 100% prête
        all_ready    = len(owned_not_ready) == 0 and len(missing_zeta) == 0
        availability = len(available) / max(len(all_ids), 1)

        # ── Calcul du Relic Delta (Attaque vs Défense) ──────────────────────
        atk_relics = [my_roster_index.get(uid.upper(), {}).get("relic_tier", 0) for uid in all_ids if my_roster_index.get(uid.upper())]
        atk_relic_avg = sum(atk_relics) / max(len(atk_relics), 1)


        relic_delta = atk_relic_avg - def_relic_avg
        is_hard_counter = counter.get("atk_leader_id", "").upper() in HARD_COUNTERS_BYPASS_DELTA

        relic_delta_score = 0 if (is_hard_counter or relic_delta >= 0) else (relic_delta * 5)

        win_pct     = counter.get("win_pct", 0)
        final_score = counter.get("final_score", win_pct / 100 if win_pct > 1 else win_pct)
        
        # Pénalité si zéta vital manquant (ex: Mando 0 zéta)
        if missing_zeta:
            final_score *= 0.5

        # ── Règle absolue anti-perso G12 contre défense Relique ─────────────
        # Si une équipe contient encore un membre non-relique (G12) face à une défense relique (def_relic_avg >= 1),
        # disqualifier la préparation de l'équipe (all_ready = False) pour forcer le bot à piocher une AUTRE équipe 100% Relique.
        has_unsubbed_g12 = any(my_roster_index.get(uid.upper(), {}).get("relic_tier", 0) == 0 for uid in all_ids)
        is_hard_counter = counter.get("atk_leader_id", "").upper() in HARD_COUNTERS_BYPASS_DELTA

        if has_unsubbed_g12 and def_relic_avg >= 1.0 and not is_hard_counter:
            all_ready = False
            final_score *= 0.1

        result.append({
            **counter,
            "roster_availability": availability,
            "all_members_ready":   all_ready,
            "all_members_owned":   True,
            "roster_power":        roster_power,
            "relic_delta":          relic_delta,
            "relic_delta_score":    relic_delta_score,
            "missing":             owned_not_ready,
            "missing_omicron":     missing_omicron,
            "missing_zeta":        missing_zeta,
            "needs_omicron":       len(missing_omicron) > 0,
            "composite_score":     final_score * (1.5 if all_ready else availability),
        })

    result.sort(key=lambda c: (
        1 if c["all_members_ready"] else 0,
        1 if c.get("win_pct", 0) >= 80 else (1 if c.get("win_pct", 0) >= 50 else 0),
        c.get("relic_delta_score", 0),
        c["roster_power"],
        c.get("final_score", 0),
        c.get("is_def_match", 0),
        c["roster_availability"],
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



# Dictionnaire de secours des contres méta universels (Hard Counters & Solos reconnus)
UNIVERSAL_META_COUNTERS = {
    "DARTHSIDIOUS": [
        {"def_leader_id": "DARTHSIDIOUS", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 98.0, "seen": 900, "avg_banners": 63.0},
        {"def_leader_id": "DARTHSIDIOUS", "def_members_ids": [], "atk_leader_id": "COMMANDERLUKESKYWALKER", "atk_members_ids": ["HANSOLO", "CHEWBACCA"], "win_pct": 96.0, "seen": 1100, "avg_banners": 56.0},
        {"def_leader_id": "DARTHSIDIOUS", "def_members_ids": [], "atk_leader_id": "SITHPALPATINE", "atk_members_ids": [], "win_pct": 99.0, "seen": 700, "avg_banners": 64.0},
        {"def_leader_id": "DARTHSIDIOUS", "def_members_ids": [], "atk_leader_id": "SUPREMELEADERKYLOREN", "atk_members_ids": [], "win_pct": 98.0, "seen": 800, "avg_banners": 63.0},
    ],
    "SIDIOUS": [
        {"def_leader_id": "SIDIOUS", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 98.0, "seen": 900, "avg_banners": 63.0},
    ],
    "DARTHNIHILUS": [
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "BOSSK", "atk_members_ids": ["BOBAFETT", "MANDALORIAN"], "win_pct": 95.0, "seen": 800, "avg_banners": 56.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "COMMANDERLUKESKYWALKER", "atk_members_ids": ["HANSOLO", "CHEWBACCA"], "win_pct": 96.0, "seen": 1000, "avg_banners": 56.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "VEERS", "atk_members_ids": ["ADMIRALPIETT", "DARKTROOPER"], "win_pct": 97.0, "seen": 900, "avg_banners": 58.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "CAPTAINREX", "atk_members_ids": ["CT7567", "CT210408"], "win_pct": 95.0, "seen": 700, "avg_banners": 57.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "JEDIKNIGHTREVAN", "atk_members_ids": ["GRANDMASTERYODA", "JOLEEBINDO"], "win_pct": 94.0, "seen": 850, "avg_banners": 54.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "DARTHVADER", "atk_members_ids": [], "win_pct": 95.0, "seen": 600, "avg_banners": 62.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "SUPREMELEADERKYLOREN", "atk_members_ids": [], "win_pct": 99.0, "seen": 800, "avg_banners": 63.0},
    ],
    "NIHILUS": [
        {"def_leader_id": "NIHILUS", "def_members_ids": [], "atk_leader_id": "BOSSK", "atk_members_ids": ["BOBAFETT", "MANDALORIAN"], "win_pct": 95.0, "seen": 800, "avg_banners": 56.0},
    ],
    "DARTHTRAYA": [
        {"def_leader_id": "DARTHTRAYA", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 92.0, "seen": 800, "avg_banners": 62.0},
        {"def_leader_id": "DARTHTRAYA", "def_members_ids": [], "atk_leader_id": "COMMANDERLUKESKYWALKER", "atk_members_ids": ["HANSOLO", "CHEWBACCA"], "win_pct": 95.0, "seen": 1200, "avg_banners": 55.0},
        {"def_leader_id": "DARTHTRAYA", "def_members_ids": [], "atk_leader_id": "SITHPALPATINE", "atk_members_ids": [], "win_pct": 98.0, "seen": 800, "avg_banners": 64.0},
        {"def_leader_id": "DARTHTRAYA", "def_members_ids": [], "atk_leader_id": "SUPREMELEADERKYLOREN", "atk_members_ids": [], "win_pct": 97.0, "seen": 700, "avg_banners": 63.0},
        {"def_leader_id": "DARTHTRAYA", "def_members_ids": [], "atk_leader_id": "JEDIKNIGHTREVAN", "atk_members_ids": ["GRANDMASTERYODA", "JOLEEBINDO"], "win_pct": 91.0, "seen": 600, "avg_banners": 54.0},
        {"def_leader_id": "DARTHTRAYA", "def_members_ids": [], "atk_leader_id": "STARKILLER", "atk_members_ids": ["MARAJADE", "VISASMARR"], "win_pct": 94.0, "seen": 500, "avg_banners": 58.0},
        {"def_leader_id": "DARTHTRAYA", "def_members_ids": [], "atk_leader_id": "DARTHBANE", "atk_members_ids": [], "win_pct": 99.0, "seen": 600, "avg_banners": 65.0},
    ],
    "DARTHNIHILUS": [
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "DARTHVADER", "atk_members_ids": ["EMPERORPALPATINE", "MARAJADE"], "win_pct": 95.0, "seen": 900, "avg_banners": 57.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "JEDIKNIGHTREVAN", "atk_members_ids": ["GRANDMASTERYODA", "JOLEEBINDO"], "win_pct": 94.0, "seen": 800, "avg_banners": 55.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "COMMANDERLUKESKYWALKER", "atk_members_ids": ["HANSOLO", "CHEWBACCA"], "win_pct": 96.0, "seen": 1000, "avg_banners": 56.0},
        {"def_leader_id": "DARTHNIHILUS", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 90.0, "seen": 400, "avg_banners": 61.0},
    ],
    "NIGHTSISTERMOTHER": [
        {"def_leader_id": "NIGHTSISTERMOTHER", "def_members_ids": [], "atk_leader_id": "VEERS", "atk_members_ids": ["ADMIRALPIETT", "DARKTROOPER"], "win_pct": 96.0, "seen": 1500, "avg_banners": 56.0},
        {"def_leader_id": "NIGHTSISTERMOTHER", "def_members_ids": [], "atk_leader_id": "SUPREMELEADERKYLOREN", "atk_members_ids": [], "win_pct": 99.0, "seen": 800, "avg_banners": 64.0},
        {"def_leader_id": "NIGHTSISTERMOTHER", "def_members_ids": [], "atk_leader_id": "DARTHVADER", "atk_members_ids": ["EMPERORPALPATINE", "MARAJADE"], "win_pct": 91.0, "seen": 900, "avg_banners": 55.0},
    ],
    "BOSSK": [
        {"def_leader_id": "BOSSK", "def_members_ids": [], "atk_leader_id": "DARTHVADER", "atk_members_ids": ["EMPERORPALPATINE", "GRANDMOFFTARKIN"], "win_pct": 95.0, "seen": 1800, "avg_banners": 57.0},
        {"def_leader_id": "BOSSK", "def_members_ids": [], "atk_leader_id": "NEST", "atk_members_ids": [], "win_pct": 93.0, "seen": 700, "avg_banners": 62.0},
        {"def_leader_id": "BOSSK", "def_members_ids": [], "atk_leader_id": "IDENVERSIOEMPIRE", "atk_members_ids": ["DEATHTROOPER", "STORMTROOPER"], "win_pct": 94.0, "seen": 900, "avg_banners": 58.0},
        {"def_leader_id": "BOSSK", "def_members_ids": [], "atk_leader_id": "GREEFCARGA", "atk_members_ids": ["MANDALORIAN", "CARADUNE"], "win_pct": 94.0, "seen": 1500, "avg_banners": 54.0},
        {"def_leader_id": "BOSSK", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 88.0, "seen": 400, "avg_banners": 61.0},
        {"def_leader_id": "BOSSK", "def_members_ids": [], "atk_leader_id": "BADBATCHHUNTER", "atk_members_ids": ["BADBATCHTECH", "BADBATCHECHO"], "win_pct": 96.0, "seen": 900, "avg_banners": 56.0},
    ],
    "NUTEGUNRAY": [
        {"def_leader_id": "NUTEGUNRAY", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 95.0, "seen": 800, "avg_banners": 63.0},
        {"def_leader_id": "NUTEGUNRAY", "def_members_ids": [], "atk_leader_id": "IDENVERSIOEMPIRE", "atk_members_ids": ["DEATHTROOPER", "STORMTROOPER"], "win_pct": 96.0, "seen": 1100, "avg_banners": 58.0},
    ],
    "GRIEVOUS": [
        {"def_leader_id": "GRIEVOUS", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 91.0, "seen": 1000, "avg_banners": 61.0},
        {"def_leader_id": "GRIEVOUS", "def_members_ids": [], "atk_leader_id": "COMMANDERLUKESKYWALKER", "atk_members_ids": ["HANSOLO", "CHEWBACCA"], "win_pct": 94.0, "seen": 1800, "avg_banners": 54.0},
    ],
    "GEONOSIANBROODALPHA": [
        {"def_leader_id": "GEONOSIANBROODALPHA", "def_members_ids": [], "atk_leader_id": "DARTHVADER", "atk_members_ids": ["GRANDMOFFTARKIN", "EMPERORPALPATINE"], "win_pct": 98.0, "seen": 3500, "avg_banners": 57.0},
        {"def_leader_id": "GEONOSIANBROODALPHA", "def_members_ids": [], "atk_leader_id": "NEST", "atk_members_ids": [], "win_pct": 93.0, "seen": 900, "avg_banners": 62.0},
    ],
    "MONMOTHMA": [
        {"def_leader_id": "MONMOTHMA", "def_members_ids": [], "atk_leader_id": "NEST", "atk_members_ids": [], "win_pct": 94.0, "seen": 800, "avg_banners": 62.0},
        {"def_leader_id": "MONMOTHMA", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 90.0, "seen": 400, "avg_banners": 60.0},
    ],
    "QIRA": [
        {"def_leader_id": "QIRA", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 96.0, "seen": 500, "avg_banners": 63.0},
    ],
    "CARTHONASI": [
        {"def_leader_id": "CARTHONASI", "def_members_ids": [], "atk_leader_id": "WAMPA", "atk_members_ids": [], "win_pct": 98.0, "seen": 600, "avg_banners": 64.0},
    ],
}

async def get_best_counter_with_memory(
    def_leader_id: str, 
    def_members_ids: list[str], 
    format_type: str, 
    my_roster_index: dict, 
    excluded_chars: set = None,
    league: str = "KYBER",
    enemy_roster_index: dict = None,
) -> list[dict]:
    """
    Sélectionne les meilleurs counters en intégrant l'historique de feedback et le roster du joueur.
    """
    counters = await get_counters_from_db(def_leader_id, format_type)
    
    # ── Fusion avec la base de connaissances méta universelles ─────────────
    univ_counters = UNIVERSAL_META_COUNTERS.get(def_leader_id.upper(), [])
    if univ_counters:
        for uc in univ_counters:
            found = False
            for c in counters:
                if c["atk_leader_id"].upper() == uc["atk_leader_id"].upper():
                    found = True
                    if c.get("win_pct", 0) < uc.get("win_pct", 90.0):
                        c["win_pct"] = uc.get("win_pct", 92.0)
                        c["seen"] = max(c.get("seen", 0), uc.get("seen", 100))
                        c["avg_banners"] = max(c.get("avg_banners", 0), uc.get("avg_banners", 60.0))
                    break
            if not found:
                max_m = 2 if format_type == "3v3" else 4
                counters.append({
                    "season_id": "meta",
                    "def_leader_id": def_leader_id,
                    "def_members_ids": [],
                    "atk_leader_id": uc["atk_leader_id"],
                    "atk_members_ids": uc.get("atk_members_ids", [])[:max_m],
                    "seen": uc.get("seen", 100),
                    "win_pct": uc.get("win_pct", 92.0),
                    "avg_banners": uc.get("avg_banners", 60.0)
                })

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
        
    filtered = filter_counters_by_roster(counters, my_roster_index, format_type, league=league, enemy_roster_index=enemy_roster_index)
    
    # ── Fallback progressif si aucun contre strict n'est trouvé pour le roster ──────
    if not filtered and league.upper() not in ["BRONZIUM", "CARBONITE"]:
        log.info(f"Aucun contre strict en {league} pour {def_leader_id}, tentative de fallback Bronzium...")
        filtered = filter_counters_by_roster(counters, my_roster_index, format_type, league="BRONZIUM", enemy_roster_index=enemy_roster_index)
        
    if not filtered and league.upper() != "CARBONITE":
        log.info(f"Tentative de fallback Carbonite pour {def_leader_id}...")
        filtered = filter_counters_by_roster(counters, my_roster_index, format_type, league="CARBONITE", enemy_roster_index=enemy_roster_index)
        
    return filtered
