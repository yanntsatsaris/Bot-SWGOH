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
        league_id = last_season.get("league", 1)
        league_name = LEAGUE_MAP.get(league_id, "CARBONITE")
        
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
        # Convertir raw roster en index pour detect_meta_teams
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
            })
            
        enemy_index = _build_roster_index(roster)
        detected_teams = _detect_enemy_meta_teams(enemy_index, fmt)
        
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
                    team_idx += 1
                else:
                    zones[zone].append({"leader_id": None, "members_ids": [], "source": "empty"})
                    
        # TODO: Flottes (Fleet) - pour l'instant on laisse vide ou on met l'Executor si possédé
        fleet_quota = quotas.get("Fleet", 1)
        # On va chercher les vaisseaux meta plus tard, on met juste un slot vide
        for _ in range(fleet_quota):
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
