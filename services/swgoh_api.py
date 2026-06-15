"""
services/swgoh_api.py — Client HTTP asynchrone vers l'API SWGOH.GG
"""
import logging

import aiohttp

from config import SWGOH_API_URL

log = logging.getLogger(__name__)

# Timeout global pour toutes les requêtes API (en secondes)
_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def fetch_player(ally_code: str) -> dict:
    """
    Récupère les données complètes d'un joueur depuis l'API SWGOH.GG.

    Args:
        ally_code: Code allié normalisé (format XXX-XXX-XXX).

    Returns:
        Dictionnaire JSON brut retourné par l'API.

    Raises:
        ValueError: Si le joueur est introuvable (HTTP 404).
        aiohttp.ClientError: Pour toute autre erreur réseau.
    """
    # L'API SWGOH.GG attend le code sans tirets
    clean_code = ally_code.replace("-", "")
    url = f"{SWGOH_API_URL}/players/{clean_code}/"

    async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
        async with session.get(url) as response:
            if response.status == 404:
                raise ValueError(f"Joueur introuvable pour le code allié : {ally_code}")
            response.raise_for_status()
            data: dict = await response.json()
            log.debug("Données reçues pour %s : %s", ally_code, list(data.keys()))
            return data
