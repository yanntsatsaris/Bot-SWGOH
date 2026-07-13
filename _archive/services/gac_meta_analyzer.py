"""
services/gac_meta_analyzer.py
Analyse les snapshots stockés pour générer des statistiques méta et les win rates des contres.
"""
import json
from database.db import get_db

async def get_unit_usage_rate(
    unit_id: str,
    season_id: str | None = None,
    league: int | None = None,
    min_relic: int = 5,
) -> dict:
    """
    Calcule le taux d'utilisation d'un personnage parmi les joueurs scannés.
    
    Returns: {"unit_id", "total_players", "players_with_unit", "usage_rate"}
    """
    async with get_db() as db:
        # Filtres dynamiques
        where = []
        params = []
        if season_id:
            where.append("s.season_id = ?")
            params.append(season_id)
        if league:
            where.append("s.league = ?")
            params.append(league)
        where_clause = "WHERE " + " AND ".join(where) if where else ""

        # Total joueurs
        async with db.execute(
            f"SELECT COUNT(DISTINCT s.id) FROM gac_roster_snapshots s {where_clause}",
            params
        ) as cur:
            row = await cur.fetchone()
            total = row[0] if row else 0

        # Joueurs ayant ce perso au niveau requis
        query = f"""
            SELECT COUNT(DISTINCT s.id)
            FROM gac_roster_snapshots s
            JOIN gac_roster_units u ON u.snapshot_id = s.id
            {where_clause}
            {'AND' if where_clause else 'WHERE'} u.unit_id = ? AND u.relic_tier >= ?
        """
        async with db.execute(query, params + [unit_id, min_relic]) as cur:
            row = await cur.fetchone()
            with_unit = row[0] if row else 0

    return {
        "unit_id":         unit_id,
        "total_players":   total,
        "players_with_unit": with_unit,
        "usage_rate":      round(with_unit / total * 100, 1) if total else 0,
    }

async def get_top_units_by_league(
    season_id: str,
    league: int,
    limit: int = 20,
    min_relic: int = 5,
) -> list[dict]:
    """
    Retourne les personnages les plus répandus dans une ligue.
    """
    async with get_db() as db:
        async with db.execute("""
            SELECT u.unit_id,
                   COUNT(DISTINCT s.id) as player_count
            FROM gac_roster_snapshots s
            JOIN gac_roster_units u ON u.snapshot_id = s.id
            WHERE s.season_id = ?
              AND s.league    = ?
              AND u.relic_tier >= ?
              AND u.combat_type = 1
            GROUP BY u.unit_id
            ORDER BY player_count DESC
            LIMIT ?
        """, (season_id, league, min_relic, limit)) as cur:
            rows = await cur.fetchall()

        # Total joueurs dans cette ligue
        async with db.execute(
            "SELECT COUNT(*) FROM gac_roster_snapshots WHERE season_id=? AND league=?",
            (season_id, league)
        ) as cur:
            row = await cur.fetchone()
            total = row[0] if row else 0

    return [
        {
            "unit_id":     row["unit_id"],
            "player_count": row["player_count"],
            "usage_rate":  round(row["player_count"] / total * 100, 1) if total else 0,
        }
        for row in rows
    ]

async def get_counter_win_rate(
    attacker_leader: str,
    defender_leader: str,
) -> dict:
    """
    Calcule le win rate d'une équipe d'attaque contre une défense spécifique.
    Basé sur les données auto-reportées (gac_round_teams).
    """
    async with get_db() as db:
        async with db.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN off_team.success = 1 THEN 1 ELSE 0 END) as wins
            FROM gac_round_teams off_team
            JOIN gac_rounds r ON r.id = off_team.round_id
            WHERE off_team.side = 'offense'
              AND off_team.leader_id = ?
              AND EXISTS (
                SELECT 1 FROM gac_round_teams def_team
                WHERE def_team.round_id = off_team.round_id
                  AND def_team.side = 'defense'
                  AND def_team.leader_id = ?
              )
        """, (attacker_leader, defender_leader)) as cur:
            row = await cur.fetchone()

    total = row["total"] if row else 0
    wins  = row["wins"]  if row else 0
    return {
        "attacker":   attacker_leader,
        "defender":   defender_leader,
        "total_games": total,
        "wins":        wins,
        "win_rate":    round(wins / total * 100, 1) if total else None,
        "confidence":  "haute" if total >= 10 else "moyenne" if total >= 5 else "faible",
    }
