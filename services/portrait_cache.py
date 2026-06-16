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
    if not _unit_data:
        _load_data()

    bid_upper = base_id.upper()
    bid_lower = base_id.lower()
    unit = _unit_data.get(bid_upper, {})
    unit_type = unit.get("type", "character")

    target_dir = SHIPS_DIR if unit_type == "ship" else PORTRAITS_DIR

    # MAPPINGS MANUELS EXHAUSTIFS (Mis à jour le 16/06)
    MANUAL_MAPPING = {
        # --- GLs / Persos Clés ---
        "SITHPALPATINE": "espalpatine_pre",
        "EMPERORPALPATINE": "palpatineemperor",
        "GLLEIA": "leiaendor",
        "GLREY": "rey_tros",
        "GRANDMASTERLUKE": "luke_jml",
        "JEDIMASTERLUKE": "luke_jml",
        "GRANDMASTERYODA": "yodagrandmaster",
        "HERMITYODA": "yodahermit",
        "GENERALKENOBI": "obiwangeneral",
        "JEDIMASTERKENOBI": "globiwan",
        "GENERALSKYWALKER": "generalanakin",
        "COMMANDERLUKESKYWALKER": "lukebespin",
        "GRANDMOFFTARKIN": "tarkinadmiral",

        # --- Autres Persos ---
        "BISHOP": "captainenoch",
        "GOPHERANTS": "groguanz",
        "HERASYNDULLAS3": "hera_s3",
        "HOTHLEIA": "leiahoth",
        "HOTHREBELSCOUT": "rebelhothscout",
        "HOTHREBELSOLDIER": "rebelhoth",
        "CHIEFNEBIT": "jawa_nebit",
        "CLONESERGEANTPHASEI": "trooperclonegreen",
        "BADBATCHECHO": "bb_echo",
        "BADBATCHHUNTER": "bb_hunter",
        "BADBATCHTECH": "bb_tech",
        "BADBATCHWRECKER": "bb_wrecker",
        "BADBATCHOMEGA": "badbatchomega",
        "EZRABRIDGERS3": "ezra_s3",
        "CROSSHAIRS3": "crosshair_scarred",
        "CORUSCANTUNDERWORLDPOLICE": "coruscantpolice",
        "EWOKELDER": "ewok_chief",
        "C3POLEGENDARY": "c3p0",
        "R2D2_LEGENDARY": "astromech_r2d2",
        "SKIFFGUARD": "undercoverlando",

        # --- Vaisseaux ---
        "GEONOSIANSTARFIGHTER1": "geonosis_fighter_sunfac",
        "GEONOSIANSTARFIGHTER2": "geonosis_fighter_spy",
        "GEONOSIANSTARFIGHTER3": "geonosis_fighter_soldier",
        "CAPITALMONCALAMARICRUISER": "moncalamarilibertycruiser",
        "CAPITALJEDICRUISER": "negotiator",
        "COMMANDSHUTTLE": "upsilon_shuttle_kylo",
        "EMPERORSSHUTTLE": "imperialshuttle",
    }

    targets = []
    if bid_upper in MANUAL_MAPPING:
        targets.append(MANUAL_MAPPING[bid_upper])

    if unit.get("thumbnail_name"):
        targets.append(unit["thumbnail_name"])

    targets.append(bid_lower)
    targets.append(bid_lower.replace("capital", "").replace("ship_", "").replace("gl", ""))

    prefixes = ["charui_", ""]

    for t in targets:
        clean = str(t).replace(".png", "").replace("tex.avatars_", "")
        for pref in prefixes:
            path = target_dir / f"{pref}{clean}.png"
            if path.exists(): return path

    # Recherche floue
    if target_dir.exists():
        search = bid_lower.replace("_", "")
        for p in target_dir.glob("*.png"):
            fname = p.stem.lower().replace("_", "").replace("charui", "")
            if search in fname or fname in search:
                return p

    return target_dir / f"charui_{bid_lower}.png"

def download_portrait(base_id: str) -> bool:
    return get_portrait_path(base_id).exists()
