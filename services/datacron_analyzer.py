"""
services/datacron_analyzer.py — Analyse de l'impact tactique des Datacrons sur une escouade (Attaque & Défense).
"""
import logging
import re
from typing import Any
from database.db import get_db, get_character_metadata

log = logging.getLogger(__name__)

# Dictionnaires de détection des Factions, Alignements et Rôles
KNOWN_ALIGNMENTS = {
    "LIGHT SIDE": "LIGHT_SIDE",
    "DARK SIDE": "DARK_SIDE",
    "NEUTRAL": "NEUTRAL",
    "CÔTÉ LUMINEUX": "LIGHT_SIDE",
    "CÔTÉ OBSCUR": "DARK_SIDE",
}

KNOWN_ROLES = {
    "ATTACKER": "ATTACKER",
    "ATTAQUANT": "ATTACKER",
    "TANK": "TANK",
    "SUPPORT": "SUPPORT",
    "SOUTIEN": "SUPPORT",
    "HEALER": "HEALER",
    "SOIGNEUR": "HEALER",
    "LEADER": "LEADER",
}

KNOWN_FACTIONS = {
    "REBEL": "REBEL",
    "REBELS": "REBEL",
    "REBELLE": "REBEL",
    "EMPIRE": "EMPIRE",
    "GALACTIC REPUBLIC": "GALACTIC_REPUBLIC",
    "RÉPUBLIQUE GALACTIQUE": "GALACTIC_REPUBLIC",
    "SITH": "SITH",
    "SITH EMPIRE": "SITH_EMPIRE",
    "JEDI": "JEDI",
    "FIRST ORDER": "FIRST_ORDER",
    "PREMIER ORDRE": "FIRST_ORDER",
    "RESISTANCE": "RESISTANCE",
    "RÉSISTANCE": "RESISTANCE",
    "BOUNTY HUNTER": "BOUNTY_HUNTERS",
    "BOUNTY HUNTERS": "BOUNTY_HUNTERS",
    "CHASSEUR DE PRIMES": "BOUNTY_HUNTERS",
    "MANDALORIAN": "MANDALORIAN",
    "MANDALORIEN": "MANDALORIAN",
    "SEPARATIST": "SEPARATIST",
    "SÉPARATISTE": "SEPARATIST",
    "DROID": "DROID",
    "DROÏDE": "DROID",
    "SCOUNDREL": "SCOUNDREL",
    "VOYOU": "SCOUNDREL",
    "CLONE TROOPER": "CLONE_TROOPER",
    "SOLDAT CLONE": "CLONE_TROOPER",
    "EWOK": "EWOK",
    "GEONOSIAN": "GEONOSIAN",
    "GÉONOSIEN": "GEONOSIAN",
    "HUTT CARTEL": "HUTT_CARTEL",
    "CARTEL DES HUTTS": "HUTT_CARTEL",
    "INQUISITORIUS": "INQUISITORIUS",
    "INQUISITEUR": "INQUISITORIUS",
    "IMPERIAL REMNANT": "IMPERIAL_REMNANT",
    "VESTIGE DE L'EMPIRE": "IMPERIAL_REMNANT",
    "IMPERIAL TROOPER": "IMPERIAL_TROOPER",
    "SOLDAT DE L'EMPIRE": "IMPERIAL_TROOPER",
    "NIGHTSISTERS": "NIGHTSISTERS",
    "NIGHTSISTER": "NIGHTSISTERS",
    "SŒUR DE LA NUIT": "NIGHTSISTERS",
    "TUSKEN": "TUSKEN",
    "UNALIGNED FORCE USER": "UNALIGNED_FORCE_USER",
    "UTILISATEUR DE LA FORCE NON ALIGNÉ": "UNALIGNED_FORCE_USER",
    "SMUGGLER": "SMUGGLER",
    "CONTREBANDIER": "SMUGGLER",
    "JAWA": "JAWA",
    "BAD BATCH": "BAD_BATCH",
    "OLD REPUBLIC": "OLD_REPUBLIC",
    "ANCIENNE RÉPUBLIQUE": "OLD_REPUBLIC",
}


def parse_affix_target_scopes(scope: int, scope_name: str, description: str, target_unit_id: str = "") -> dict[str, str | None]:
    """
    Extrait les cibles (alignement, faction, rôle, personnage) d'un palier de Datacron.
    """
    combined = f"{scope_name or ''} {description or ''}".upper()

    target_alignment = None
    target_faction = None
    target_role = None
    extracted_unit_id = (target_unit_id or "").strip().upper() or None

    # 1. Alignement
    for k, v in KNOWN_ALIGNMENTS.items():
        if re.search(rf"\b{k}\b", combined):
            target_alignment = v
            break

    # 2. Faction
    for k, v in KNOWN_FACTIONS.items():
        if re.search(rf"\b{k}\b", combined):
            target_faction = v
            break

    # 3. Rôle
    for k, v in KNOWN_ROLES.items():
        if re.search(rf"\b{k}\b", combined):
            target_role = v
            break

    # 4. Scope 3 = Perso spécifique si scope_name ressemble à un perso ou target_unit_id fourni
    if scope >= 3 and not extracted_unit_id and scope_name:
        clean_name = re.sub(r"[^A-Z0-9]", "", scope_name.upper())
        if clean_name and clean_name not in KNOWN_FACTIONS.values() and clean_name not in KNOWN_ALIGNMENTS.values():
            extracted_unit_id = clean_name

    return {
        "target_alignment": target_alignment,
        "target_faction": target_faction,
        "target_role": target_role,
        "target_unit_id": extracted_unit_id
    }


async def get_template_affixes(template_id: str, max_tier: int = 15) -> list[dict]:
    """Récupère les affixes actifs d'un template jusqu'à un niveau donné."""
    if not template_id:
        return []
    affixes = []
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT tier, scope, scope_name, target_unit_id, target_alignment, target_faction, target_role,
                   stat_type, stat_value, ability_id, description, icon_url
            FROM datacron_affixes
            WHERE template_id = ? AND tier <= ?
            ORDER BY tier ASC
            """,
            (template_id, max_tier)
        )
        rows = await cursor.fetchall()
        for r in rows:
            affixes.append(dict(r))
    return affixes


async def analyze_datacron_impact_on_squad(
    template_id: str,
    level: int,
    squad_base_ids: list[str]
) -> dict[str, Any]:
    """
    Analyse l'impact tactique complet d'un Datacron sur une escouade de 3 ou 5 personnages.
    Retourne :
      - is_applicable : bool (si au moins 1 perso bénéficie d'un bonus)
      - affected_members : liste détaillée par personnage avec ses bonus actifs
      - stat_summary : résumé des stats cumulées
      - special_mechanics : capacités spéciales débloquées
      - threat_level : niveau de menace (LOW, MEDIUM, HIGH, EXTREME)
      - counter_tips : conseils de contre
    """
    if not squad_base_ids or not template_id or level <= 0:
        return {
            "is_applicable": False,
            "threat_level": "NONE",
            "affected_members": [],
            "special_mechanics": [],
            "counter_tips": []
        }

    # 1. Récupération des métadonnées de chaque membre de l'escouade
    squad_meta = []
    for bid in squad_base_ids:
        meta = await get_character_metadata(bid)
        if meta:
            squad_meta.append(meta)
        else:
            squad_meta.append({
                "base_id": bid,
                "name": bid,
                "alignment": None,
                "role": None,
                "factions": [],
                "is_galactic_legend": False,
                "is_leader": False
            })

    # 2. Récupération des affixes du Datacron jusqu'au niveau actif
    affixes = await get_template_affixes(template_id, max_tier=level)
    if not affixes:
        return {
            "is_applicable": False,
            "threat_level": "NONE",
            "affected_members": [],
            "special_mechanics": [],
            "counter_tips": []
        }

    # 3. Évaluation membre par membre
    affected_members = []
    special_mechanics = []
    has_focused_char_active = False

    for char in squad_meta:
        c_bid = char["base_id"].upper()
        c_align = (char.get("alignment") or "").upper().replace(" ", "_")
        c_role = (char.get("role") or "").upper()
        c_factions = [f.upper().replace(" ", "_") for f in char.get("factions", [])]

        active_bonuses = []
        is_char_focused = False

        for aff in affixes:
            t_align = aff.get("target_alignment")
            t_fac = aff.get("target_faction")
            t_role = aff.get("target_role")
            t_unit = aff.get("target_unit_id")
            scope = aff.get("scope", 1)

            applies = False

            # Scope 1 (Stats générales / Alignement)
            if scope == 1:
                if not t_align or t_align == c_align:
                    applies = True

            # Scope 2 (Faction / Rôle)
            elif scope == 2:
                align_match = (not t_align or t_align == c_align)
                role_match = (not t_role or t_role == c_role)
                fac_match = (not t_fac or any(t_fac in f for f in c_factions))
                if align_match and (role_match or fac_match):
                    applies = True

            # Scope 3 (Perso spécifique ou faction restreinte)
            elif scope >= 3:
                if t_unit and (t_unit in c_bid or c_bid in t_unit):
                    applies = True
                    is_char_focused = True
                    has_focused_char_active = True
                elif t_fac and any(t_fac in f for f in c_factions):
                    applies = True

            if applies:
                active_bonuses.append({
                    "tier": aff.get("tier"),
                    "scope": scope,
                    "stat_type": aff.get("stat_type"),
                    "stat_value": aff.get("stat_value"),
                    "description": aff.get("description"),
                    "scope_name": aff.get("scope_name")
                })
                if aff.get("description") and scope >= 2:
                    if aff["description"] not in special_mechanics:
                        special_mechanics.append(aff["description"])

        if active_bonuses:
            affected_members.append({
                "base_id": char["base_id"],
                "name": char["name"],
                "is_focused_unit": is_char_focused,
                "bonuses_count": len(active_bonuses),
                "bonuses": active_bonuses
            })

    # 4. Calcul du niveau de menace (Threat Level)
    threat_score = 0
    threat_score += len(affected_members) * 10
    if has_focused_char_active:
        threat_score += 40
    if level >= 5:
        threat_score += 20
    elif level >= 3:
        threat_score += 10

    if threat_score >= 65:
        threat_level = "EXTREME"
    elif threat_score >= 40:
        threat_level = "HIGH"
    elif threat_score >= 20:
        threat_level = "MEDIUM"
    elif threat_score > 0:
        threat_level = "LOW"
    else:
        threat_level = "NONE"

    # 5. Conseils de contre tactiques basés sur les mécaniques
    counter_tips = []
    combined_desc = " ".join(special_mechanics).lower()
    
    if "revive" in combined_desc or "ressusc" in combined_desc:
        counter_tips.append("Anti-Revive requis (ex: Boba Fett, GAS, SLKR) pour empêcher la résurrection.")
    if "ignore defense" in combined_desc or "ignore l'armure" in combined_desc:
        counter_tips.append("Dégâts bruts / Ignore l'armure : Privilégier des persos avec Damage Immunity ou Foresight.")
    if "counter" in combined_desc or "riposte" in combined_desc:
        counter_tips.append("Forte riposte adverse : Utiliser Daze (Étourdissement/Confusion) ou attaques furtives.")
    if "tenacity" in combined_desc or "ténacité" in combined_desc:
        counter_tips.append("Haute ténacité : Éviter les équipes dépendantes des debuffs ou apporter Tenacity Down incontournable.")
    if "health steal" in combined_desc or "vol de vie" in combined_desc or "heal" in combined_desc:
        counter_tips.append("Fort sustain / Vol de vie : Apporter Healing Immunity (Immunité aux soins).")
    if "stealth" in combined_desc or "camouflage" in combined_desc:
        counter_tips.append("Camouflage adverse : Apporter du dispel AoE ou True Sight.")

    return {
        "is_applicable": len(affected_members) > 0,
        "threat_level": threat_level,
        "threat_score": threat_score,
        "has_focused_char_active": has_focused_char_active,
        "affected_members": affected_members,
        "special_mechanics": special_mechanics,
        "counter_tips": counter_tips
    }
