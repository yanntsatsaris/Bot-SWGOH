"""
services/portrait_cache.py — Gestion du cache local des portraits
"""
from __future__ import annotations

import logging
import requests
import cloudscraper
from pathlib import Path

log = logging.getLogger(__name__)

PORTRAITS_DIR = Path("assets/portraits")
_SCRAPER = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "linux", "mobile": False}
)

def get_portrait_path(base_id: str) -> Path:
    """Retourne le chemin local du portrait."""
    return PORTRAITS_DIR / f"{base_id.lower()}.png"

def download_portrait(base_id: str) -> bool:
    """Télécharge le portrait à la volée."""
    dest = get_portrait_path(base_id)
    if dest.exists() and dest.stat().st_size > 2000:
        return True

    urls = [
        f"https://swgoh.gg/game-asset/u/{base_id}/",
        f"https://game-assets.swgoh.gg/tex.avatars_{base_id.lower()}.png",
        f"https://swgoh.gg/static/img/assets/tex.avatars_{base_id.lower()}.png",
    ]

    for url in urls:
        try:
            client = _SCRAPER if "swgoh.gg" in url else requests
            resp = client.get(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200 and len(resp.content) > 2000:
                if b"PNG" in resp.content[:10] or b"JFIF" in resp.content[:10]:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(resp.content)
                    return True
        except Exception:
            continue
    return False

def download_all_portraits(base_ids: list[str]) -> dict[str, bool]:
    return {bid: download_portrait(bid) for bid in base_ids}
