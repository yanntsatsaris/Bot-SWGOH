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
_db_image_paths: dict[str, str] = {}
_validated_image_paths: set[str] = set()

async def build_portrait_cache() -> None:
    """Charge le cache des chemins d'images validés depuis la BDD."""
    global _db_image_paths, _validated_image_paths
    try:
        from database.db import get_db
        async with get_db() as db:
            cursor = await db.execute("SELECT base_id, image_path, is_image_valid FROM units_directory WHERE image_path IS NOT NULL")
            rows = await cursor.fetchall()
            if rows:
                _db_image_paths = {
                    row["base_id"].upper(): row["image_path"] 
                    for row in rows if row["is_image_valid"] == 1
                }
                _validated_image_paths = {
                    Path(row["image_path"]).as_posix()
                    for row in rows if row["is_image_valid"] == 1
                }
    except Exception as e:
        log.error("Erreur chargement cache portraits depuis DB: %s", e)

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
    bid_upper = base_id.upper()
    
    # 1. Priorité absolue : le chemin en base de données s'il est validé ou deviné
    if bid_upper in _db_image_paths and _db_image_paths[bid_upper]:
        p = Path(_db_image_paths[bid_upper])
        if p.exists():
            return p

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
        "SUPREMELEADERKYLOREN": "kyloren_tros",
        "KYLORENUNMASKED": "kylo_unmasked",
        "MOTHERTALZIN": "nightsisters_talzin",
        "NIGHTSISTERZOMBIE": "nightsisters_zombie",
        "NIGHTSISTERINITIATE": "nightsister_initiate",
        "ASAJVENTRESS": "ventress",
        "TALIA": "nightsister_talia",
        "FIRSTORDERTIEPILOT": "firstordertiepilot",
        "FIRSTORDERSPECIALFORCESPILOT": "firstorder_pilot",
        "GENERALHUX": "generalhux",
        "MARAJADE": "marajade",
        "DARTHNIHILUS": "nihilus",
        "ROYALGUARD": "royalguard",
        "PADMEAMIDALA": "padme_geonosis",

        # --- Clones ---
        "CT7567": "trooperclone_rex",
        "CC2224": "trooperclone_cody",
        "CT210408": "trooperclone_echo",
        "CT5555": "trooperclone_fives",
        "ARCTROOPER501ST": "trooperclone_arc",
        "CLONESERGEANTPHASEI": "trooperclonegreen",

        # --- Autres Persos ---
        "GOPHERANTS": "groguanz",
        "HERASYNDULLAS3": "hera_s3",
        "HOTHLEIA": "leiahoth",
        "HOTHREBELSCOUT": "rebelhothscout",
        "HOTHREBELSOLDIER": "rebelhoth",
        "CHIEFNEBIT": "jawa_nebit",
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

        # --- Nouveaux Overrides Persos ---
        "ADMINISTRATORLANDO": "landobespin",
        "ADMIRALACKBAR": "ackbaradmiral",
        "BARRISSOFFEE": "barriss_light",
        "BIGGSDARKLIGHTER": "rebelpilot_biggs",
        "CHIEFCHIRPA": "ewok_chirpa",
        "COLONELSTARCK": "colonel_stark",
        "DARTHREVAN": "sithrevan",
        "HUMANTHUG": "mob_enforcer",
        "IG90": "ig-90",
        "OLDBENKENOBI": "obiwanep4",

        # --- Vaisseaux ---
        "GEONOSIANSTARFIGHTER1": "geonosis_fighter_sunfac",
        "GEONOSIANSTARFIGHTER2": "geonosis_fighter_spy",
        "GEONOSIANSTARFIGHTER3": "geonosis_fighter_soldier",
        "CAPITALMONCALAMARICRUISER": "moncalamarilibertycruiser",
        "CAPITALJEDICRUISER": "negotiator",
        "COMMANDSHUTTLE": "upsilon_shuttle_kylo",
        "EMPERORSSHUTTLE": "imperialshuttle",

        # --- Nouveaux Overrides Vaisseaux ---
        "JEDISTARFIGHTERPLOKOON": "jedi_fighter_bladeofdorin",
        "JEDISTARFIGHTERANAKIN": "jedi_fighter_anakin",
        "JEDISTARFIGHTERAHSOKA": "jedi_fighter_ahsoka",
        "JEDISTARFIGHTERCONSULAR": "jedi_fighter",
        "CLONESERGEANTARC170": "arc170",
        "REXARC170": "arc170_02",
        "MEONECROW": "comeuppance",
        "SITHBOMBER": "b28extinctionclassbomber",
        "SITHINFILTRATOR": "sithinfiltrator",
        "SITHFIGHTER": "sithfighter",
        "TIEINTERCEPTORPROTOTYPE": "tie_interceptor_prototype",
        "UWINGHERO": "uwing_hero",
        "UWING": "uwing",
        "XWINGBLACKONE": "xwing_blackone",
        "XWINGRED2": "xwing_red2",
        "XWINGRED3": "xwing_red3",
        "XWINGRESISTANCE": "xwing_resistance",
        "YWINGBTLB": "ywing_btlb",
        "YWING": "ywing",
        "BWINGREBEL": "bwingrebel",
    }

    targets = []
    if bid_upper in MANUAL_MAPPING:
        targets.append(MANUAL_MAPPING[bid_upper])

    if unit.get("thumbnail_name"):
        targets.append(unit["thumbnail_name"])

    targets.append(bid_lower)
    targets.append(bid_lower.replace("capital", "").replace("ship_", "").replace("gl", ""))

    prefixes = ["charui_", ""]
    
    def is_path_available(p: Path) -> bool:
        # On rejette si c'est déjà validé pour un autre perso
        return p.as_posix() not in _validated_image_paths

    for t in targets:
        if not t: continue
        clean = str(t).replace(".png", "").replace("tex.avatars_", "")
        for pref in prefixes:
            path = target_dir / f"{pref}{clean}.png"
            if path.exists() and is_path_available(path): 
                return path

    # Recherche floue intelligente améliorée
    if target_dir.exists():
        import difflib
        best_match = None
        best_ratio = 0.0
        search = bid_lower.replace("_", "").replace("charui", "")

        for p in target_dir.glob("*.png"):
            if not is_path_available(p):
                continue
                
            fname = p.stem.lower().replace("_", "").replace("charui", "")

            # 1. Correspondance exacte après nettoyage
            if search == fname:
                return p

            # 2. Un est sous-chaîne de l'autre
            if search in fname or fname in search:
                return p

            # 3. Calcul du ratio standard
            ratio = difflib.SequenceMatcher(None, search, fname).ratio()

            # 4. Détection d'anagrammes (ex: "admiralackbar" et "ackbaradmiral")
            if sorted(search) == sorted(fname):
                ratio = max(ratio, 0.95)

            # 5. Détection de jetons communs (ex: "biggs" dans "rebelpilot_biggs")
            tokens = p.stem.lower().split("_")
            for token in tokens:
                if token != "charui" and len(token) >= 4:
                    if token in search or search in token:
                        ratio = max(ratio, 0.70)

            # 6. Plus long segment commun
            if len(search) >= 5 and len(fname) >= 5:
                match = difflib.SequenceMatcher(None, search, fname).find_longest_match(0, len(search), 0, len(fname))
                if match.size >= 5:
                    ratio = max(ratio, match.size / max(len(search), len(fname)))

            if ratio > best_ratio:
                best_ratio = ratio
                best_match = p

        if best_match and best_ratio >= 0.55:
            log.info("Fuzzy match trouvé : %s -> %s (ratio: %.2f)", base_id, best_match.name, best_ratio)
            return best_match

    return target_dir / f"charui_{bid_lower}.png"

def download_portrait(base_id: str) -> bool:
    """
    Tente de télécharger le portrait depuis swgoh.gg si absent du cache local.
    Retourne True si le fichier existe après la tentative.
    """
    import urllib.request

    bid_lower = base_id.lower()

    # Vérifie si un fichier existe déjà dans le cache (via la logique fuzzy)
    existing = get_portrait_path(base_id)
    if existing.exists():
        return True

    # URLs candidates à essayer dans l'ordre
    urls_to_try = [
        f"https://swgoh.gg/static/img/assets/tex.avatars_{bid_lower}.png",
        f"https://game-assets.swgoh.gg/textures/tex.avatars_{bid_lower}.png",
    ]

    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PORTRAITS_DIR / f"{bid_lower}.png"

    for url in urls_to_try:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    dest.write_bytes(resp.read())
                    log.info("Portrait téléchargé : %s -> %s", base_id, dest.name)
                    return True
        except Exception as e:
            log.debug("Échec téléchargement portrait %s depuis %s : %s", base_id, url, e)

    log.warning("Portrait introuvable pour %s", base_id)
    return False

