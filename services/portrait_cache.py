"""
services/portrait_cache.py — Téléchargement et cache local des portraits SWGOH
"""
from __future__ import annotations

import logging
from pathlib import Path
import cloudscraper

log = logging.getLogger(__name__)

PORTRAITS_DIR = Path("assets/portraits")

_TIMEOUT = 15
_SCRAPER = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "linux", "mobile": False}
)

def get_portrait_path(base_id: str) -> Path:
    """Retourne le chemin local du portrait (qu'il existe ou non)."""
    return PORTRAITS_DIR / f"{base_id.lower()}.png"

def download_portrait(base_id: str) -> bool:
    """
    Télécharge le portrait d'un personnage et le sauvegarde localement.
    """
    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    dest = get_portrait_path(base_id)

    if dest.exists():
        return True

    # Liste des patterns d'URL
    urls = [
        f"https://game-assets.swgoh.gg/tex.avatars_{base_id.lower()}.png",
        f"https://static-swgoh.gg/game-asset/u/{base_id}/",
        f"https://swgoh.gg/game-asset/u/{base_id}/",
    ]

    for url in urls:
        try:
            resp = _SCRAPER.get(url, timeout=_TIMEOUT)
            if resp.status_code == 200 and len(resp.content) > 1000:
                dest.write_bytes(resp.content)
                log.debug("Portrait téléchargé : %s", base_id)
                return True
        except Exception:
            continue

    log.debug("Portrait introuvable : %s", base_id)
    return False

def download_all_portraits(base_ids: list[str]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for base_id in base_ids:
        results[base_id] = download_portrait(base_id)
    return results
