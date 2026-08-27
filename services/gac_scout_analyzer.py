import json
import logging
from database.db import get_db
from services.gac_meta import GAC_FLEETS

logger = logging.getLogger("gac_scout_analyzer")

class GacScoutAnalyzer:
    @staticmethod
    async def get_defensive_habits(ally_code: str, format_type: str = '5v5') -> dict:
        """
        Analyse les habitudes défensives d'un joueur en extrayant ses vrais matchs de défense
        depuis la base de données (gac_matches et gac_rounds).
        Retourne un dictionnaire structuré par zone (top, bottom, back, fleet).
        """
        clean_code = str(ally_code).replace("-", "").strip()
        async with get_db() as db:
            # 1. Vérifier s'il y a des rounds pour ce joueur dans le format demandé (sinon fallback autre format)
            cur = await db.execute(
                "SELECT COUNT(*) FROM gac_rounds WHERE player_code = ? AND format = ?",
                (clean_code, format_type)
            )
            r_cnt = await cur.fetchone()
            total_rounds = r_cnt[0] if r_cnt else 0
            
            effective_format = format_type
            if total_rounds == 0:
                cur = await db.execute(
                    "SELECT COUNT(*), format FROM gac_rounds WHERE player_code = ? GROUP BY format ORDER BY COUNT(*) DESC LIMIT 1",
                    (clean_code,)
                )
                r_fallback = await cur.fetchone()
                if r_fallback and r_fallback[0]:
                    total_rounds = r_fallback[0]
                    effective_format = r_fallback[1]
                    logger.info(f"⚠️ Pas de rounds {format_type} pour {clean_code} — fallback sur {effective_format} ({total_rounds} rounds)")

            if total_rounds == 0:
                logger.info(f"[Analyzer] 0 round trouvé pour {clean_code}")
                return {"total_rounds": 0, "zones": {"top": [], "bottom": [], "back": [], "fleet": []}}

            # 2. Récupérer le threshold des 3 derniers rounds
            cur = await db.execute(
                """
                SELECT MIN(season_id || '-' || CAST(round_number AS TEXT)) FROM (
                    SELECT season_id, round_number FROM gac_rounds 
                    WHERE player_code = ? AND format = ?
                    ORDER BY season_id DESC, round_number DESC LIMIT 3
                ) AS sub
                """,
                (clean_code, effective_format)
            )
            t_row = await cur.fetchone()
            threshold_val = t_row[0] if t_row and t_row[0] else ""

            # 3. Récupérer les équipes terrestres de défense
            query_scraped_land = """
                SELECT 
                    m.defender_team,
                    COALESCE(m.zone, 'unknown') as zone,
                    COUNT(DISTINCT r.id) as frequency,
                    MAX(r.season_id || '-' || CAST(r.round_number AS TEXT)) as last_seen_round
                FROM gac_matches m
                JOIN gac_rounds r ON m.round_id = r.id
                WHERE (m.is_attack = FALSE OR m.is_attack = 0 OR m.is_attack IS FALSE)
                  AND r.format = ?
                  AND r.player_code = ?
                  AND (m.zone IS NULL OR m.zone != 'fleet')
                  AND NOT (m.defender_team LIKE '%CAPITAL%')
                GROUP BY m.defender_team, COALESCE(m.zone, 'unknown')
            """
            
            # 4. Récupérer les flottes de défense (tous formats confondus)
            query_scraped_fleet = """
                SELECT 
                    m.defender_team,
                    'fleet' as zone,
                    COUNT(DISTINCT r.id) as frequency,
                    MAX(r.season_id || '-' || CAST(r.round_number AS TEXT)) as last_seen_round
                FROM gac_matches m
                JOIN gac_rounds r ON m.round_id = r.id
                WHERE (m.is_attack = FALSE OR m.is_attack = 0 OR m.is_attack IS FALSE)
                  AND r.player_code = ?
                  AND (m.zone = 'fleet' OR m.defender_team LIKE '%CAPITAL%')
                GROUP BY m.defender_team
            """

            cur = await db.execute(query_scraped_land, (effective_format, clean_code))
            scraped_land_rows = await cur.fetchall()

            cur = await db.execute(query_scraped_fleet, (clean_code,))
            scraped_fleet_rows = await cur.fetchall()

            logger.info(f"[Analyzer] 🎯 {len(scraped_land_rows)} équipes terrestres et {len(scraped_fleet_rows)} flottes trouvées en BDD pour {clean_code} ({total_rounds} rounds)")

            def _calc_score(r):
                freq = r["frequency"]
                lsr = r.get("last_seen_round") or ""
                bonus = 10000 if (threshold_val and lsr >= threshold_val) else 0
                return (freq * 10) + bonus

            scraped_land_rows = sorted(scraped_land_rows, key=_calc_score, reverse=True)
            scraped_fleet_rows = sorted(scraped_fleet_rows, key=_calc_score, reverse=True)
            scraped_rows = scraped_land_rows + scraped_fleet_rows

            land_teams = []
            fleet_teams = []
            
            habits = {
                "total_rounds": total_rounds,
                "zones": {
                    "top": [],
                    "bottom": [],
                    "back": [],
                    "fleet": fleet_teams
                }
            }
            
            for r_row in scraped_rows:
                try:
                    raw_dt = r_row["defender_team"]
                    members = json.loads(raw_dt) if isinstance(raw_dt, str) else list(raw_dt)
                except Exception:
                    members = []
                    
                if not members:
                    continue
                    
                leader_id = str(members[0]).upper()
                members_ids = [str(m).upper() for m in members[1:]]
                freq = r_row["frequency"]
                percent = round((freq / total_rounds) * 100, 1)
                zone_val = str(r_row.get("zone", "unknown")).lower()
                
                is_fleet = leader_id in GAC_FLEETS or "CAPITAL" in leader_id
                
                if format_type == "3v3" and not is_fleet and len(members) > 3:
                    continue
                if format_type == "5v5" and not is_fleet and len(members) > 5:
                    continue
                
                team_info = {
                    "leader_id": leader_id,
                    "members": members_ids,
                    "frequency": freq,
                    "percent": percent
                }
                
                if is_fleet:
                    fleet_teams.append(team_info)
                else:
                    if zone_val in ["top", "bottom", "back"]:
                        habits["zones"][zone_val].append(team_info)
                    else:
                        land_teams.append(team_info)
                        
            # Répartir les équipes terrestres (round-robin si zone inconnue)
            zones_cycle = ["top", "bottom", "back"]
            for idx, team in enumerate(land_teams):
                zone_name = zones_cycle[idx % 3]
                habits["zones"][zone_name].append(team)
                
            return habits
