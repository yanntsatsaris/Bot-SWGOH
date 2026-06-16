"""
services/portrait_cache.py — Gestion du cache local des portraits
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Les portraits sont stockés dans assets/portraits/ sous la forme charui_xxx.png
Ce module gère le mapping entre le base_id (Comlink) et le nom du fichier.
"""
from __future__ import annotations

import logging
import json
import os
from pathlib import Path

log = logging.getLogger(__name__)

PORTRAITS_DIR = Path("assets/portraits")
THUMB_MAP_FILE = Path("utils/unit_thumbs.json")

_thumb_cache: dict[str, str] = {}

def load_thumb_map():
    """Charge le mapping base_id -> thumbnailName depuis le fichier JSON."""
    global _thumb_cache
    if THUMB_MAP_FILE.exists():
        try:
            with open(THUMB_MAP_FILE, "r", encoding="utf-8") as f:
                _thumb_cache = json.load(f)
        except Exception as e:
            log.error("Erreur chargement thumb map: %s", e)

def get_portrait_path(base_id: str) -> Path:
    """
    Retourne le chemin local du portrait pour un base_id donné.
    Format attendu : charui_[thumbnail_name].png
    """
    if not _thumb_cache:
        load_thumb_map()

    # 1. On cherche dans le mapping Comlink (ex: SITHPALPATINE -> tex.avatars_sithemperor)
    thumb_name = _thumb_cache.get(base_id.upper())

    if thumb_name:
        clean_name = thumb_name.replace("tex.avatars_", "")
        path = PORTRAITS_DIR / f"charui_{clean_name}.png"
        if path.exists():
            return path

    # 2. Fallback direct (ex: DARTHVADER -> charui_vader.png)
    short_id = base_id.lower()
    if short_id == "darthvader": short_id = "vader"
    if short_id == "sithpalpatine": short_id = "sithemperor"

    path = PORTRAITS_DIR / f"charui_{short_id}.png"
    if path.exists():
        return path

    # 3. Dernier recours : on cherche n'importe quel fichier contenant le base_id
    for p in PORTRAITS_DIR.glob(f"*{base_id.lower()}*"):
        return p

    return PORTRAITS_DIR / f"charui_{base_id.lower()}.png"

def download_portrait(base_id: str) -> bool:
    """
    Les portraits sont gérés par download_portraits.py.
    """
    return get_portrait_path(base_id).exists()
