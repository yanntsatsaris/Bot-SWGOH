"""
services/portrait_cache.py — Gestion du cache local des portraits et vaisseaux
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging
import json
from pathlib import Path

log = logging.getLogger(__name__)

PORTRAITS_DIR = Path("assets/portraits")
SHIPS_DIR = Path("assets/vaisseaux")
ALL_UNITS_FILE = Path("database/all_units.json")

_unit_data: dict[str, dict] = {}

def _load_data():
    global _unit_data
    if ALL_UNITS_FILE.exists():
        try:
            with open(ALL_UNITS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _unit_data = {u["base_id"].upper(): u for u in data}
        except Exception:
            pass

def get_portrait_path(base_id: str) -> Path:
    """
    Retourne le chemin local du portrait (personnage ou vaisseau).
    """
    if not _unit_data:
        _load_data()

    bid_upper = base_id.upper()
    bid_lower = base_id.lower()
    unit = _unit_data.get(bid_upper, {})
    unit_type = unit.get("type", "character")

    # Choix du dossier racine
    target_dir = SHIPS_DIR if unit_type == "ship" else PORTRAITS_DIR

    # 1. Overrides manuels (Personnages)
    MANUAL_OVERRIDES = {
        "SITHPALPATINE": "espalpatine_pre",
        "JEDIMASTERKENOBI": "globiwan",
        "GENERALSKYWALKER": "generalanakin",
        "SKIFFGUARD": "undercoverlando",
        "OLDREPUBLICGUARD": "vanguardtempleguard",
    }

    # 2. Mappings spécifiques Vaisseaux (basés sur ta liste ll)
    SHIP_OVERRIDES = {
        "MILLENNIUMFALCON": "mfalcon",
        "HANSOLO_MILLENNIUMFALCON": "mfalcon",
        "MILLENNIUMFALCONPRISTINE": "mil_fal_pristine",
        "EBONHAWK": "ebonhawk",
        "SLAVE1": "slave1",
        "EXECUTOR": "executor",
        "CHIMAERA": "chimaera",
        "FINALIZER": "finalizer",
        "MALEVOLENCE": "malevolence",
        "NEGOTIATOR": "negotiator",
        "PROFUNDITY": "profundity",
        "LEVIATHAN": "leviathan",
        "RAZORCREST": "razorcrest",
        "TIEADVANCED": "tieadvanced",
        "TIE_INTERCEPTOR_PROTOTYPE": "tie_interceptor_prototype",
        "SCYTHE": "scythe",
        "OUTRIDER": "outrider",
    }

    targets = []
    if unit_type == "character" and bid_upper in MANUAL_OVERRIDES:
        targets.append(MANUAL_OVERRIDES[bid_upper])
    elif unit_type == "ship" and bid_upper in SHIP_OVERRIDES:
        targets.append(SHIP_OVERRIDES[bid_upper])

    # 3. Mapping officiel thumbnail_name
    official_thumb = unit.get("thumbnail_name")
    if official_thumb:
        targets.append(official_thumb)

    # 4. Dérivations (avec et sans préfixes)
    targets.append(bid_lower)
    # Pour les vaisseaux, on teste sans le préfixe common "capitalship_" ou "ship_"
    if unit_type == "ship":
        targets.append(bid_lower.replace("capitalship_", "").replace("ship_", ""))

    # On teste les variations dans le bon dossier
    prefixes = ["charui_", ""] if unit_type == "character" else [""] # Tes vaisseaux n'ont pas l'air d'avoir de préfixe charui_

    for t in targets:
        clean = t.replace(".png", "").replace("tex.avatars_", "")
        for pref in prefixes:
            path = target_dir / f"{pref}{clean}.png"
            if path.exists(): return path

    # 5. Recherche floue finale (inclusion)
    if target_dir.exists():
        search = bid_lower.replace("_", "")
        for p in target_dir.glob("*.png"):
            fname = p.stem.lower().replace("_", "").replace("charui", "")
            if search in fname or fname in search:
                return p

    # Fallback par défaut (visuel manquant)
    return target_dir / f"{bid_lower}.png"

def download_portrait(base_id: str) -> bool:
    return get_portrait_path(base_id).exists()
