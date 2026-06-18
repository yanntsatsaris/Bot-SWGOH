"""
services/scouting.py — Moteur de Scouting Hybride pour la GAC
"""
import logging
from database.db import get_db
from services.comlink import get_player
from utils.gac_config import get_gac_quotas
from services.gac_counter_engine import _build_roster_index, _detect_enemy_meta_teams, _is_gac_ready

log = logging.getLogger(__name__)

# Mapping des leagues SWGOH API
LEAGUE_MAP = {
    1: "CARBONITE",
    2: "BRONZIUM",
    3: "CHROMIUM",
    4: "AURODIUM",
    5: "KYBER"
}

_HARDCODED_FLEETS = {
    "CAPITALLEVIATHAN": ["CAPITALLEVIATHAN", "SITHFIGHTER", "SITHBOMBER", "FURYCLASSINTERCEPTOR", "MKVIINTERCEPTOR", "EBONHAWK", "SITHASSASSIN"],
    "CAPITALEXECUTOR": ["CAPITALEXECUTOR", "HOUNDSTOOTH", "RAZORCREST", "XANADUBLOOD", "IG2000", "SLAVE1", "EBONHAWK", "TIEFIGHTER"],
    "CAPITALPROFUNDITY": ["CAPITALPROFUNDITY", "MILLENNIUMFALCON", "OUTRIDER", "YWINGREBEL", "GHOST", "PHANTOM2", "CASSIANSUWING", "BISTANSUEING"],
    "CAPITALNEGOTIATOR": ["CAPITALNEGOTIATOR", "JEDISTARFIGHTERANAKIN", "UMBARANSTARFIGHTER", "JEDISTARFIGHTERAHSOKATANO", "BTLB_YWING", "JEDISTARFIGHTERPLOKOON", "ARC170CLONESERGEANT", "ARC170REX"],
    "CAPITALMALEVOLENCE": ["CAPITALMALEVOLENCE", "VULTUREDROID", "HYENABOMBER", "GEONOSIANSTARFIGHTERSUNFAC", "GEONOSIANSTARFIGHTERSPY", "GEONOSIANSTARFIGHTER", "IG2000"],
    "CAPITALCHIMAERA": ["CAPITALCHIMAERA", "TIEADVANCED", "TIEBOMBER", "TIEDEFENDER", "TIEINTERCEPTOR", "TIEFIGHTER", "GAUNTLETSTARFIGHTER", "EMPERORSSHUTTLE"],
    "CAPITALSTARDESTROYER": ["CAPITALSTARDESTROYER", "TIEADVANCED", "TIEBOMBER", "TIEDEFENDER", "TIEINTERCEPTOR", "TIEFIGHTER", "GAUNTLETSTARFIGHTER", "EMPERORSSHUTTLE"],
    "CAPITALFINALIZER": ["CAPITALFINALIZER", "KYLORENSCOMMANDSHUTTLE", "TIESILENCER", "FIRSTORDERSPECIALFORCESTIEFIGHTER", "FIRSTORDERTIEFIGHTER", "HOUNDSTOOTH"],
    "CAPITALRADDUS": ["CAPITALRADDUS", "REYSMILLENNIUMFALCON", "RESISTANCEYWING", "POE_XWING", "RESISTANCE_XWING", "EBOE_XWING"],
}

async def get_scout_data(enemy_ally_code: str, fmt: str) -> dict:
    """
    Récupère ou génère les données de défense d'un ennemi pour le scouting.
    """
    clean_code = str(enemy_ally_code).replace("-", "").strip()
    profile = await get_player(clean_code)
    
    if not profile:
        raise ValueError(f"Profil introuvable pour {clean_code}")

    enemy_name = profile.get("name", clean_code)
    
    # Extraction de la ligue
    league_name = "CARBONITE"
    season_status = profile.get("seasonStatus", [])
    if season_status:
        last_season = season_status[-1]
        league_val = last_season.get("league", "CARBONITE")
        if isinstance(league_val, str):
            league_name = league_val.split("_")[-1].upper()
        else:
            league_name = LEAGUE_MAP.get(league_val, "CARBONITE")
            
    # Fallback propre si la ligue est inconnue
    if league_name not in ["CARBONITE", "BRONZIUM", "CHROMIUM", "AURODIUM", "KYBER"]:
        league_name = "CARBONITE"
        
    quotas = get_gac_quotas(league_name, fmt)
    
    # 1. Vérification de l'historique local
    historic_defenses = await _get_history(clean_code, fmt)
    
    # On structure les zones
    zones = {
        "North": [],
        "South": [],
        "Back": [],
        "Fleet": []
    }
    
    source = "Prédictive (Basé sur le Roster)"
    
    if historic_defenses:
        source = "Historique Guilde"
        for d in historic_defenses:
            zone = d["zone"]
            if zone in zones:
                zones[zone].append({
                    "leader_id": d["leader_id"],
                    "members_ids": d["members_ids"].split(","),
                    "source": "history"
                })
    else:
        # 2. Prédiction basée sur le roster
        raw_roster = profile.get("rosterUnit", [])
        roster = []
        for unit in raw_roster:
            def_id = unit.get("definitionId", "")
            base_id = def_id.split(":")[0] if ":" in def_id else def_id
            raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
            relic_tier = max(0, raw_relic - 2) if raw_relic >= 2 else 0
            roster.append({
                "base_id": base_id,
                "gear_tier": unit.get("currentTier", 0),
                "relic_tier": relic_tier,
                "rarity": unit.get("currentRarity", 0),
            })
            
        enemy_index = _build_roster_index(roster)
        detected_teams = _detect_enemy_meta_teams(enemy_index, fmt)
        
        # On va garder une liste des personnages déjà utilisés
        used_base_ids = set()
        
        # Répartition naïve des équipes détectées selon les quotas
        team_idx = 0
        for zone in ["North", "South", "Back"]:
            q = quotas.get(zone, 0)
            for _ in range(q):
                if team_idx < len(detected_teams):
                    t = detected_teams[team_idx]
                    zones[zone].append({
                        "leader_id": t["leader_id"],
                        "members_ids": t["members_base_ids"],
                        "source": "predictive"
                    })
                    used_base_ids.update(t["members_base_ids"])
                    team_idx += 1
                else:
                    # On marque comme à remplir plus tard
                    zones[zone].append({"leader_id": None, "members_ids": [], "source": "empty"})
                    
        # Système de remplissage pour les slots vides (GAC Fill)
        # On trie le roster par relic_tier puis gear_tier pour avoir les plus forts restants
        roster.sort(key=lambda x: (x["relic_tier"], x["gear_tier"]), reverse=True)
        remaining_chars = [u["base_id"] for u in roster if u["base_id"] not in used_base_ids and not u["base_id"].startswith("CAPITAL")]
        
        team_size = 3 if fmt == "3v3" else 5
        
        for zone in ["North", "South", "Back"]:
            for team in zones[zone]:
                if team["leader_id"] is None:
                    # Remplir avec une team générique depuis remaining_chars
                    if len(remaining_chars) >= team_size:
                        new_team = remaining_chars[:team_size]
                        remaining_chars = remaining_chars[team_size:]
                        team["leader_id"] = new_team[0]
                        team["members_ids"] = new_team
                        team["source"] = "predictive_fill"
                    
        # Flottes
        fleet_quota = quotas.get("Fleet", 1)
        detected_fleets = []
        for cap_id, ships in _HARDCODED_FLEETS.items():
            if enemy_index.get(cap_id):
                cap = enemy_index[cap_id]
                if cap.get("rarity", 0) >= 5: # Vaisseau mère au moins 5 étoiles
                    detected_fleets.append({
                        "leader_id": cap_id,
                        "members_ids": ships
                    })
                    
        # On remplit les slots de flotte
        fleet_idx = 0
        for _ in range(fleet_quota):
            if fleet_idx < len(detected_fleets):
                zones["Fleet"].append({
                    "leader_id": detected_fleets[fleet_idx]["leader_id"],
                    "members_ids": detected_fleets[fleet_idx]["members_ids"],
                    "source": "predictive"
                })
                fleet_idx += 1
            else:
                zones["Fleet"].append({"leader_id": None, "members_ids": [], "source": "empty"})

    return {
        "enemy_name": enemy_name,
        "league": league_name,
        "format": fmt,
        "source": source,
        "zones": zones,
        "quotas": quotas
    }


async def _get_history(enemy_code: str, fmt: str) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute("""
            SELECT zone, leader_id, members_ids 
            FROM gac_history 
            WHERE enemy_id = ? AND format = ?
            ORDER BY date_scanned DESC
        """, (enemy_code, fmt))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]
