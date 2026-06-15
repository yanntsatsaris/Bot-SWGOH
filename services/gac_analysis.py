"""
services/gac_analysis.py — Logique métier d'analyse GAC via Comlink
"""
import logging

from services.comlink import get_player, get_player_arena

log = logging.getLogger(__name__)

_ARENA_TAB  = 1
_FLEET_TAB  = 2

# Mapping league_id → nom lisible
_LEAGUE_NAMES = {
    "CARBONITE":  "Carbonite",
    "BRONZIUM":   "Bronzium",
    "CHROMIUM":   "Chromium",
    "AURODIUM":   "Aurodium",
    "KYBER":      "Kyber",
}

# Mapping division : valeur numérique → label
# Dans Comlink, divisionId est un entier (5, 10, 15, 20, 25)
_DIVISION_LABELS = {
    5:  "I",
    10: "II",
    15: "III",
    20: "IV",
    25: "V",
}


def _parse_squad(cells: list[dict]) -> list[str]:
    """
    Extrait les base_id depuis les cellules d'un squad.
    unitDefId format : 'BASE_ID:SEVEN_STAR' → on coupe avant ':'.
    Le leader a squadUnitType == 2.
    """
    sorted_cells = sorted(cells, key=lambda c: 0 if c.get("squadUnitType") == 2 else 1)
    return [
        c["unitDefId"].split(":")[0]
        for c in sorted_cells
        if c.get("unitDefId")
    ]


def _parse_season_status(season_list: list[dict]) -> dict:
    """
    Retourne les infos de la saison en cours (dernière de la liste).
    seasonId contient '3v3' ou '5v5' pour identifier le format.
    """
    if not season_list:
        return {}

    # La saison active est celle avec remove=False et la joinTime la plus récente
    active = [s for s in season_list if not s.get("remove", True)]
    if not active:
        active = season_list

    current = max(active, key=lambda s: int(s.get("joinTime", 0)))

    season_id = current.get("seasonId", "")
    fmt = "3v3" if "3v3" in season_id else "5v5"

    league_id   = current.get("league", "")
    division_id = current.get("division")

    return {
        "season_id":     current.get("seasonId"),
        "format":        fmt,
        "league":        _LEAGUE_NAMES.get(league_id, league_id),
        "division":      _DIVISION_LABELS.get(division_id, str(division_id)),
        "rank":          current.get("rank"),
        "wins":          current.get("wins", 0),
        "losses":        current.get("losses", 0),
        "season_points": current.get("seasonPoints", 0),
    }


async def get_player_gac_stats(ally_code: str) -> dict:
    """
    Récupère et normalise les statistiques GAC d'un joueur via Comlink.

    Returns:
        Dictionnaire avec les clés :
        username, ally_code,
        league, division, rank, wins, losses, season_points, format,
        arena_rank, gac_squad, arena_squad.
    """
    clean = ally_code.replace("-", "")

    player_raw = await get_player(clean)
    arena_raw  = await get_player_arena(clean)

    username = player_raw.get("name", "Inconnu")

    # --- Saison GAC en cours ---
    season_info = _parse_season_status(player_raw.get("seasonStatus", []))

    # --- Ligue/division actuelle (hors saison) ---
    player_rating  = player_raw.get("playerRating", {})
    rank_status    = player_rating.get("playerRankStatus", {})
    current_league = _LEAGUE_NAMES.get(rank_status.get("leagueId", ""), rank_status.get("leagueId"))
    current_div    = _DIVISION_LABELS.get(rank_status.get("divisionId"), str(rank_status.get("divisionId", "")))

    # --- Squads d'arène ---
    pvp: dict[int, dict] = {
        p["tab"]: p for p in arena_raw.get("pvpProfile", [])
    }

    arena_profile = pvp.get(_ARENA_TAB, {})
    arena_rank    = arena_profile.get("rank")
    arena_cells   = arena_profile.get("squad", {}).get("cell", [])
    arena_squad   = _parse_squad(arena_cells)

    # Squad GAC = équipe arène (Comlink ne retourne pas de tab 3 séparé)
    gac_squad = arena_squad

    return {
        "username":      username,
        "ally_code":     ally_code,
        # Saison en cours
        "league":        season_info.get("league") or current_league,
        "division":      season_info.get("division") or current_div,
        "rank":          season_info.get("rank"),
        "wins":          season_info.get("wins", 0),
        "losses":        season_info.get("losses", 0),
        "season_points": season_info.get("season_points", 0),
        "format":        season_info.get("format", "?"),
        # Arène
        "arena_rank":    arena_rank,
        "arena_squad":   arena_squad,
        "gac_squad":     gac_squad,
    }
