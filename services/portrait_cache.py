"""
services/portrait_cache.py — Téléchargement et cache local des portraits SWGOH
"""
from __future__ import annotations

import logging
from pathlib import Path

import requests

log = logging.getLogger(__name__)

PORTRAITS_DIR = Path("assets/portraits")

# URLs candidates dans l'ordre de priorité
_PORTRAIT_URL_TEMPLATES = [
    "https://swgoh.gg/game-asset/u/{base_id}.png",
    "https://swgoh.gg/static/img/assets/tex.avatars_{base_id_lower}.png",
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SwgohBot/1.0)",
    "Referer": "https://swgoh.gg/",
}
_TIMEOUT = 15


def get_portrait_path(base_id: str) -> Path:
    """Retourne le chemin local du portrait (qu'il existe ou non)."""
    return PORTRAITS_DIR / f"{base_id.lower()}.png"


def download_portrait(base_id: str) -> bool:
    """
    Télécharge le portrait d'un personnage et le sauvegarde localement.

    Returns:
        True si téléchargé avec succès, False sinon.
    """
    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    dest = get_portrait_path(base_id)

    if dest.exists():
        return True  # Déjà en cache

    for template in _PORTRAIT_URL_TEMPLATES:
        url = template.format(base_id=base_id, base_id_lower=base_id.lower())
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
                dest.write_bytes(resp.content)
                log.debug("Portrait téléchargé : %s", base_id)
                return True
        except requests.RequestException:
            continue

    log.debug("Portrait introuvable : %s", base_id)
    return False


def download_all_portraits(base_ids: list[str]) -> dict[str, bool]:
    """
    Télécharge tous les portraits d'une liste de base_id.

    Returns:
        Dictionnaire {base_id: succès}.
    """
    results: dict[str, bool] = {}
    for base_id in base_ids:
        results[base_id] = download_portrait(base_id)
    ok = sum(1 for v in results.values() if v)
    log.info("Portraits : %d/%d téléchargés", ok, len(base_ids))
    return results
