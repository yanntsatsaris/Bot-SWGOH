"""
services/scouting.py — Moteur de Scouting Hybride pour la GAC
"""
import asyncio
import json
import logging
import os
import sys
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

async def get_gac_valid_omicron_units() -> set[str]:
    valid_units = set()
    try:
        async with get_db() as db:
            async with db.execute("SELECT DISTINCT base_id FROM gac_valid_omicrons") as cursor:
                async for row in cursor:
                    valid_units.add(row["base_id"].upper())
    except Exception as e:
        log.warning(f"Erreur chargement gac_valid_omicrons: {e}")
    return valid_units

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

async def get_zeta_dict() -> dict:
    zetas = {}
    try:
        async with get_db() as db:
            async with db.execute("SELECT skill_id, zeta_tier FROM game_zetas") as cursor:
                async for row in cursor:
                    zetas[row["skill_id"]] = row["zeta_tier"]
    except Exception as e:
        log.warning(f"Erreur chargement zetas: {e}")
    return zetas

def _is_gac_ready(unit: dict) -> bool:
    return unit.get("relic_tier", 0) > 0 or unit.get("gear_tier", 0) >= 11

def _get_fleet_max_reinforcements(capital_rarity: int) -> int:
    """
    Retourne le nombre maximum de renforts autorisés en fonction des étoiles du vaisseau capital.
    Règle officielle SWGOH :
      1★ à 2★ : 1 renfort max
      3★ à 5★ : 2 renforts max
      6★     : 3 renforts max
      7★     : 4 renforts max (limite absolue)
    """
    if capital_rarity <= 2:
        return 1
    elif capital_rarity <= 5:
        return 2
    elif capital_rarity == 6:
        return 3
    else:  # 7★
        return 4

async def get_db_meta_fleets(mode: str = "defense") -> dict:
    """
    Récupère les compositions de flottes méta dynamiquement depuis la BDD (fleet_tier_list et ship_counters).
    GAC_FLEETS ne sert qu'en cas de secours extrême si la base est vide.
    """
    fleets = {}
    try:
        async with get_db() as db:
            # 1. D'abord depuis fleet_tier_list (scrapée depuis swgoh.gg)
            cursor = await db.execute(
                """
                SELECT capital_ship, members_ids, hold_pct, win_pct, rank
                FROM fleet_tier_list
                WHERE side = ? OR side = 'defense'
                ORDER BY rank ASC
                """,
                (mode,)
            )
            rows = await cursor.fetchall()
            for r in rows:
                cap = (r["capital_ship"] or "").upper()
                mems = json.loads(r["members_ids"] or "[]")
                if cap and mems and cap not in fleets:
                    fleets[cap] = {
                        "members": [cap] + [m for m in mems if m.upper() != cap],
                        "defense": max(1, int((r["hold_pct"] or 50) / 10))
                    }

            # 2. Compléter depuis ship_counters (compositions défensives les plus jouées)
            cursor = await db.execute(
                """
                SELECT def_capital, def_members_ids, SUM(seen) as total_seen
                FROM ship_counters
                WHERE def_members_ids IS NOT NULL AND def_members_ids != '[]' AND def_members_ids != ''
                GROUP BY def_capital, def_members_ids
                ORDER BY total_seen DESC
                """
            )
            rows = await cursor.fetchall()
            for r in rows:
                cap = (r["def_capital"] or "").upper()
                mems = json.loads(r["def_members_ids"] or "[]")
                if cap and mems and cap not in fleets:
                    fleets[cap] = {
                        "members": [cap] + [m for m in mems if m.upper() != cap],
                        "defense": 8
                    }
    except Exception as e:
        log.warning(f"[MetaFleets] Erreur lecture flottes BDD: {e}")

    # Secours si BDD totalement vide
    if not fleets:
        from services.gac_meta import GAC_FLEETS
        fleets = GAC_FLEETS

    return fleets

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


def attach_datacrons_to_scouted_zones(zones: dict, player_datacrons: list[dict], roster_index: dict = None) -> None:
    """
    Associe intelligemment les Datacrons de l'inventaire du joueur aux escouades défensives.
    Prend en compte les prérequis officiels de Reliques pour l'activation réelle des paliers :
    - Tier 1 (Palier 3) : Tous les membres doivent être au moins Relic 3 (R3+).
    - Tier 2 (Palier 6) : Tous les membres doivent être au moins Relic 5 (R5+).
    - Tier 3 (Palier 9) : Tous les membres doivent être au moins Relic 7 (R7+).
    """
    if not player_datacrons:
        return

    valid_dtcs = [d for d in player_datacrons if len(d.get("affix", [])) >= 3]
    if not valid_dtcs:
        return

    # Dictionnaire de correspondance de factions pour vérification de l'escouade
    FACTION_KEYWORDS = {
        "resistance": ["GLREY", "REY", "BENSOLO", "REYJEDITRAINING", "FINN", "POE", "AMILYNHOLDO", "BB8", "RESISTANCE", "ROSE", "ZORII"],
        "firstorder": ["SUPREMELEADERKYLOREN", "KYLOREN", "GENERALHUX", "FIRSTORDER", "SITHTROOPER", "PHASMA", "FOST", "KRU", "EXECUTIONER"],
        "empire": ["VADER", "EMPEROR", "VEERS", "IDEN", "THRAWN", "INQUISITOR", "THIRD_SISTER", "FIFTHBROTHER", "SEVENTHSISTER", "EIGHTHBROTHER", "MARAJADE", "GIDEON", "STARCK", "PIETT", "TIE", "SNOWTROOPER"],
        "inquisitor": ["THIRDSISTER", "GRANDINQUISITOR", "FIFTHBROTHER", "SEVENTHSISTER", "EIGHTHBROTHER", "NINTHSISTER", "SECOND_SISTER", "MARROK", "INQUISITOR"],
        "imperialtrooper": ["VEERS", "PIETT", "STARCK", "IDEN", "GIDEON", "DARKTROOPER", "RANGETROOPER", "DEATHTROOPER", "SNOWTROOPER", "MAGMATROOPER", "SHORETROOPER", "SCOUTTROOPER"],
        "rebel": ["COMMANDERLUKESKYWALKER", "HANSOLO", "CHEWBACCA", "LEIA", "MOTHMA", "RADDUS", "CHOPPER", "HERA", "CASSIAN", "JYN", "SAWGERRERA", "KLEYA", "LUTHEN", "CHIRRUT", "BAZE", "REBEL", "DROGAN"],
        "jedi": ["JEDIMASTERKENOBI", "JEDIMASTERLUKE", "MACEWINDU", "JEDIKNIGHTREVAN", "QUI", "YODA", "AHSOKA", "JEDI", "CALKESTIS", "KELLERANBEQ", "KAM", "PLO", "AAYLA", "JEDIKNIGHTCAL"],
        "galacticrepublic": ["QUEENAMIDALA", "MASTERQUIGON", "PADAWANOBIWAN", "PADMEAMIDALA", "GENERALKENOBI", "MACEWINDU", "SHAAKTI", "GRANDMASTERYODA", "ANAKINKNIGHT", "CLONETROOPER", "REX", "CODY", "ECHO", "FIVES", "GALACTICREPUBLIC", "GAS", "GENERALSKYWALKER", "HUNTER", "WRECKER", "TECH", "CROSSHAIR", "OMEGA"],
        "badbatch": ["HUNTER", "WRECKER", "TECH", "ECHO", "OMEGA", "CROSSHAIR"],
        "clonetrooper": ["REX", "CODY", "ECHO", "FIVES", "ARCTROOPER", "HUNTER", "WRECKER", "TECH", "CROSSHAIR", "CLONETROOPER", "GREGOR"],
        "separatist": ["GRIEVOUS", "B1BATTLEDROID", "B2SUPERBATTLEDROID", "MAGNAGUARD", "DROIDEKA", "NUTEGUNRAY", "WATTAMBOR", "JANGOFETT", "DOOKU", "TRENCH", "SEPARATIST", "POGGLE", "SUNFAC", "GEONOSIAN", "STAP"],
        "geonosian": ["GEONOSIANBROODALPHA", "POGGLE", "SUNFAC", "GEONOSIANSOLDIER", "GEONOSIANSPY", "GEONOSIAN"],
        "sith": ["SITHPALPATINE", "DARTHBANE", "DARTHMALGUS", "DARTHMALAK", "DARTHTRAYA", "DARTHNIHILUS", "DARTHSION", "SITH", "SITHMARAUDER", "TALON", "SAVAGEOPRESS", "DARTHVADER"],
        "sithempire": ["DARTHMALGUS", "DARTHREVAN", "DARTHMALAK", "BASTILASHANDARK", "SITHMARAUDER", "SITHEMPIRE", "SITHASSASSIN"],
        "oldrepublic": ["JEDIKNIGHTREVAN", "BASTILASHAN", "JOLEEBINDO", "MISSIONVAO", "ZAALBAR", "CARTHONASI", "JUHANI", "T3M4", "CANDEROUS", "OLDREPUBLIC"],
        "bountyhunter": ["BOBAFETT", "BOSSK", "JANGOFETT", "DENGAR", "EMBO", "MANDALORIAN", "FENNEC", "KRRSANTAN", "GREEDO", "IG88", "AURRA", "ZUCKUSS", "4LOM"],
        "huttcartel": ["GLHONDO", "HONDO", "BOBAFETT", "BOBAFETTSCION", "KRRSANTAN", "EMBO", "CADBANE", "GREEDO", "GAMORREANGUARD", "MOBENFORCER", "HUTTCARTEL", "BRUTUS", "CAPTAINSILVO", "SM33", "VANE", "JABBA", "SKIFF", "BOUSHH"],
        "scoundrel": ["GLHONDO", "HONDO", "DASHRENDAR", "CHEWBACCA", "L3_37", "QI_RA", "ENFYS", "SCOUNDREL", "PIRATE", "BRUTUS", "CAPTAINSILVO", "SM33", "VANE", "KUIIL", "IG11", "NEST"],
        "nightsister": ["MOTHERTALZIN", "ASAJJVENTRESS", "MERRIN", "OLDDAKA", "NIGHTSISTERZOMBIE", "GREATMOTHERS", "NIGHTSISTER", "MORGANELSBETH", "NIGHTSISTERINITIATE", "NIGHTSISTERSPIRIT"],
        "mandalorian": ["MANDALORIAN", "BO-KATAN", "THEMANDALORIAN", "ARMORER", "SABINE", "PAZVIZSLA", "BESKARGARMOR", "BO_KATAN", "MANDOBOKATAN", "MAUL"],
        "gungan": ["JARJARBINDS", "JARJARBINKS", "BOSSNASS", "CAPTAINTARPALS", "GUNGANBOOMADIER", "GUNGANPHALANX", "GUNGAN"],
        "ewok": ["CHIEFCHIRPA", "EWOKELDER", "PAPLOO", "LOGRAY", "WICKET", "KNEESAA", "EWOK"],
        "jawa": ["CHIEFNEBIT", "JAWAENGINEER", "JAWASCAVENGER", "DATHCHA", "JAWA"],
        "tusken": ["TUSKENCHIEFTAIN", "TUSKENWARRIOR", "TUSKENRAIDER", "TUSKENSHAMAN", "URORRURRR", "TUSKEN"],
        "unalignedforceuser": ["CEREJUNDA", "CALKESTIS", "FULCRUM", "BENSOLO", "KYLOREN", "STRANGER", "QIMIR", "BAYLAN", "SHIN", "UNALIGNEDFORCEUSER", "STARKILLER", "MARAJADE", "VISAS", "MAUL"]
    }

    used_dtc_ids = set()

    for zone_name in ["North", "South", "Back"]:
        for team in zones.get(zone_name, []):
            ldr = team.get("leader_id")
            if not ldr or ldr in ["USED", "None", "EMPTY", "Vide"]:
                continue
            members = [ldr] + team.get("members_ids", [])
            members_upper = [m.upper() for m in members if m]
            squad_str = " ".join(members_upper)

            best_dtc = None
            best_match_level = 0  # 4 = Perso, 3 = Faction, 2 = Role/Alignement

            for dtc in valid_dtcs:
                dtc_id = dtc.get("id")
                if dtc_id in used_dtc_ids:
                    continue

                affixes = dtc.get("affix", [])
                template_id = dtc.get("templateId", "")
                
                dtc_char_target = None
                dtc_faction_target = None
                dtc_align_target = None
                dtc_role_target = None

                for aff in affixes:
                    rule = (aff.get("targetRule") or "").lower()
                    ab_id = (aff.get("abilityId") or "").lower()
                    combined_target = f"{rule} {ab_id}"

                    # 1. Vérification cible personnage spécifique
                    for m_id in members_upper:
                        clean_m = m_id.replace("_", "").lower()
                        if (clean_m in combined_target) or (m_id in ["GLREY", "REY"] and "glrey" in combined_target):
                            dtc_char_target = m_id
                            break

                    # 2. Vérification cible faction
                    for fac_name, keywords in FACTION_KEYWORDS.items():
                        if fac_name in combined_target:
                            if any(kw in squad_str for kw in keywords):
                                dtc_faction_target = fac_name
                                break

                    # 3. Vérification Rôles (Tank, Support, Attacker, Healer)
                    for r_name in ["tank", "support", "attacker", "healer"]:
                        if r_name in combined_target:
                            dtc_role_target = r_name

                    # 4. Vérification alignement
                    if "darkside" in combined_target:
                        dtc_align_target = "DARK_SIDE"
                    elif "lightside" in combined_target:
                        dtc_align_target = "LIGHT_SIDE"

                # Calcul du niveau d'étoiles/pastilles maximales selon les affixes
                if len(affixes) >= 9:
                    dtc_max_tier = 3
                elif len(affixes) >= 6:
                    dtc_max_tier = 2
                elif len(affixes) >= 3:
                    dtc_max_tier = 1
                else:
                    dtc_max_tier = 0

                # Score et sélection stricte : Uniquement Personnage ou Faction dédiée !
                if dtc_char_target:
                    best_dtc = {
                        "template_id": template_id,
                        "level": dtc_max_tier,
                        "is_focused": "focused" in template_id,
                        "character_base_id": dtc_char_target,
                        "id": dtc_id
                    }
                    best_match_level = 4
                    break  # Priorité absolue au personnage spécifique !
                elif dtc_faction_target and best_match_level < 3:
                    best_dtc = {
                        "template_id": template_id,
                        "level": dtc_max_tier,
                        "is_focused": False,
                        "id": dtc_id
                    }
                    best_match_level = 3

            if best_dtc:
                # ── CONTRÔLE DES RELIQUES DU JOUEUR/ENNEMI SELON LES PRÉREQUIS OFFICIELS ──
                # - Palier 1 (Tier 3) : R3+
                # - Palier 2 (Tier 6) : R5+
                # - Palier 3 (Tier 9) : R7+
                if roster_index and members_upper:
                    char_target = best_dtc.get("character_base_id")
                    if char_target and char_target in roster_index:
                        char_relic = roster_index[char_target].get("relic_tier", 0)
                        if char_relic >= 7:
                            pass
                        elif char_relic >= 5:
                            best_dtc["level"] = min(best_dtc["level"], 2)
                        elif char_relic >= 3:
                            best_dtc["level"] = min(best_dtc["level"], 1)
                        else:
                            best_dtc["level"] = 0
                    else:
                        # Datacron de faction : vérifie le niveau de relique des membres
                        max_relic = max((roster_index.get(m, {}).get("relic_tier", 0) for m in members_upper if m in roster_index), default=0)
                        if max_relic >= 7:
                            pass
                        elif max_relic >= 5:
                            best_dtc["level"] = min(best_dtc["level"], 2)
                        elif max_relic >= 3:
                            best_dtc["level"] = min(best_dtc["level"], 1)
                        else:
                            best_dtc["level"] = 0

                team["datacron"] = best_dtc
                used_dtc_ids.add(best_dtc["id"])

def attach_datacrons_to_attack_plan(plan: dict, player_datacrons: list[dict], roster_index: dict = None) -> None:
    """
    Associe intelligemment les Datacrons de l'inventaire du joueur aux escouades d'attaque recommandées dans le planneur.
    Règle d'usage unique : chaque Datacron physique n'est assigné qu'à une seule équipe d'attaque.
    """
    if not player_datacrons or not plan:
        return

    valid_dtcs = [d for d in player_datacrons if len(d.get("affix", [])) >= 3]
    if not valid_dtcs:
        return

    FACTION_KEYWORDS = {
        "resistance": ["GLREY", "REY", "BENSOLO", "REYJEDITRAINING", "FINN", "POE", "AMILYNHOLDO", "BB8", "RESISTANCE", "ROSE", "ZORII"],
        "firstorder": ["SUPREMELEADERKYLOREN", "KYLOREN", "GENERALHUX", "FIRSTORDER", "SITHTROOPER", "PHASMA", "FOST", "KRU", "EXECUTIONER"],
        "empire": ["VADER", "EMPEROR", "VEERS", "IDEN", "THRAWN", "INQUISITOR", "THIRD_SISTER", "FIFTHBROTHER", "SEVENTHSISTER", "EIGHTHBROTHER", "MARAJADE", "GIDEON", "STARCK", "PIETT", "TIE", "SNOWTROOPER"],
        "inquisitor": ["THIRDSISTER", "GRANDINQUISITOR", "FIFTHBROTHER", "SEVENTHSISTER", "EIGHTHBROTHER", "NINTHSISTER", "SECOND_SISTER", "MARROK", "INQUISITOR"],
        "imperialtrooper": ["VEERS", "PIETT", "STARCK", "IDEN", "GIDEON", "DARKTROOPER", "RANGETROOPER", "DEATHTROOPER", "SNOWTROOPER", "MAGMATROOPER", "SHORETROOPER", "SCOUTTROOPER"],
        "rebel": ["COMMANDERLUKESKYWALKER", "HANSOLO", "CHEWBACCA", "LEIA", "MOTHMA", "RADDUS", "CHOPPER", "HERA", "CASSIAN", "JYN", "SAWGERRERA", "KLEYA", "LUTHEN", "CHIRRUT", "BAZE", "REBEL", "DROGAN"],
        "jedi": ["JEDIMASTERKENOBI", "JEDIMASTERLUKE", "MACEWINDU", "JEDIKNIGHTREVAN", "QUI", "YODA", "AHSOKA", "JEDI", "CALKESTIS", "KELLERANBEQ", "KAM", "PLO", "AAYLA", "JEDIKNIGHTCAL"],
        "galacticrepublic": ["QUEENAMIDALA", "MASTERQUIGON", "PADAWANOBIWAN", "PADMEAMIDALA", "GENERALKENOBI", "MACEWINDU", "SHAAKTI", "GRANDMASTERYODA", "ANAKINKNIGHT", "CLONETROOPER", "REX", "CODY", "ECHO", "FIVES", "GALACTICREPUBLIC", "GAS", "GENERALSKYWALKER", "HUNTER", "WRECKER", "TECH", "CROSSHAIR", "OMEGA"],
        "badbatch": ["HUNTER", "WRECKER", "TECH", "ECHO", "OMEGA", "CROSSHAIR"],
        "clonetrooper": ["REX", "CODY", "ECHO", "FIVES", "ARCTROOPER", "HUNTER", "WRECKER", "TECH", "CROSSHAIR", "CLONETROOPER", "GREGOR"],
        "separatist": ["GRIEVOUS", "B1BATTLEDROID", "B2SUPERBATTLEDROID", "MAGNAGUARD", "DROIDEKA", "NUTEGUNRAY", "WATTAMBOR", "JANGOFETT", "DOOKU", "TRENCH", "SEPARATIST", "POGGLE", "SUNFAC", "GEONOSIAN", "STAP"],
        "geonosian": ["GEONOSIANBROODALPHA", "POGGLE", "SUNFAC", "GEONOSIANSOLDIER", "GEONOSIANSPY", "GEONOSIAN"],
        "sith": ["SITHPALPATINE", "DARTHBANE", "DARTHMALGUS", "DARTHMALAK", "DARTHTRAYA", "DARTHNIHILUS", "DARTHSION", "SITH", "SITHMARAUDER", "TALON", "SAVAGEOPRESS", "DARTHVADER"],
        "sithempire": ["DARTHMALGUS", "DARTHREVAN", "DARTHMALAK", "BASTILASHANDARK", "SITHMARAUDER", "SITHEMPIRE", "SITHASSASSIN"],
        "oldrepublic": ["JEDIKNIGHTREVAN", "BASTILASHAN", "JOLEEBINDO", "MISSIONVAO", "ZAALBAR", "CARTHONASI", "JUHANI", "T3M4", "CANDEROUS", "OLDREPUBLIC"],
        "bountyhunter": ["BOBAFETT", "BOSSK", "JANGOFETT", "DENGAR", "EMBO", "MANDALORIAN", "FENNEC", "KRRSANTAN", "GREEDO", "IG88", "AURRA", "ZUCKUSS", "4LOM"],
        "huttcartel": ["GLHONDO", "HONDO", "BOBAFETT", "BOBAFETTSCION", "KRRSANTAN", "EMBO", "CADBANE", "GREEDO", "GAMORREANGUARD", "MOBENFORCER", "HUTTCARTEL", "BRUTUS", "CAPTAINSILVO", "SM33", "VANE", "JABBA", "SKIFF", "BOUSHH"],
        "scoundrel": ["GLHONDO", "HONDO", "DASHRENDAR", "CHEWBACCA", "L3_37", "QI_RA", "ENFYS", "SCOUNDREL", "PIRATE", "BRUTUS", "CAPTAINSILVO", "SM33", "VANE", "KUIIL", "IG11", "NEST"],
        "nightsister": ["MOTHERTALZIN", "ASAJJVENTRESS", "MERRIN", "OLDDAKA", "NIGHTSISTERZOMBIE", "GREATMOTHERS", "NIGHTSISTER", "MORGANELSBETH", "NIGHTSISTERINITIATE", "NIGHTSISTERSPIRIT"],
        "mandalorian": ["MANDALORIAN", "BO-KATAN", "THEMANDALORIAN", "ARMORER", "SABINE", "PAZVIZSLA", "BESKARGARMOR", "BO_KATAN", "MANDOBOKATAN", "MAUL"],
        "gungan": ["JARJARBINDS", "JARJARBINKS", "BOSSNASS", "CAPTAINTARPALS", "GUNGANBOOMADIER", "GUNGANPHALANX", "GUNGAN"],
        "ewok": ["CHIEFCHIRPA", "EWOKELDER", "PAPLOO", "LOGRAY", "WICKET", "KNEESAA", "EWOK"],
        "jawa": ["CHIEFNEBIT", "JAWAENGINEER", "JAWASCAVENGER", "DATHCHA", "JAWA"],
        "tusken": ["TUSKENCHIEFTAIN", "TUSKENWARRIOR", "TUSKENRAIDER", "TUSKENSHAMAN", "URORRURRR", "TUSKEN"],
        "unalignedforceuser": ["CEREJUNDA", "CALKESTIS", "FULCRUM", "BENSOLO", "KYLOREN", "STRANGER", "QIMIR", "BAYLAN", "SHIN", "UNALIGNEDFORCEUSER", "STARKILLER", "MARAJADE", "VISAS", "MAUL"]
    }

    used_dtc_ids = set()

    for zone, slots in plan.items():
        for slot in slots:
            c_info = slot.get("counter")
            if not c_info:
                continue
            
            c_leader = c_info.get("atk_leader_id")
            if not c_leader or c_leader in ["USED", "None", "EMPTY"]:
                continue
            
            members = [c_leader] + c_info.get("atk_members_ids", [])
            members_upper = [m.upper() for m in members if m]
            squad_str = " ".join(members_upper)

            best_dtc = None
            best_match_level = 0

            for dtc in valid_dtcs:
                dtc_id = dtc.get("id")
                if dtc_id in used_dtc_ids:
                    continue

                affixes = dtc.get("affix", [])
                template_id = dtc.get("templateId", "")
                
                dtc_char_target = None
                dtc_faction_target = None

                for aff in affixes:
                    rule = (aff.get("targetRule") or "").lower()
                    ab_id = (aff.get("abilityId") or "").lower()
                    combined_target = f"{rule} {ab_id}"

                    # 1. Personnage
                    for m_id in members_upper:
                        clean_m = m_id.replace("_", "").lower()
                        if (clean_m in combined_target) or (m_id in ["GLREY", "REY"] and "glrey" in combined_target):
                            dtc_char_target = m_id
                            break

                    # 2. Faction
                    for fac_name, keywords in FACTION_KEYWORDS.items():
                        if fac_name in combined_target:
                            if any(kw in squad_str for kw in keywords):
                                dtc_faction_target = fac_name
                                break

                dtc_max_tier = 3 if len(affixes) >= 9 else (2 if len(affixes) >= 6 else 1)

                if dtc_char_target:
                    best_dtc = {
                        "template_id": template_id,
                        "level": dtc_max_tier,
                        "is_focused": "focused" in template_id,
                        "character_base_id": dtc_char_target,
                        "id": dtc_id
                    }
                    best_match_level = 4
                    break
                elif dtc_faction_target and best_match_level < 3:
                    best_dtc = {
                        "template_id": template_id,
                        "level": dtc_max_tier,
                        "is_focused": False,
                        "id": dtc_id
                    }
                    best_match_level = 3

            if best_dtc:
                # ── CONTRÔLE DES RELIQUES DU JOUEUR SELON LES PRÉREQUIS OFFICIELS ──
                # - Palier 1 (Tier 3) : R3+
                # - Palier 2 (Tier 6) : R5+
                # - Palier 3 (Tier 9) : R7+
                if roster_index and members_upper:
                    char_target = best_dtc.get("character_base_id")
                    if char_target and char_target in roster_index:
                        char_relic = roster_index[char_target].get("relic_tier", 0)
                        if char_relic >= 7:
                            pass
                        elif char_relic >= 5:
                            best_dtc["level"] = min(best_dtc["level"], 2)
                        elif char_relic >= 3:
                            best_dtc["level"] = min(best_dtc["level"], 1)
                        else:
                            best_dtc["level"] = 0
                    else:
                        # Datacron de faction : vérifie le niveau de relique des membres
                        max_relic = max((roster_index.get(m, {}).get("relic_tier", 0) for m in members_upper if m in roster_index), default=0)
                        if max_relic >= 7:
                            pass
                        elif max_relic >= 5:
                            best_dtc["level"] = min(best_dtc["level"], 2)
                        elif max_relic >= 3:
                            best_dtc["level"] = min(best_dtc["level"], 1)
                        else:
                            best_dtc["level"] = 0

                c_info["datacron"] = best_dtc
                used_dtc_ids.add(best_dtc["id"])

def _build_roster_index(raw_roster: list, omicron_dict: dict, zeta_dict: dict, ship_base_ids: set, gac_omicron_units: set = None) -> dict:
    roster = {}
    ship_base_ids = ship_base_ids or set()
    for unit in raw_roster:
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
        relic_tier = max(0, raw_relic - 2) if raw_relic >= 2 else 0
        
        has_omicron = False
        omicrons_count = 0
        zetas_count = 0
        
        # Filtrage strict GAC : si la table gac_valid_omicrons est renseignée, l'unité DOIT avoir un omicron GAC
        is_gac_omi_candidate = (not gac_omicron_units) or (base_id.upper() in gac_omicron_units)
        
        unit_skills = (unit.get("skill") or [])
        for skill in unit_skills:
            skill_id = str(skill.get("id", ""))
            skill_tier_upgrades = int(skill.get("tier", 0))
            # In Comlink player payload, 'tier' is the number of upgrades, so tier 1 is 0 upgrades.
            actual_skill_tier = skill_tier_upgrades + 1
            
            if omicron_dict and skill_id in omicron_dict and actual_skill_tier >= int(omicron_dict[skill_id]):
                if is_gac_omi_candidate:
                    has_omicron = True
                    omicrons_count += 1
            if zeta_dict and skill_id in zeta_dict and actual_skill_tier >= int(zeta_dict[skill_id]):
                zetas_count += 1
                
        combat_type = 2 if base_id.upper() in ship_base_ids or base_id in ship_base_ids else unit.get("combatType", 1)

        unit_entry = {
            "base_id": base_id.upper(),
            "gear_tier": unit.get("currentTier", 0),
            "relic_tier": relic_tier,
            "rarity": unit.get("currentRarity", 0),
            "level": unit.get("currentLevel", 85),
            "has_omicron": has_omicron,
            "omicrons": omicrons_count,
            "zetas": zetas_count,
            "combat_type": combat_type
        }
        roster[base_id.upper()] = unit_entry
        roster[base_id] = unit_entry
    return roster

async def _predict_zones(enemy_index: dict, quotas: dict, fmt: str, ship_base_ids: set, habits: dict = None, league: str = "KYBER") -> dict:
    zones = {"North": [], "South": [], "Back": [], "Fleet": []}
    used_base_ids = set()
    expected_size = 3 if fmt == "3v3" else 5
            
    # 1. PERSONNAGES (Via la Meta Dynamique de swgoh.gg uniquement)
    # Récupérer les top teams défensives depuis la BDD
    dynamic_teams = []
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
                    
                if "GLREY" in units and "EZRAEXILE" in units:
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
        
        relic_sum = sum(
            (enemy_index.get(m.upper()) or enemy_index.get(m, {})).get("relic_tier", 0)
            for m in core_ready
        )
        ldr_relic = (enemy_index.get(leader_id.upper()) or enemy_index.get(leader_id, {})).get("relic_tier", 0)
        # Bonus d'investissement : les équipes avec de vraies reliques (R7, R8, R9) priment sur les compos G12/non-relique
        score = (def_score * 15) + (ldr_relic * 5) + (relic_sum * 2) + (len(core_ready) * 5)
        
        available_teams.append({
            "leader_id": leader_id,
            "members": core_ready,
            "defense": def_score,
            "offense": off_score,
            "score": score,
            "target_size": expected_size,
            "id": leader_id
        })
                
    # Trier par score pondéré par reliques réelles puis par défense
    available_teams.sort(key=lambda x: (x["score"], x["defense"]), reverse=True)

    # Filtrer les doublons de leader (si le joueur a les unités pour la Variation 1 et Variation 2)
    filtered_teams = []
    seen_leaders = set()
    for t in available_teams:
        if t["leader_id"] not in seen_leaders:
            filtered_teams.append(t)
            seen_leaders.add(t["leader_id"])
    available_teams = filtered_teams

    # 0. INJECTION DE L'HISTORIQUE RÉEL (Avec logique d'Upgrade)
    log.info(f"[PredictZones] 📖 Habits reçus: total_rounds={habits.get('total_rounds', 0) if habits else 'N/A'}, zones_keys={list(habits['zones'].keys()) if habits else 'N/A'}")
    if habits and habits.get("total_rounds", 0) > 0:
        mapping = {"top": "North", "bottom": "South", "back": "Back", "fleet": "Fleet"}
        for hz, h_name in mapping.items():
            teams = habits["zones"].get(hz, [])
            quota = quotas.get(h_name, 0)
            log.info(f"[PredictZones] Zone {hz}/{h_name}: {len(teams)} équipes historiques, quota={quota}")
            
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
                                log.info(f"[PredictZones] ⛔ Historique {hz} | Leader={leader} | Filtre anti-garbage (synergy={has_synergy}, percent={percent}%)")
                                continue

                    # Pour la flotte : limiter les renforts selon les étoiles du capital
                    if hz == "fleet":
                        cap_rarity = (enemy_index.get(leader.upper()) or enemy_index.get(leader, {})).get("rarity", 7)
                        max_reinforcements = _get_fleet_max_reinforcements(cap_rarity)
                        # Total membres = 3 vaisseaux de départ + max_reinforcements
                        valid_members = valid_members[:3 + max_reinforcements]
                        log.info(f"[PredictZones] 🚀 Flotte {leader} | Rareté={cap_rarity}★ | Max renforts={max_reinforcements} | Membres retenus={len(valid_members)}")

                    # Ajout direct et fidèle de l'équipe historique du joueur
                    log.info(f"[PredictZones] ✅ Historique {hz} | Leader={leader} | {len(valid_members)} membres | {percent}%")
                    zones[h_name].append({
                        "leader_id": leader,
                        "members_ids": valid_members,
                        "source": f"Historique ({percent}%)",
                        "target_size": expected_size if hz != "fleet" else 8
                    })
                    used_base_ids.add(leader)
                    used_base_ids.update(valid_members)
                    placed_in_zone += 1
                else:
                    log.info(f"[PredictZones] ⏭️ Historique {hz} | Leader={leader} DÉJÀ UTILISÉ")
    else:
        log.info(f"[PredictZones] ⚠️ Pas d'historique disponible (habits total_rounds={habits.get('total_rounds', 0) if habits else 'None'})")
    
    # Remplir les slots vides UNIQUEMENT avec de vraies équipes meta disponibles (pas de leftovers aléatoires)
    for zone in ["North", "South", "Back"]:
        q = quotas.get(zone, 0)
        remaining_q = max(0, q - len(zones[zone]))
        if remaining_q == 0:
            continue
        for meta_team in list(available_teams):
            if remaining_q == 0:
                break
            if meta_team["leader_id"] in used_base_ids or meta_team["leader_id"] == "USED":
                continue
            leader = meta_team["leader_id"]
            members = [m for m in meta_team["members"] if m not in used_base_ids]
            zones[zone].append({
                "leader_id": leader,
                "members_ids": members,
                "source": "Prédiction (Meta)",
                "target_size": expected_size
            })
            used_base_ids.add(leader)
            used_base_ids.update(members)
            meta_team["leader_id"] = "USED"
            remaining_q -= 1
        # Si toujours pas assez d'équipes meta connues → slots vides (plutôt qu'équipes absurdes)
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

    # BOUCHAGE DE TROUS (Hole-Filling) — UNIQUEMENT avec candidats synergiques (aucun leftover anarchique)
    leftovers = [
        m for m, data in enemy_index.items()
        if m not in used_base_ids
        and data.get("combat_type", 1) == 1
        and (data.get("relic_tier", 0) > 0 or data.get("gear_tier", 0) >= 8)
    ]
    leftovers.sort(key=lambda m: enemy_index[m].get("relic_tier", 0) * 10 + enemy_index[m].get("gear_tier", 0), reverse=True)

    for zone in ["North", "South", "Back"]:
        for t in zones[zone]:
            target = t.get("target_size", expected_size)
            leader_id = t.get("leader_id")
            if not leader_id:
                # Slot sans leader → on ne le remplit PAS (déjà source="empty")
                continue
            need = target - 1  # -1 pour le leader déjà placé
            synergy_candidates = leader_synergy_map.get(leader_id, [])
            while len(t["members_ids"]) < need:
                filler = None
                # Chercher uniquement parmi les candidats synergiques de ce leader
                for candidate in synergy_candidates:
                    if candidate in leftovers and candidate not in t["members_ids"]:
                        if candidate in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[candidate]:
                            continue
                        filler = candidate
                        leftovers.remove(candidate)
                        break
                if filler is None:
                    break  # Pas de candidat synergique dispo → on laisse l'équipe incomplète
                t["members_ids"].append(filler)
                used_base_ids.add(filler)


    # 2. FLOTTES (Synergies complètes et dédoublonnage strict des Amiraux)
    CAP_NORM = {
        "NEGOTIATOR": "CAPITALNEGOTIATOR",
        "PROFUNDITY": "CAPITALPROFUNDITY",
        "LEVIATHAN": "CAPITALLEVIATHAN",
        "EXECUTOR": "CAPITALEXECUTOR",
        "HOMEONE": "CAPITALMONCALAMARICRUISER",
        "CHIMAERA": "CAPITALCHIMAERA",
        "FINALIZER": "CAPITALFINALIZER",
        "EXECUTRIX": "CAPITALSTARDESTROYER",
        "MALEVOLENCE": "CAPITALMALEVOLENCE",
        "RADDUS": "CAPITALRADDUS",
        "ENDURANCE": "CAPITALJEDICRUISER",
    }
    # 2. FLOTTES (Dynamique BDD via fleet_tier_list / ship_counters)
    db_fleets = await get_db_meta_fleets(mode="defense")
    available_fleets = []
    for cap_id, team_data in db_fleets.items():
        norm_cap = CAP_NORM.get(cap_id, cap_id)
        if enemy_index.get(norm_cap) and enemy_index[norm_cap].get("rarity", 0) >= 5:
            score = enemy_index[norm_cap].get("relic_tier", 0) * 10 + enemy_index[norm_cap].get("gear_tier", 0)
            available_fleets.append({
                "leader_id": norm_cap,
                "members": [m for m in team_data["members"] if m != norm_cap],
                "defense": team_data.get("defense", 5),
                "score": score
            })
            
    available_fleets.sort(key=lambda x: (x["defense"], x["score"]), reverse=True)
    
    fleet_quota = quotas.get("Fleet", 1)
    remaining_fleet_q = max(0, fleet_quota - len(zones["Fleet"]))
    for _ in range(remaining_fleet_q):
        placed = False
        for f in available_fleets:
            cap = f["leader_id"]
            if cap not in used_base_ids and cap != "USED":
                cap_rarity = enemy_index.get(cap, {}).get("rarity", 7)
                max_reinforcements = _get_fleet_max_reinforcements(cap_rarity)
                max_members = 3 + max_reinforcements
                valid_members = [
                    m for m in f["members"] 
                    if m not in used_base_ids and m in enemy_index and m != cap
                ][:max_members]
                zones["Fleet"].append({
                    "leader_id": cap,
                    "members_ids": valid_members,
                    "source": "Prédiction (Meta BDD)",
                    "target_size": 1 + max_members
                })
                used_base_ids.update(valid_members)
                f["leader_id"] = "USED"
                placed = True
                break
        if not placed:
            zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": 8})

    # 2.5 Vaisseaux sans bourrage anarchique : on conserve uniquement les vaisseaux synergiques
    return zones

async def _plan_user_defense(ally_code: str, my_index: dict, quotas: dict, fmt: str, ship_base_ids: set, enemy_zones: dict = None, league: str = "KYBER") -> dict:
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
        min_gear=8
    )
    
    if not suggestions:
        return await _predict_zones(my_index, quotas, fmt, ship_base_ids)

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
    # Niveau 1 : Personnage avec synergie méta parmi les leftovers libres et viables
    # Niveau 2 : Personnage avec synergie méta réservé pour l'attaque (viable) → libération
    # Niveau 3 : Fallback désactivé (pas de personnage poubelle)
    from services.gac_attack_planner import LEAGUE_THRESHOLDS
    thresh = LEAGUE_THRESHOLDS.get(league.upper(), LEAGUE_THRESHOLDS["BRONZIUM"])
    min_g = thresh["min_gear"]
    min_r = thresh["min_rarity"]
    require_relic = thresh.get("require_g12_or_relic", False)

    def _is_viable(data: dict) -> bool:
        if not data or data.get("combat_type", 1) != 1:
            return False
        if data.get("relic_tier", 0) > 0:
            return True
        gear = data.get("gear_tier", 0)
        rarity = data.get("rarity", 0)
        if gear < min_g or rarity < min_r:
            return False
        if require_relic and gear < 12:
            return False
        return True

    leftovers_t1 = [
        m for m, data in my_index.items()
        if m not in used_base_ids
        and _is_viable(data)
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
                    # Ne pas créer de team "Leftover" aléatoire pour le joueur.
                    # On laisse le slot d'équipe Vide.
                    break
                else:
                    filler = None
                    raw_synergy = leader_synergy_map.get(leader_id, [])
                    # Prioriser les candidats avec les reliques les plus hautes (R7+ puis R5+) pour maximiser les Datacrons
                    synergy_candidates = sorted(
                        raw_synergy,
                        key=lambda c: (
                            my_index.get(c, {}).get("relic_tier", 0) >= 7,
                            my_index.get(c, {}).get("relic_tier", 0) >= 5,
                            my_index.get(c, {}).get("relic_tier", 0) * 10 + my_index.get(c, {}).get("gear_tier", 0)
                        ),
                        reverse=True
                    )

                    # Niveau 1 : synergie méta parmi les leftovers libres (et viables)
                    for candidate in synergy_candidates:
                        if candidate in leftovers and candidate not in t["members_ids"]:
                            if candidate in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[candidate]:
                                continue
                            filler = candidate
                            leftovers.remove(candidate)
                            break

                    # Niveau 2 : libérer un perso réservé pour l'attaque (synergie confirmée et viable)
                    if filler is None:
                        for candidate in synergy_candidates:
                            if (
                                candidate in my_index
                                and candidate in used_base_ids
                                and candidate not in t["members_ids"]
                                and _is_viable(my_index[candidate])
                            ):
                                if candidate in UNIT_RESTRICTIONS and leader_id not in UNIT_RESTRICTIONS[candidate]:
                                    continue
                                filler = candidate
                                used_base_ids.discard(candidate)
                                log.debug(f"[HoleFill] {candidate} libéré de l'attaque → synergie {leader_id}")
                                break

                    # Niveau 3 : fallback — désactivé pour le joueur
                    if filler is None:
                        break  # Rien à placer pour cette équipe

                    t["members_ids"].append(filler)

                if filler:
                    used_base_ids.add(filler)

    # 2. FLOTTES DU JOUEUR (Synergies complètes et dédoublonnage strict des Amiraux)
    CAP_NORM = {
        "NEGOTIATOR": "CAPITALNEGOTIATOR",
        "PROFUNDITY": "CAPITALPROFUNDITY",
        "LEVIATHAN": "CAPITALLEVIATHAN",
        "EXECUTOR": "CAPITALEXECUTOR",
        "HOMEONE": "CAPITALMONCALAMARICRUISER",
        "CHIMAERA": "CAPITALCHIMAERA",
        "FINALIZER": "CAPITALFINALIZER",
        "EXECUTRIX": "CAPITALSTARDESTROYER",
        "MALEVOLENCE": "CAPITALMALEVOLENCE",
        "RADDUS": "CAPITALRADDUS",
        "ENDURANCE": "CAPITALJEDICRUISER",
    }
    # 2. FLOTTES DU JOUEUR (Dynamique BDD via fleet_tier_list / ship_counters)
    db_fleets = await get_db_meta_fleets(mode="defense")
    available_fleets = []
    for cap_id, team_data in db_fleets.items():
        norm_cap = CAP_NORM.get(cap_id, cap_id)
        if my_index.get(norm_cap) and my_index[norm_cap].get("rarity", 0) >= 5:
            score = my_index[norm_cap].get("relic_tier", 0) * 10 + my_index[norm_cap].get("gear_tier", 0)
            available_fleets.append({
                "leader_id": norm_cap,
                "members": [m for m in team_data["members"] if m != norm_cap],
                "defense": team_data.get("defense", 5),
                "score": score
            })
            
    available_fleets.sort(key=lambda x: (x["defense"], x["score"]), reverse=True)
    
    fleet_quota = quotas.get("Fleet", 1)
    remaining_fleet_q = max(0, fleet_quota - len(zones["Fleet"]))
    for _ in range(remaining_fleet_q):
        placed = False
        for f in available_fleets:
            cap = f["leader_id"]
            if cap not in used_base_ids and cap != "USED":
                cap_rarity = my_index.get(cap, {}).get("rarity", 7)
                max_reinforcements = _get_fleet_max_reinforcements(cap_rarity)
                # 3 vaisseaux de départ + max_reinforcements selon les étoiles du capital
                max_members = 3 + max_reinforcements
                valid_members = [
                    m for m in f["members"] 
                    if m not in used_base_ids and m in my_index and m != cap
                ][:max_members]
                zones["Fleet"].append({
                    "leader_id": cap,
                    "members_ids": valid_members,
                    "source": "Prédiction (Meta BDD)",
                    "target_size": 1 + max_members  # capital + membres
                })
                used_base_ids.add(cap)
                used_base_ids.update(valid_members)
                f["leader_id"] = "USED"
                placed = True
                break
        if not placed:
            zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty", "target_size": 8})

    return zones

async def get_scout_data(enemy_ally_code: str, fmt: str, my_ally_code: str | None = None, progress_callback=None, discord_id: str | None = None) -> dict:
    clean_code = str(enemy_ally_code).replace("-", "").strip()

    # Verifier si un snapshot verrouille existe en BDD pour cet adversaire
    from database.db import get_locked_roster
    profile = await get_locked_roster(clean_code)
    if profile:
        log.info(f"[Scout] 🔒 Utilisation du profil VERROUILLE (Lock GAC) pour {clean_code}")
    else:
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
        async with get_db() as db:
            cursor = await db.execute("SELECT league FROM gac_rounds WHERE player_code = ? AND league IS NOT NULL ORDER BY id DESC LIMIT 1", (target_code,))
            row = await cursor.fetchone()
            if row and row["league"]:
                league_name = row["league"].upper()
            
    if league_name not in ["CARBONITE", "BRONZIUM", "CHROMIUM", "AURODIUM", "KYBER"]:
        league_name = "CARBONITE"
        
    quotas = get_gac_quotas(league_name, fmt)
    omicron_dict = await get_omicron_dict()
    gac_omicron_units = await get_gac_valid_omicron_units()
    zeta_dict = await get_zeta_dict()
    ship_base_ids = await get_ship_base_ids()
    enemy_index = _build_roster_index(profile.get("rosterUnit", []), omicron_dict, zeta_dict, ship_base_ids, gac_omicron_units)
    
    from services.gac_scout_analyzer import GacScoutAnalyzer
    habits = await GacScoutAnalyzer.get_defensive_habits(clean_code, fmt)
    
    enemy_zones = await _predict_zones(enemy_index, quotas, fmt, ship_base_ids, habits, league=league_name)
    
    # ── Association intelligente des Datacrons adverses aux escouades défensives ──
    try:
        attach_datacrons_to_scouted_zones(enemy_zones, profile.get("datacron", []), enemy_index)
    except Exception as e:
        log.warning(f"Erreur association Datacrons ennemis: {e}")

    # ── Intégration des slots de défense adverse MODIFIÉS MANUELLEMENT (via /gac-edit-slot) ──
    # IMPORTANT : On ne charge PAS les zones "enemy_defense" auto-sauvegardées d'un scout précédent
    # car elles écraserait l'analyse basée sur l'historique frais. On charge UNIQUEMENT
    # les slots modifiés manuellement, identifiés par la table active_manual_enemy_slots.
    if discord_id:
        from database.db import load_manual_enemy_slots
        manual_slots = await load_manual_enemy_slots(str(discord_id))
        if manual_slots:
            for zone_name, saved_teams in manual_slots.items():
                if zone_name in enemy_zones:
                    for s_team in saved_teams:
                        s_idx = s_team.get("slot_index", 1) - 1
                        if 0 <= s_idx < len(enemy_zones[zone_name]):
                            ldr = s_team.get("leader_id")
                            if ldr and ldr not in ["USED", "None", "EMPTY"]:
                                enemy_zones[zone_name][s_idx] = {
                                    "leader_id": ldr,
                                    "members_ids": s_team.get("members_ids", []),
                                    "source": "Modifié manuellement",
                                    "target_size": enemy_zones[zone_name][s_idx].get("target_size", 5)
                                }

    if my_ally_code:
        try:
            # 1. Déclenchement et attente du scraping ciblé pour la Flotte ennemie (Amiral + 3 départ + renforts)
            for f_team in enemy_zones.get("Fleet", []):
                f_cap = f_team.get("leader_id")
                if f_cap and f_cap not in ["USED", "None", "EMPTY"]:
                    f_all = [m for m in f_team.get("members_ids", []) if m and m != f_cap]
                    front_3 = f_all[:3]
                    reinforcements = f_all[3:]
                    f_d_str = ",".join(front_3)
                    f_r_str = ",".join(reinforcements) if reinforcements else ""

                    # Vérification en BDD si on a déjà des contres récents (< 7 jours) pour cette flotte
                    needs_ship_scrape = True
                    from database.db import get_db
                    import datetime
                    async with get_db() as db:
                        cursor = await db.execute(
                            "SELECT last_updated FROM ship_counters WHERE UPPER(def_capital) = UPPER(?) ORDER BY last_updated DESC LIMIT 1",
                            (f_cap,)
                        )
                        s_row = await cursor.fetchone()
                        if s_row and s_row["last_updated"]:
                            try:
                                raw_date = s_row["last_updated"]
                                if isinstance(raw_date, datetime.datetime):
                                    l_upd = raw_date.replace(tzinfo=None) if raw_date.tzinfo else raw_date
                                elif isinstance(raw_date, str):
                                    try:
                                        l_upd = datetime.datetime.fromisoformat(raw_date.replace("Z", "+00:00").replace("T", " "))
                                    except Exception:
                                        l_upd = datetime.datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                                else:
                                    l_upd = datetime.datetime.utcnow()

                                if (datetime.datetime.utcnow() - l_upd).days <= 7:
                                    needs_ship_scrape = False
                                    log.info(f"[Scout] ⚡ Contres récents déjà en BDD pour la flotte {f_cap} (dernière MAJ: {l_upd}) -> Pas de re-scraping")
                            except Exception:
                                needs_ship_scrape = True

                    if needs_ship_scrape:
                        from services.gac_ship_counters_scraper import GacShipCountersScraper
                        f_scraper = GacShipCountersScraper()
                        log.info(f"[Scout] 🚀 Scraping et attente flotte : {f_cap} (départ: [{f_d_str}], renforts: [{f_r_str}])...")
                        if progress_callback:
                            await progress_callback(f"⏳ **[■■■■■■■■□□] 80%** : Extraction swgoh.gg des contres pour {f_cap}...")
                        await f_scraper.refresh_ship_counters(f_cap, d_members=f_d_str, d_reinforcements=f_r_str)

            # 2. Personnages
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
                from database.db import get_db
                import datetime
                scraper = GacCountersScraper()
                leaders_needing_scrape = []
                async with get_db() as db:
                    for l_id, members_str in leaders_to_scrape.items():
                        if not l_id or l_id in ["USED", "None"]: continue
                        cursor = await db.execute(
                            "SELECT last_updated FROM gac_counters WHERE def_leader_id = ? AND format = ? ORDER BY last_updated DESC LIMIT 1",
                            (l_id, fmt)
                        )
                        row = await cursor.fetchone()
                        if not row:
                            leaders_needing_scrape.append(l_id)
                        else:
                            try:
                                raw_date = row["last_updated"]
                                if isinstance(raw_date, datetime.datetime):
                                    last_updated = raw_date.replace(tzinfo=None) if raw_date.tzinfo else raw_date
                                elif isinstance(raw_date, str):
                                    try:
                                        last_updated = datetime.datetime.fromisoformat(raw_date.replace("Z", "+00:00").replace("T", " "))
                                    except Exception:
                                        last_updated = datetime.datetime.strptime(raw_date, "%Y-%m-%d %H:%M:%S")
                                else:
                                    last_updated = datetime.datetime.utcnow()

                                if (datetime.datetime.utcnow() - last_updated).days > 7:
                                    leaders_needing_scrape.append(l_id)
                            except Exception:
                                leaders_needing_scrape.append(l_id)
                
                if leaders_needing_scrape and progress_callback:
                    total_sec = len(leaders_needing_scrape) * 30
                    mins, secs = divmod(total_sec, 60)
                    time_str = f"{mins} min {secs}s" if mins > 0 else f"{secs}s"
                    await progress_callback(f"⏳ **[■■■■■■■□□□] 70%** : Extraction swgoh.gg pour {len(leaders_needing_scrape)} leaders absents/expirés (≈ {time_str})...")

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
        from database.db import get_locked_roster
        my_profile = await get_locked_roster(my_clean) or await get_player(my_clean)
        if my_profile:
            my_index = _build_roster_index(my_profile.get("rosterUnit", []), omicron_dict, zeta_dict, ship_base_ids, gac_omicron_units)
            
            # ── Recharger la défense modifiée/enregistrée par le joueur depuis SQLite ──
            from database.db import load_user_defense_zones
            saved_zones = None
            if discord_id:
                saved_zones = await load_user_defense_zones(str(discord_id), "defense")
            if not saved_zones or not any(len(teams) > 0 for teams in saved_zones.values()):
                saved_zones = await load_user_defense_zones(my_clean, "defense")

            has_saved_defense = saved_zones and any(len(teams) > 0 for teams in saved_zones.values())
            
            if has_saved_defense:
                # Vérifier si toutes les unités de la défense sauvegardée sont toujours viables dans le roster
                from services.gac_attack_planner import LEAGUE_THRESHOLDS
                thresh = LEAGUE_THRESHOLDS.get(league_name.upper(), LEAGUE_THRESHOLDS["BRONZIUM"])
                min_g = thresh["min_gear"]
                min_r = thresh["min_rarity"]
                require_relic = thresh.get("require_g12_or_relic", False)

                def _is_viable_unit(uid):
                    if not uid or uid.upper() not in my_index:
                        return False
                    data = my_index[uid.upper()]
                    if data.get("combat_type", 1) == 2:
                        return True  # Flotte
                    if data.get("relic_tier", 0) > 0:
                        return True
                    gear = data.get("gear_tier", 0)
                    rarity = data.get("rarity", 0)
                    if gear < min_g or rarity < min_r:
                        return False
                    if require_relic and gear < 12:
                        return False
                    return True

                cleaned_zones = {}
                has_invalid_unit = False
                for z, teams in saved_zones.items():
                    cleaned_zones[z] = []
                    for t in teams:
                        ldr = t.get("leader_id")
                        if ldr and not _is_viable_unit(ldr):
                            has_invalid_unit = True
                            continue
                        valid_m = []
                        for m in t.get("members_ids", []):
                            if _is_viable_unit(m):
                                valid_m.append(m)
                            else:
                                has_invalid_unit = True
                        cleaned_zones[z].append({
                            "leader_id": ldr,
                            "members_ids": valid_m,
                            "slot_index": t.get("slot_index", 0),
                            "source": t.get("source", "saved")
                        })

                if has_invalid_unit:
                    log.info(f"Défense sauvegardée contenait des unités non viables. Recalcul propre de la défense pour {my_clean}...")
                    my_zones = await _plan_user_defense(my_clean, my_index, quotas, fmt, ship_base_ids, enemy_zones, league_name)
                else:
                    my_zones = cleaned_zones
            else:
                my_zones = await _plan_user_defense(my_clean, my_index, quotas, fmt, ship_base_ids, enemy_zones, league_name)

            # ── Association intelligente des Datacrons du joueur à sa défense suggérée ──
            try:
                attach_datacrons_to_scouted_zones(my_zones, my_profile.get("datacron", []), my_index)
            except Exception as e:
                log.warning(f"Erreur association Datacrons joueur: {e}")

            result["my_zones"] = my_zones
            result["my_name"] = my_profile.get("name", my_clean)
            result["my_roster_index"] = my_index

    return result


async def generate_attack_plan(discord_id: str, my_index: dict, enemy_zones: dict, fmt: str, league: str = "KYBER", enemy_roster_index: dict = None, my_datacrons: list[dict] = None) -> dict:
    """
    Génère un plan d'attaque global optimisé pour l'ensemble de la carte ennemie.
    Utilise un algorithme d'affectation globale sous contraintes (Global Matching) :
    1. Collecte tous les contres candidats pour chaque secteur ouvert/échec.
    2. Priorise l'assignation des secteurs les plus contraints (moins d'options disponibles ou choix manuel).
    3. Empêche un secteur secondaire d'accaparer un contre vital avec 0% de win_rate si un autre secteur en a besoin.
    4. Maximise le nombre total de secteurs couverts avec le meilleur taux de victoire global.
    """
    from database.db import get_used_units, get_active_sector_statuses
    from services.gac_attack_planner import get_best_counter_with_memory

    used_units = set(await get_used_units(discord_id))
    sector_statuses = await get_active_sector_statuses(discord_id)

    # 1. Collecter tous les slots actifs et leurs candidats contres
    slots_data = []

    # ─── Zone Fleet : ship counters depuis la BDD ─────────────────────────────
    fleet_slots = []
    for slot_idx, enemy_fleet in enumerate(enemy_zones.get("Fleet", []), 1):
        def_capital = enemy_fleet.get("leader_id")
        def_members = enemy_fleet.get("members_ids", [])

        if not def_capital or def_capital in ["USED", "None", "EMPTY"]:
            continue

        sec_info = sector_statuses.get(("Fleet", slot_idx), {})
        fleet_status = sec_info.get("status", "OPEN")
        fleet_offset = sec_info.get("counter_offset", 0)

        if fleet_status == "CLEARED":
            fleet_slots.append({
                "zone": "Fleet",
                "slot_index": slot_idx,
                "enemy_team": enemy_fleet,
                "counter": None,
                "win_pct": 100,
                "status": "CLEARED",
                "counter_offset": 0,
                "total_options": 0,
                "candidates": [],
            })
            continue

        # Chercher les ship counters depuis la BDD avec normalisation des IDs
        CAPITAL_MAP = {
            "NEGOTIATOR": "CAPITALNEGOTIATOR",
            "PROFUNDITY": "CAPITALPROFUNDITY",
            "LEVIATHAN": "CAPITALLEVIATHAN",
            "EXECUTOR": "CAPITALEXECUTOR",
            "HOMEONE": "CAPITALMONCALAMARICRUISER",
            "CHIMAERA": "CAPITALCHIMAERA",
            "FINALIZER": "CAPITALFINALIZER",
            "EXECUTRIX": "CAPITALSTARDESTROYER",
            "MALEVOLENCE": "CAPITALMALEVOLENCE",
            "RADDUS": "CAPITALRADDUS",
            "ENDURANCE": "CAPITALJEDICRUISER",
        }
        norm_cap = CAPITAL_MAP.get(def_capital.upper(), def_capital.upper())

        try:
            from database.db import get_ship_counters as _get_ship_counters
            ship_counters_raw = await _get_ship_counters(norm_cap)
            if not ship_counters_raw and norm_cap != def_capital:
                ship_counters_raw = await _get_ship_counters(def_capital)
        except Exception as _e:
            log.warning(f"[AttackPlan] Erreur get_ship_counters({norm_cap}): {_e}")
            ship_counters_raw = []

        # IDs des vaisseaux du joueur disponibles
        player_ship_ids = {
            bid.upper() for bid, udata in my_index.items()
            if udata.get("combat_type", 1) == 2
        }
        used_units_fleet = {u.upper() for u in await get_used_units(discord_id)} if discord_id else set()

        converted_fleet = []
        for sc in ship_counters_raw:
            atk_cap = (sc.get("atk_capital") or "").upper()
            atk_members = [m.upper() for m in sc.get("atk_members_ids", []) if m]
            
            # Le joueur DOIT posséder le vaisseau amiral d'attaque
            if not atk_cap or atk_cap not in player_ship_ids or atk_cap in used_units_fleet:
                continue

            # Front ships (les 3 vaisseaux de départ : 100% obligatoires)
            front_ships = atk_members[:3]
            if len(front_ships) < 3 or not all(s in player_ship_ids and s not in used_units_fleet for s in front_ships):
                continue

            # Renforts (slots 4 à 7) : souples, ne garder que ceux possédés (les manquants restent vides)
            reinforcements_owned = [s for s in atk_members[3:] if s in player_ship_ids and s not in used_units_fleet]
            final_members = front_ships + reinforcements_owned

            converted_fleet.append({
                "atk_leader_id":   atk_cap,
                "atk_members_ids": final_members,
                "win_pct":         sc.get("win_pct", 0.0),
                "seen":            sc.get("seen", 0),
                "avg_banners":     sc.get("avg_banners", 0.0),
                "def_leader_id":   norm_cap,
                "def_members_ids": def_members,
            })

        converted_fleet.sort(key=lambda x: (x.get("win_pct", 0), x.get("seen", 0)), reverse=True)
        best_fleet = converted_fleet[fleet_offset] if fleet_offset < len(converted_fleet) else (converted_fleet[0] if converted_fleet else None)

        fleet_slots.append({
            "zone": "Fleet",
            "slot_index": slot_idx,
            "enemy_team": enemy_fleet,
            "counter": best_fleet,
            "win_pct": best_fleet.get("win_pct", 0) if best_fleet else 0,
            "status": fleet_status,
            "counter_offset": fleet_offset,
            "total_options": len(converted_fleet),
            "candidates": converted_fleet,
        })
    # ─────────────────────────────────────────────────────────────────────────────

    for zone, teams in enemy_zones.items():
        if zone == "Fleet":
            continue

        for slot_idx, enemy_team in enumerate(teams, 1):
            def_leader = enemy_team.get("leader_id")
            def_members = enemy_team.get("members_ids", [])

            if not def_leader or def_leader in ["USED", "None", "EMPTY"]:
                continue

            sec_info = sector_statuses.get((zone, slot_idx), {})
            status = sec_info.get("status", "OPEN")
            offset = sec_info.get("counter_offset", 0)

            if status == "CLEARED":
                slots_data.append({
                    "zone": zone,
                    "slot_index": slot_idx,
                    "enemy_team": enemy_team,
                    "counter": None,
                    "win_pct": 100,
                    "status": "CLEARED",
                    "counter_offset": 0,
                    "total_options": 0,
                    "candidates": []
                })
                continue

            # Obtenir tous les contres disponibles pour ce roster (sans exclure used_units globalement pour l'instant)
            counters = await get_best_counter_with_memory(
                def_leader_id=def_leader,
                def_members_ids=def_members,
                format_type=fmt,
                my_roster_index=my_index,
                excluded_chars=used_units,
                league=league,
                enemy_roster_index=enemy_roster_index
            )

            slots_data.append({
                "zone": zone,
                "slot_index": slot_idx,
                "enemy_team": enemy_team,
                "counter": None,
                "win_pct": 0,
                "status": status,
                "counter_offset": offset,
                "total_options": len(counters),
                "candidates": counters
            })

    # 2. Ordonner l'assignation globale par niveau de contrainte RÉELLE du roster
    # Calculer pour chaque slot le nombre de contres 100% PRÊTS dans le roster du joueur.
    # Les secteurs qui ont le MOINS d'options réalisables dans le roster (ex: 1 seule équipe possible)
    # sont traités EN PREMIER pour ne pas se faire "voler" leur seul contre par un secteur qui a plein d'alternatives !
    pending_slots = [s for s in slots_data if s["status"] != "CLEARED"]

    for s in pending_slots:
        ready_count = len([c for c in s["candidates"] if c.get("all_members_ready") or c.get("roster_availability", 0) >= 0.8])
        s["ready_candidates_count"] = ready_count if ready_count > 0 else len(s["candidates"])

    pending_slots.sort(key=lambda s: (
        0 if s["counter_offset"] > 0 else 1,            # Choix manuels du joueur en premier
        s["ready_candidates_count"],                    # Moins de contres VRAIMENT DISPOS dans le roster en premier !
        -max([c.get("win_pct", 0) for c in s["candidates"]], default=0) # Meilleurs win rate max
    ))

    # 3. Affectation optimisée (STRICTEMENT SANS DOUBLON DE PERSONNAGE)
    assigned_units = set(used_units)

    for slot in pending_slots:
        candidates = slot["candidates"]
        def_leader = slot["enemy_team"].get("leader_id")
        def_members = slot["enemy_team"].get("members_ids", [])
        offset = slot["counter_offset"]

        # 1. Filtrer les candidats pré-calculés qui n'utilisent AUCUN perso déjà assigné
        available_candidates = [
            c for c in candidates
            if not set([c["atk_leader_id"]] + c.get("atk_members_ids", [])).intersection(assigned_units)
        ]

        # 2. Si aucun candidat pré-calculé n'est totalement libre, interroger dynamiquement les contres alternatifs
        # en excluant formellement la totalité des unités déjà assignées sur d'autres secteurs
        if not available_candidates and def_leader and def_leader not in ["USED", "None", "EMPTY"]:
            fresh_counters = await get_best_counter_with_memory(
                def_leader_id=def_leader,
                def_members_ids=def_members,
                format_type=fmt,
                my_roster_index=my_index,
                excluded_chars=assigned_units,
                league=league,
                enemy_roster_index=enemy_roster_index
            )
            available_candidates = fresh_counters

        chosen_c = None
        if available_candidates:
            target_idx = offset if offset < len(available_candidates) else 0

            # ── Règle anti-gaspillage des Légendes Galactiques (GL Overkill) ──
            # Si l'équipe ennemie n'est PAS une GL, privilégier les contres non-GL à haut win rate
            GL_UNITS = {"SITHPALPATINE", "SUPREMELEADERKYLOREN", "JEDIMASTERKENOBI", "GLREY", "LORDVADER", "JEDIMASTERLUKE", "JABBATHEHUTT", "AHSOKATANO", "GLAHSOKATANO", "GLLEIA", "LEIAORGANA", "LEIAORGANAGL"}
            def_leader_id = (def_leader or "").upper()
            if def_leader_id not in GL_UNITS and offset == 0:
                available_candidates.sort(key=lambda c: (
                    0 if c["atk_leader_id"].upper() not in GL_UNITS else 1,
                    -c.get("win_pct", 0)
                ))

            chosen_c = available_candidates[target_idx]
            if chosen_c.get("win_pct", 0) == 0:
                positive_candidates = [c for c in available_candidates if c.get("win_pct", 0) > 0]
                if positive_candidates:
                    chosen_c = positive_candidates[0]

            # Vérification stricte anti-doublon avant validation
            atk_members = list(chosen_c.get("atk_members_ids", []))
            
            # ── Compléter les équipes incomplètes à 5 membres en 5v5 (ex: Gungans 4/5) ──
            from services.gac_attack_planner import RECOGNIZED_SOLO_LEADERS
            ldr_upper = chosen_c["atk_leader_id"].upper()
            if fmt == "5v5" and len(atk_members) < 4 and ldr_upper not in RECOGNIZED_SOLO_LEADERS and len(atk_members) >= 2:
                FACTION_FILLERS = {
                    "BOSSNASS": ["GUNGANPHALANX", "GUNGANBOOMADIER", "CAPTAINTARPALS", "JARJARBINKS"],
                    "GRIEVOUS": ["DROIDEKA", "B2SUPERBATTLEDROID", "MAGNAGUARD", "B1BATTLEDROIDV2", "STAP"],
                    "VEERS": ["DARKTROOPER", "COLONELSTARCK", "ADMIRALPIETT", "RANGETROOPER", "MOFFGIDEONS1"],
                    "IDENVERSIOEMPIRE": ["MAGMATROOPER", "DEATHTROOPER", "STORMTROOPER", "SCOUTTROOPER", "SNOWTROOPER"],
                    "COMMANDERLUKESKYWALKER": ["CHEWBACCALEGENDARY", "HANSOLO", "C3POLEGENDARY", "CHIRRUTIMWE", "BAZEMALBUS"],
                    "HEROAMIRAL": ["KAPEX", "CT7567", "CC2224", "CT210408", "CT5555", "ARCTROOPER501ST"],
                    "GEONOSIANBROODALPHA": ["GEONOSIANSOLDIER", "GEONOSIANSPY", "POGGLETHELESSER", "SUNFAC"],
                    "PADMEAMIDALA": ["JEDIKNIGHTANAKIN", "GENERALKENOBI", "AHSOKATANO", "C3POLEGENDARY", "BARRISSOFFEE"],
                    "FINN": ["REYJEDITRAINING", "POE", "BB8", "RESISTANCETROOPER", "AMILYNHOLDO"],
                    "DARTHTRAYA": ["DARTHNIHILUS", "DARTHSION", "SAVAGEOPRESS", "TALON", "DARTHBANE"],
                }
                candidates_pool = FACTION_FILLERS.get(ldr_upper, [])
                for f_unit in candidates_pool:
                    if f_unit in my_index and f_unit not in assigned_units and f_unit not in atk_members and f_unit != ldr_upper:
                        f_data = my_index[f_unit]
                        if f_data.get("combat_type", 1) == 1 and (f_data.get("relic_tier", 0) > 0 or f_data.get("gear_tier", 0) >= 8):
                            atk_members.append(f_unit)
                            log.info(f"Équipe 5v5 complétée pour {ldr_upper} avec {f_unit}")
                            if len(atk_members) == 4:
                                break
                chosen_c["atk_members_ids"] = atk_members

            atk_units = set([chosen_c["atk_leader_id"]] + atk_members)
            if not atk_units.intersection(assigned_units):
                assigned_units.update(atk_units)
            else:
                chosen_c = None

        if chosen_c:
            slot["counter"] = chosen_c
            slot["win_pct"] = chosen_c.get("win_pct", 0)
        else:
            slot["counter"] = None
            slot["win_pct"] = 0

    # 3.5 Pass d'optimisation / Recomposition pour couvrir les slots restés sans contre
    for slot in pending_slots:
        if slot["counter"] is not None:
            continue

        def_leader = slot["enemy_team"].get("leader_id")
        def_members = slot["enemy_team"].get("members_ids", [])
        if not def_leader or def_leader in ["USED", "None", "EMPTY"]:
            continue

        # Chercher si un autre slot a un contre qui conviendrait à CE slot et qui peut céder sa place
        for other_slot in pending_slots:
            if other_slot["counter"] is None or other_slot == slot:
                continue

            c_assigned = other_slot["counter"]
            assigned_team = set([c_assigned["atk_leader_id"]] + c_assigned.get("atk_members_ids", []))
            
            # Vérifier si d'autres contres valides existent pour other_slot sans c_assigned
            free_units = assigned_units - assigned_team
            alt_counters = [
                c for c in other_slot["candidates"]
                if not set([c["atk_leader_id"]] + c.get("atk_members_ids", [])).intersection(free_units | used_units)
                and c["atk_leader_id"] != c_assigned["atk_leader_id"]
            ]
            
            if not alt_counters:
                continue

            # Vérifier si c_assigned est un contre valide pour notre slot non-couvert !
            slot_counters = await get_best_counter_with_memory(
                def_leader_id=def_leader,
                def_members_ids=def_members,
                format_type=fmt,
                my_roster_index=my_index,
                excluded_chars=free_units | used_units,
                league=league,
                enemy_roster_index=enemy_roster_index
            )
            
            c_assigned_units = set([c_assigned["atk_leader_id"]] + c_assigned.get("atk_members_ids", []))
            # Filtrer les alt_counters pour interdire formellement TOUT perso présent dans c_assigned
            valid_alt_counters = [
                c for c in alt_counters
                if not set([c["atk_leader_id"]] + c.get("atk_members_ids", [])).intersection(c_assigned_units)
            ]
            if not valid_alt_counters:
                continue

            can_swap = any(sc["atk_leader_id"] == c_assigned["atk_leader_id"] for sc in slot_counters)
            if can_swap:
                alt_c = valid_alt_counters[0]
                other_slot["counter"] = alt_c
                other_slot["win_pct"] = alt_c.get("win_pct", 0)
                
                slot["counter"] = c_assigned
                slot["win_pct"] = c_assigned.get("win_pct", 0)
                
                alt_units = set([alt_c["atk_leader_id"]] + alt_c.get("atk_members_ids", []))
                assigned_units = (free_units | alt_units | c_assigned_units)
                log.info(f"[AttackPlanSwap] Échange effectué entre {other_slot['zone']} #{other_slot['slot_index']} et {slot['zone']} #{slot['slot_index']}")
                break

    # 3.9 Vérification finale d'intégrité anti-doublon absolue
    final_assigned = set(used_units)
    for s in slots_data:
        c = s.get("counter")
        if not c:
            continue
        c_team = set([c["atk_leader_id"]] + c.get("atk_members_ids", []))
        if c_team.intersection(final_assigned):
            conflict = c_team.intersection(final_assigned)
            log.warning(f"[AttackPlan] Doublon résiduel détecté sur {s['zone']} #{s['slot_index']} ({conflict}). Annulation du contre.")
            s["counter"] = None
            s["win_pct"] = 0
        else:
            final_assigned.update(c_team)

    # 4. Reconstruire l'attack_plan groupé par zone et trié par slot_index d'origine
    attack_plan = {}
    slots_by_zone = {}
    
    for slot in slots_data:
        z = slot["zone"]
        if z not in slots_by_zone:
            slots_by_zone[z] = []
        
        slots_by_zone[z].append({
            "slot_index": slot["slot_index"],
            "enemy_team": slot["enemy_team"],
            "counter": slot["counter"],
            "win_pct": slot["win_pct"],
            "status": slot["status"],
            "counter_offset": slot["counter_offset"],
            "total_options": slot["total_options"]
        })

    for z in ["North", "South", "Back"]:
        if z in slots_by_zone:
            slots_by_zone[z].sort(key=lambda s: s["slot_index"])
            attack_plan[z] = slots_by_zone[z]

    # Ajouter la zone Fleet (ship counters)
    if fleet_slots:
        fleet_slots.sort(key=lambda s: s["slot_index"])
        attack_plan["Fleet"] = fleet_slots

    # ── Association intelligente des Datacrons d'Attaque du Joueur ──
    try:
        if not my_datacrons and discord_id:
            from database.db import get_db
            async with get_db() as db:
                cursor = await db.execute("SELECT ally_code FROM players WHERE discord_id = ?", (str(discord_id),))
                row = await cursor.fetchone()
                if row and row["ally_code"]:
                    p_code = str(row["ally_code"]).replace("-", "").strip()
                    from database.db import get_locked_roster
                    p_prof = await get_locked_roster(p_code) or await get_player(p_code)
                    if p_prof:
                        my_datacrons = p_prof.get("datacron", [])
        if my_datacrons:
            attach_datacrons_to_attack_plan(attack_plan, my_datacrons, my_index)
    except Exception as e:
        log.warning(f"Erreur association Datacrons d'attaque: {e}")

    return attack_plan



