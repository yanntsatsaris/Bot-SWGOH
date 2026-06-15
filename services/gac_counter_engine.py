"""
services/gac_counter_engine.py — Moteur d'analyse et de suggestions de contres GAC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Logique :
  1. Récupère le roster ennemi via Comlink
  2. Détecte les équipes méta que l'ennemi peut aligner (relic R5+ ou G13+)
  3. Pour chaque équipe détectée, cherche des contres dans meta_teams
  4. Filtre les contres que le joueur demandeur possède lui-même
"""
from __future__ import annotations

import json
import logging

from services.comlink import get_player_roster
from services.unit_names import get_name
from database.db import get_db

log = logging.getLogger(__name__)

# Seuils minimaux pour considérer qu'une unité est "prête pour le GAC"
_MIN_RELIC = 5   # Relic 5+
_MIN_GEAR  = 13  # ou Gear 13 (sans relic)

# Équipes méta codées en dur pour les cas où la BDD est vide.
# Format : leader_base_id → liste de base_id membres
_HARDCODED_META: dict[str, list[str]] = {
    "SITHPALPATINE":        ["SITHPALPATINE", "DARTHVADER", "MARAJADE", "DARTHNIHILUS", "ROYALGUARD"],
    "LORDVADER":            ["LORDVADER", "MARAJADE", "DARTHVADER", "ROYALGUARD", "DARTHNIHILUS"],
    "JABBATHEHUTT":         ["JABBATHEHUTT", "BOBAFETTSCION", "KRRSANTAN", "GAMORREANGUARD", "SKIFFGUARD"],
    "SUPREMELEADERKYLOREN": ["SUPREMELEADERKYLOREN", "KYLORENUNMASKED", "GENERALHUX", "FIRSTORDERTIEPILOT", "FIRSTORDERSFTFIGHTER"],
    "JEDIMASTERKENOBI":     ["JEDIMASTERKENOBI", "PADMEAMIDALA", "GENERALSKYWALKER", "AHSOKATANO", "SHAAKTI"],
    "MOTHERTALZIN":         ["MOTHERTALZIN", "ASAJVENTRESS", "ZOMBIESISTER", "NIGHTSISTERINIT", "TALIA"],
    "GENERALGRIEVOUS":      ["GENERALGRIEVOUS", "DROIDEKA", "B1BATTLEDROIDV2", "MAGNAGUARD", "NUTE"],
    # 3v3
    "BOBAFETT":             ["BOBAFETT", "JANGOFETT", "DENGAR"],
    "BASTILLASHAN":         ["BASTILLASHAN", "DARTHREVAN", "BASTILLASHANDARK"],
}

# Contres hardcodés : leader_base_id adverse → liste de leaders qui les contrent
_HARDCODED_COUNTERS: dict[str, list[str]] = {
    "SITHPALPATINE":        ["JEDIMASTERKENOBI", "PADMEAMIDALA", "GENERALSKYWALKER"],
    "LORDVADER":            ["JABBATHEHUTT", "SUPREMELEADERKYLOREN"],
    "JABBATHEHUTT":         ["LORDVADER", "SITHPALPATINE"],
    "SUPREMELEADERKYLOREN": ["SITHPALPATINE", "JEDIMASTERKENOBI"],
    "JEDIMASTERKENOBI":     ["LORDVADER", "SITHPALPATINE"],
    "MOTHERTALZIN":         ["JEDIMASTERKENOBI", "SITHPALPATINE"],
    "GENERALGRIEVOUS":      ["PADMEAMIDALA", "GENERALSKYWALKER"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_gac_ready(unit: dict) -> bool:
    """Retourne True si l'unité est assez puissante pour le GAC."""
    relic = unit.get("relic_tier", 0)
    gear  = unit.get("gear_tier", 0)
    return relic >= _MIN_RELIC or gear >= _MIN_GEAR


def _build_roster_index(roster: list[dict]) -> dict[str, dict]:
    """Indexe le roster par base_id pour un accès O(1)."""
    return {u["base_id"].upper(): u for u in roster}


def _detect_enemy_meta_teams(
    enemy_index: dict[str, dict],
    fmt: str,
) -> list[dict]:
    """
    Détecte les équipes méta que l'ennemi peut aligner.
    Vérifie que le leader ET au moins 60% des membres sont prêts GAC.

    Returns:
        Liste de dicts {leader_name, members, source}.
    """
    detected: list[dict] = []

    for leader_id, members_ids in _HARDCODED_META.items():
        # Filtrer par format (équipes 3v3 ont 3 membres, 5v5 en ont 5)
        expected_size = 3 if fmt == "3v3" else 5
        if len(members_ids) != expected_size:
            continue

        leader_unit = enemy_index.get(leader_id)
        if not leader_unit or not _is_gac_ready(leader_unit):
            continue

        ready_members = sum(
            1 for mid in members_ids
            if enemy_index.get(mid) and _is_gac_ready(enemy_index[mid])
        )

        # Au moins 60% des membres prêts
        if ready_members / len(members_ids) >= 0.6:
            detected.append({
                "leader_id":   leader_id,
                "leader_name": get_name(leader_id),
                "members":     [get_name(mid) for mid in members_ids],
                "ready_count": ready_members,
                "total":       len(members_ids),
            })

    # Trier par nombre de membres prêts décroissant
    detected.sort(key=lambda t: t["ready_count"], reverse=True)
    return detected


async def _get_counters_from_db(leader_name: str, fmt: str) -> list[str]:
    """Cherche les contres dans meta_teams pour un leader donné."""
    try:
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT counters FROM meta_teams
                WHERE leader_name = ? AND format = ?
                LIMIT 1
                """,
                (leader_name, fmt),
            )
            row = await cursor.fetchone()
        if row and row["counters"]:
            return json.loads(row["counters"])
    except Exception:
        log.debug("Pas de contre trouvé en BDD pour %s", leader_name)
    return []


def _get_counters_hardcoded(leader_id: str) -> list[str]:
    """Retourne les contres hardcodés pour un leader."""
    counter_ids = _HARDCODED_COUNTERS.get(leader_id.upper(), [])
    return [get_name(cid) for cid in counter_ids]


def _filter_owned_counters(
    counter_names: list[str],
    my_index: dict[str, dict],
) -> list[dict]:
    """
    Filtre les contres que le joueur possède et qui sont prêts GAC.
    Retourne des dicts {name, relic_tier, gear_tier, ready}.
    """
    result = []
    for name in counter_names:
        # Cherche par nom dans l'index (qui est indexé par base_id)
        # On fait une recherche inverse via le dict statique
        from services.unit_names import _STATIC_NAMES
        base_id = next(
            (bid for bid, n in _STATIC_NAMES.items() if n == name),
            None,
        )
        unit = my_index.get(base_id.upper()) if base_id else None
        result.append({
            "name":       name,
            "base_id":    base_id,
            "relic_tier": unit["relic_tier"] if unit else None,
            "gear_tier":  unit["gear_tier"]  if unit else None,
            "ready":      _is_gac_ready(unit) if unit else False,
            "owned":      unit is not None,
        })
    # Trier : prêts en premier, puis possédés, puis non possédés
    result.sort(key=lambda c: (not c["ready"], not c["owned"]))
    return result


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------
async def analyze_matchup(
    my_ally_code: str,
    enemy_ally_code: str,
    fmt: str = "5v5",
) -> dict:
    """
    Analyse un matchup GAC et retourne des suggestions de contres.

    Args:
        my_ally_code:     Code allié du joueur (sans tirets).
        enemy_ally_code:  Code allié de l'ennemi (sans tirets).
        fmt:              '5v5' ou '3v3'.

    Returns:
        Dict avec :
        - enemy_name      : nom de l'ennemi
        - enemy_teams     : équipes méta détectées chez l'ennemi
        - suggestions     : liste de {enemy_team, counters[]}
        - fmt             : format analysé
    """
    # Récupération en parallèle des deux rosters
    import asyncio
    my_roster, enemy_roster = await asyncio.gather(
        get_player_roster(my_ally_code),
        get_player_roster(enemy_ally_code),
    )

    my_index    = _build_roster_index(my_roster)
    enemy_index = _build_roster_index(enemy_roster)

    # Récupérer le nom de l'ennemi
    from services.comlink import get_player
    enemy_profile = await get_player(enemy_ally_code)
    enemy_name = enemy_profile.get("name", enemy_ally_code)

    # Détecter les équipes méta de l'ennemi
    enemy_teams = _detect_enemy_meta_teams(enemy_index, fmt)

    # Pour chaque équipe, chercher les contres
    suggestions = []
    for team in enemy_teams:
        # BDD d'abord, hardcoded en fallback
        counters_names = await _get_counters_from_db(team["leader_name"], fmt)
        if not counters_names:
            counters_names = _get_counters_hardcoded(team["leader_id"])

        counters_with_status = _filter_owned_counters(counters_names, my_index)

        suggestions.append({
            "enemy_team": team,
            "counters":   counters_with_status,
        })

    return {
        "enemy_name":  enemy_name,
        "enemy_teams": enemy_teams,
        "suggestions": suggestions,
        "fmt":         fmt,
    }
