"""
services/portrait_cache.py — Gestion du cache local des portraits
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging
import json
import os
from pathlib import Path

log = logging.getLogger(__name__)

PORTRAITS_DIR = Path("assets/portraits")

# Mapping exhaustif BaseID (Comlink) -> Nom du fichier (sans extension)
ASSET_MAPPING = {
    # GLs
    "SITHPALPATINE": "espalpatine_pre",
    "JEDIMASTERKENOBI": "globiwan",
    "JEDIMASTERLUKE": "luke_jml",
    "SUPREMELEADERKYLOREN": "kyloren_tros",
    "LORDVADER": "lordvader",
    "JABBATHEHUTT": "jabbathehutt",
    "REYJEDITRAINING": "rey_tlj",
    "LEIAORGANA": "leiaendor",
    "GLHONDO": "glhondo",

    # Empire / Sith
    "DARTHVADER": "vader",
    "PALPATINE": "palpatineemperor",
    "THRAWN": "thrawn",
    "MARAJADE": "marajade",
    "DARTHNIHILUS": "nihilus",
    "DEATHTROOPER": "trooperdeath",
    "RANGETROOPER": "trooperranger",
    "MAGMATROOPER": "trooperstorm_magma",
    "GENERALVEERS": "veers",
    "KRENNIC": "krennic",
    "STARKILLERBASE": "starkiller",
    "ROYALGUARD": "royalguard",
    "SITHMARAUDER": "sithmarauder",
    "SITHASSASSIN": "sithassassin",
    "SITHTROOPER": "firstorder_sithtrooper",

    # Jedi / Galactic Republic
    "GENERALSKYWALKER": "generalanakin",
    "PADMEAMIDALA": "padme_geonosis",
    "AHSOKATANO": "ahsoka",
    "COMMANDERAHSOKATANO": "commanderahsokatano",
    "SHAAKTI": "shaakti",
    "GRANDMASTERYODA": "yodagrandmaster",
    "HERMITYODA": "yodahermit",
    "QUIGONJINN": "quigon",
    "OBIWAN": "obiwanep4",
    "MACEWINDU": "macewindu",
    "KITFISTO": "kitfisto",
    "BARRISSOFFEE": "barriss_light",
    "JEDIKNIGHTLUKE": "luke_jediknight",

    # Rebels
    "COMMANDERLUKESKYWALKER": "lukebespin",
    "HANSOLO": "han",
    "CHEWBACCA": "chewbacca_ot",
    "C3POLEGENDARY": "c3p0",
    "R2D2_LEGENDARY": "astromech_r2d2",
    "PRINCESSLEIA": "leia_princess",
    "CHIRRUT": "chirrut",
    "BAZE": "bazemalbus",
    "CASSIANANDOR": "cassian",
    "K2SO": "k2so",
    "ADMIRALACKBAR": "ackbaradmiral",

    # Bounty Hunters / Jabba
    "BOBAFETT": "bobafett",
    "BOBAFETTSCION": "bobafettold",
    "BOSSK": "bossk",
    "DENGAR": "dengar",
    "CADSANE": "cadbane",
    "IG88": "ig88",
    "GREEFKARGA": "greefkarga",
    "FENNECSHAND": "fennec",
    "KRRSANTAN": "krrsantan",
    "SKIFFGUARD": "skiffguard",
    "BIBFORTUNA": "bibfortuna",
    "GAMORREANGUARD": "gamorreanguard",

    # First Order / Resistance
    "KYLORENUNMASKED": "kylo_unmasked",
    "KYLOREN": "kyloren",
    "GENERALHUX": "generalhux",
    "FIRSTORDERTIEPILOT": "firstordertiepilot",
    "FIRSTORDERSFTFIGHTER": "firstorder_pilot",
    "CAPTAINPHASMA": "phasma",
    "FINN": "finn",
    "REYJAKKU": "reyjakku",
    "BB8": "bb8",

    # Separatists
    "GENERALGRIEVOUS": "grievous",
    "DROIDEKA": "droideka",
    "B1BATTLEDROIDV2": "b1",
    "MAGNAGUARD": "magnaguard",
    "NUTE": "nutegunray",
    "COUNTDOOKU": "dooku",
    "ASAJVENTRESS": "ventress",

    # Old Republic
    "DARTHREVAN": "sithrevan",
    "JEDIKNIGHTREVAN": "jedirevan",
    "BASTILLASHAN": "bastilashan",
    "BASTILLASHANDARK": "bastilashan_dark",
    "JOLEEBINDO": "joleebindo",
    "JUHANI": "juhani",

    # Nightsisters
    "MOTHERTALZIN": "nightsisters_talzin",
    "ZOMBIESISTER": "nightsisters_zombie",
    "NIGHTSISTERINIT": "nightsister_initiate",
    "TALIA": "nightsister_talia",
    "DAKA": "daka",
    "ACOLYTE": "nightsister_acolyte",

    # Mandalorians
    "THEMANDALORIAN": "mandalorian",
    "THEMANDALORIANBESKARARMOR": "mandobeskar",
    "MOFFGIDEON": "moffgideon",
    "BOSAKATAN": "bokatan",
}

def get_portrait_path(base_id: str) -> Path:
    """
    Retourne le chemin local du portrait.
    Tente le mapping manuel, puis plusieurs variantes automatiques.
    """
    bid_upper = base_id.upper()

    # 1. Mapping manuel (priorité haute car exacte)
    if bid_upper in ASSET_MAPPING:
        asset = ASSET_MAPPING[bid_upper]
        for name in [f"charui_{asset}", asset]:
            p = PORTRAITS_DIR / f"{name}.png"
            if p.exists(): return p

    # 2. Test direct (ex: charui_maul.png)
    for name in [f"charui_{base_id.lower()}", base_id.lower()]:
        p = PORTRAITS_DIR / f"{name}.png"
        if p.exists(): return p

    # 3. Recherche floue (inclusion)
    if PORTRAITS_DIR.exists():
        search = base_id.lower().replace("_", "")
        for p in PORTRAITS_DIR.glob("*.png"):
            fname = p.stem.lower().replace("_", "").replace("charui", "")
            if search == fname or search in fname or fname in search:
                return p

    # Fallback par défaut
    return PORTRAITS_DIR / f"charui_{base_id.lower()}.png"

def download_portrait(base_id: str) -> bool:
    return get_portrait_path(base_id).exists()
