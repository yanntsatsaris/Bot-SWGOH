"""
utils/gac_config.py — Configuration des quotas GAC
"""

# Dictionnaire des quotas de défense par ligue, format et zone.
GAC_DEFENSE_QUOTAS = {
    "CARBONITE": {
        "3v3": {"North": 1, "South": 1, "Back": 1, "Fleet": 1},
        "5v5": {"North": 1, "South": 1, "Back": 1, "Fleet": 1},
    },
    "BRONZIUM": {
        "3v3": {"North": 2, "South": 2, "Back": 3, "Fleet": 1},
        "5v5": {"North": 2, "South": 2, "Back": 1, "Fleet": 1},
    },
    "CHROMIUM": {
        "3v3": {"North": 3, "South": 3, "Back": 4, "Fleet": 2},
        "5v5": {"North": 3, "South": 2, "Back": 2, "Fleet": 2},
    },
    "AURODIUM": {
        "3v3": {"North": 4, "South": 4, "Back": 5, "Fleet": 2},
        "5v5": {"North": 3, "South": 3, "Back": 3, "Fleet": 2},
    },
    "KYBER": {
        "3v3": {"North": 5, "South": 5, "Back": 5, "Fleet": 3},
        "5v5": {"North": 4, "South": 4, "Back": 3, "Fleet": 3},
    },
}

def get_gac_quotas(league: str, fmt: str) -> dict[str, int]:
    """Retourne les quotas pour une ligue (ex: 'KYBER') et un format ('3v3' ou '5v5')."""
    league_upper = league.upper()
    if league_upper not in GAC_DEFENSE_QUOTAS:
        # Fallback de sécurité (ex: si le joueur n'a pas de ligue)
        league_upper = "CARBONITE"
    return GAC_DEFENSE_QUOTAS[league_upper].get(fmt, GAC_DEFENSE_QUOTAS[league_upper]["5v5"])
