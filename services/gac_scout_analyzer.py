import logging
from database.db import get_db

logger = logging.getLogger("gac_scout_analyzer")

class GacScoutAnalyzer:
    @staticmethod
    async def get_defensive_habits(ally_code: str, format_type: str = '5v5') -> dict:
        """
        Analyse les habitudes défensives d'un joueur.
        Retourne un dictionnaire groupé par zone (Top, Bottom, Back, Fleet).
        """
        async with get_db() as db:
            # On cherche toutes les équipes de défense posées par ce joueur
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

            # On compte le nombre total de rounds où le joueur a joué en défense dans ce format
            # Pour calculer les vrais pourcentages.
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

        if total_rounds == 0:
            return {"total_rounds": 0, "zones": {}}

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
