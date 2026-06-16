"""
services/portrait_cache.py — Gestion du cache local des portraits
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging
import json
from pathlib import Path

log = logging.getLogger(__name__)

PORTRAITS_DIR = Path("assets/portraits")
ALL_UNITS_FILE = Path("database/all_units.json")

_portrait_mapping: dict[str, str] = {}

def _load_mapping():
    global _portrait_mapping
    if ALL_UNITS_FILE.exists():
        try:
            with open(ALL_UNITS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _portrait_mapping = {u["base_id"].upper(): u["thumbnail_name"] for u in data}
        except Exception:
            pass

def get_portrait_path(base_id: str) -> Path:
    """
    Retourne le chemin local du portrait.
    """
    if not _portrait_mapping:
        _load_mapping()

    bid_upper = base_id.upper()
    bid_lower = base_id.lower()

    # Overrides manuels spécifiques confirmés
    MANUAL_OVERRIDES = {
        "SITHPALPATINE": "espalpatine_pre",
        "JEDIMASTERKENOBI": "globiwan",
        "GENERALSKYWALKER": "generalanakin",
        "SKIFFGUARD": "undercoverlando",
        "OLDREPUBLICGUARD": "vanguardtempleguard",
    }

    targets = []
    if bid_upper in MANUAL_OVERRIDES:
        targets.append(MANUAL_OVERRIDES[bid_upper])

    # Mapping officiel
    official_thumb = _portrait_mapping.get(bid_upper)
    if official_thumb:
        targets.append(official_thumb)

    # Dérivations
    targets.append(bid_lower)

    for t in targets:
        clean = t.replace(".png", "").replace("tex.avatars_", "")
        for name in [f"charui_{clean}", clean]:
            path = PORTRAITS_DIR / f"{name}.png"
            if path.exists(): return path

    # Recherche floue finale
    if PORTRAITS_DIR.exists():
        search = bid_lower.replace("_", "")
        for p in PORTRAITS_DIR.glob("*.png"):
            fname = p.stem.lower().replace("_", "").replace("charui", "")
            if search in fname or fname in search:
                return p

    return PORTRAITS_DIR / f"charui_{bid_lower}.png"

def download_portrait(base_id: str) -> bool:
    return get_portrait_path(base_id).exists()
