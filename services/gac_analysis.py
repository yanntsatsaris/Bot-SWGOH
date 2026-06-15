"""
services/gac_analysis.py — Logique métier d'analyse GAC
"""
import logging

from services.swgoh_api import fetch_player

log = logging.getLogger(__name__)


async def get_player_gac_stats(ally_code: str) -> dict:
    """
    Récupère et normalise les statistiques GAC d'un joueur.

    Args:
        ally_code: Code allié normalisé (format XXX-XXX-XXX).

    Returns:
        Dictionnaire avec les clés : username, ally_code, league,
        division, rank, wins, losses.
    """
    raw = await fetch_player(ally_code)
    player_data: dict = raw.get("data", {})

    return {
        "username":  player_data.get("name", "Inconnu"),
        "ally_code": ally_code,
        "league":    player_data.get("league_name"),
        "division":  player_data.get("division_number"),
        "rank":      player_data.get("league_rank"),
        "wins":      player_data.get("wins", 0),
        "losses":    player_data.get("losses", 0),
    }
