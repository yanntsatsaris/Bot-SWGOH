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

    target_dir = SHIPS_DIR if unit_type == "ship" else PORTRAITS_DIR

    # Mappings manuels exhaustifs basés sur les fichiers réels
    MANUAL_MAPPING = {
        # GLs
        "SITHPALPATINE": "espalpatine_pre",
        "JEDIMASTERKENOBI": "globiwan",
        "GENERALSKYWALKER": "generalanakin",
        "JEDIMASTERLUKE": "luke_jml",
        "SUPREMELEADERKYLOREN": "kyloren_tros",
        "REYJEDITRAINING": "rey_tlj",

        # Bad Batch
        "BADBATCHECHO": "bb_echo",
        "BADBATCHHUNTER": "bb_hunter",
        "BADBATCHTECH": "bb_tech",
        "BADBATCHWRECKER": "bb_wrecker",
        "BADBATCHOMEGA": "badbatchomega",

        # Clones / Republic
        "ARCTROOPER501ST": "trooperclone_arc",
        "CC2224": "trooperclone_cody",
        "CT7567": "trooperclone_rex",
        "CT5555": "trooperclone_fives",
        "CT210408": "trooperclone_echo",
        "BARRISSOFFEE": "barriss_light",

        # Rebels / Empire
        "ADMINISTRATORLANDO": "landobespin",
        "ADMIRALACKBAR": "ackbaradmiral",
        "BIGGSDARKLIGHTER": "rebelpilot_biggs",
        "WEDGEANTILLES": "rebelpilot_wedge",
        "PRINCESSLEIA": "leia_princess",
        "HANSOLO": "han",
        "C3POLEGENDARY": "c3p0",
        "R2D2_LEGENDARY": "astromech_r2d2",
        "CHIEFCHIRPA": "ewok_chirpa",

        # Jabba / Bounty Hunters
        "SKIFFGUARD": "undercoverlando",
        "BOBAFETTSCION": "bobafettold",
        "GREEFKARGA": "greefkarga",

        # Vaisseaux (Basés sur ton ll)
        "CAPITALMONCALAMARICRUISER": "moncalamarilibertycruiser",
        "CAPITALJEDICRUISER": "negotiator",
        "CAPITALSTARDESTROYER": "stardestroyer",
        "CAPITALCHIMAERA": "chimaera",
        "CAPITALFINALIZER": "finalizer",
        "CAPITALMALEVOLENCE": "malevolence",
        "CAPITALPROFUNDITY": "profundity",
        "CAPITALVICTORYSTARDESTROYER": "stardestroyer",
        "MILLENNIUMFALCON": "mfalcon",
        "HANSOLO_MILLENNIUMFALCON": "mfalcon",
        "EBONHAWK": "ebonhawk",
        "SLAVE1": "slave1",
    }

    targets = []
    if bid_upper in MANUAL_MAPPING:
        targets.append(MANUAL_MAPPING[bid_upper])

    # thumbnail_name officiel
    if unit.get("thumbnail_name"):
        targets.append(unit["thumbnail_name"])

    # Dérivations
    targets.append(bid_lower)
    targets.append(bid_lower.replace("capital", "").replace("ship_", ""))

    prefixes = ["charui_", ""]

    for t in targets:
        clean = t.replace(".png", "").replace("tex.avatars_", "")
        for pref in prefixes:
            path = target_dir / f"{pref}{clean}.png"
            if path.exists(): return path

    # Recherche floue finale
    if target_dir.exists():
        search = bid_lower.replace("_", "")
        for p in target_dir.glob("*.png"):
            fname = p.stem.lower().replace("_", "").replace("charui", "")
            if search in fname or fname in search:
                return p

    return target_dir / f"charui_{bid_lower}.png"

def download_portrait(base_id: str) -> bool:
    return get_portrait_path(base_id).exists()
