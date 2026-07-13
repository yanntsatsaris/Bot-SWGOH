import logging
from database.db import get_db

logger = logging.getLogger("gac_scout_analyzer")

class GacScoutAnalyzer:
    @staticmethod
    async def get_defensive_habits(ally_code: str, format_type: str = '5v5') -> dict:
        """
        Analyse les habitudes défensives d'un joueur.
        Retourne un dictionnaire groupé par zone (Top, Bottom, Back, Fleet).
        Si aucune donnée n'est trouvée dans gac_round_teams, interroge gac_matches
        (données issues du scraping de swgoh.gg) comme fallback.
        """
        async with get_db() as db:
            # 1. On cherche toutes les équipes de défense dans gac_round_teams (saisie manuelle/brackets)
            query = """
                SELECT t.zone, t.leader_id, t.members_ids, COUNT(*) as frequency
                FROM gac_round_teams t
                JOIN gac_rounds r ON t.round_id = r.id
                WHERE t.side = 'defense'
                  AND r.format = ?
                  AND ((r.player_code = ? AND t.owner = 'player') OR (r.opponent_code = ? AND t.owner = 'opponent'))
                GROUP BY t.zone, t.leader_id, t.members_ids
                ORDER BY t.zone, frequency DESC
            """
            async with db.execute(query, (format_type, ally_code, ally_code)) as cur:
                rows = await cur.fetchall()

            # On compte le nombre total de rounds où le joueur a joué en défense dans ce format dans gac_round_teams
            count_query = """
                SELECT COUNT(DISTINCT r.id) as total_rounds
                FROM gac_rounds r
                JOIN gac_round_teams t ON t.round_id = r.id
                WHERE t.side = 'defense'
                  AND r.format = ?
                  AND ((r.player_code = ? AND t.owner = 'player') OR (r.opponent_code = ? AND t.owner = 'opponent'))
            """
            async with db.execute(count_query, (format_type, ally_code, ally_code)) as cur:
                count_row = await cur.fetchone()
                total_rounds = count_row[0] if count_row else 0

        # 2. Si aucune donnée dans gac_round_teams, on interroge gac_matches (données scrapées)
        if total_rounds == 0:
            async with get_db() as db:
                async with db.execute(
                    "SELECT COUNT(*) FROM gac_rounds WHERE player_code = ? AND format = ?",
                    (ally_code, format_type)
                ) as cur:
                    row = await cur.fetchone()
                    total_rounds = row[0] if row else 0
                    
                if total_rounds > 0:
                    query_scraped = """
                        SELECT m.defender_team, COUNT(DISTINCT r.id) as frequency
                        FROM gac_matches m
                        JOIN gac_rounds r ON m.round_id = r.id
                        WHERE m.is_attack = 0
                          AND r.format = ?
                          AND r.player_code = ?
                        GROUP BY m.defender_team
                        ORDER BY frequency DESC
                    """
                    async with db.execute(query_scraped, (format_type, ally_code)) as cur:
                        scraped_rows = await cur.fetchall()
                        
                    # Extraire et séparer terre/flottes
                    land_teams = []
                    fleet_teams = []
                    
                    import json
                    from services.gac_meta import GAC_FLEETS
                    
                    for r_row in scraped_rows:
                        try:
                            members = json.loads(r_row["defender_team"])
                        except:
                            members = []
                            
                        if not members:
                            continue
                            
                        leader_id = members[0]
                        members_ids = members[1:]
                        freq = r_row["frequency"]
                        percent = round((freq / total_rounds) * 100, 1)
                        
                        is_fleet = leader_id in GAC_FLEETS or "CAPITAL" in leader_id
                        
                        # Sécurité absolue : ignorer les équipes qui ne respectent pas la taille du format (ex: équipes de 4 ou 5 personnages taggées par erreur en 3v3)
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
                            land_teams.append(team_info)
                            
                    habits = {
                        "total_rounds": total_rounds,
                        "zones": {
                            "top": [],
                            "bottom": [],
                            "back": [],
                            "fleet": fleet_teams
                        }
                    }
                    
                    # Répartir les équipes terrestres de manière équitable (round-robin)
                    zones_cycle = ["top", "bottom", "back"]
                    for idx, team in enumerate(land_teams):
                        zone_name = zones_cycle[idx % 3]
                        habits["zones"][zone_name].append(team)
                        
                    return habits

        if total_rounds == 0:
            return {"total_rounds": 0, "zones": {}}

        # 3. Traiter le résultat de gac_round_teams
        habits = {
            "total_rounds": total_rounds,
            "zones": {
                "top": [],
                "bottom": [],
                "back": [],
                "fleet": []
            }
        }

        for row in rows:
            zone_raw = row["zone"]
            if not zone_raw:
                continue
                
            zone = str(zone_raw).lower()
            if "top" in zone or "north" in zone:
                z = "top"
            elif "bottom" in zone or "south" in zone:
                z = "bottom"
            elif "back" in zone:
                z = "back"
            elif "fleet" in zone or "ship" in zone:
                z = "fleet"
            else:
                z = zone

            import json
            try:
                members = json.loads(row["members_ids"])
            except:
                members = []

            freq = row["frequency"]
            percent = round((freq / total_rounds) * 100, 1)

            if z not in habits["zones"]:
                habits["zones"][z] = []

            habits["zones"][z].append({
                "leader_id": row["leader_id"],
                "members": members,
                "frequency": freq,
                "percent": percent
            })

        return habits
