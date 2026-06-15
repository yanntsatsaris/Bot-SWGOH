"""
services/portrait_cache.py — Gestion du cache local des portraits via swgoh-ae2
"""
from __future__ import annotations

import logging
import requests
from pathlib import Path

log = logging.getLogger(__name__)

PORTRAITS_DIR = Path("assets/portraits")
AE2_URL = "http://localhost:3001"

def get_portrait_path(base_id: str) -> Path:
    """Retourne le chemin local du portrait."""
    return PORTRAITS_DIR / f"{base_id.lower()}.png"

def download_portrait(base_id: str) -> bool:
    """
    Tente de télécharger un portrait via l'Asset Extractor local.
    """
    dest = get_portrait_path(base_id)
    if dest.exists() and dest.stat().st_size > 2000:
        return True

    asset_name = f"charui_{base_id.lower()}"
    url = f"{AE2_URL}/Asset/single?assetName={asset_name}&forceReDownload=false"

    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code == 200 and resp.content.startswith(b'\x89PNG'):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            log.info("Portrait extrait via AE2 : %s", base_id)
            return True
    except Exception as e:
        log.debug("Échec extraction AE2 pour %s : %s", base_id, e)

    return False

def download_all_portraits(base_ids: list[str]) -> dict[str, bool]:
    return {bid: download_portrait(bid) for bid in base_ids}
