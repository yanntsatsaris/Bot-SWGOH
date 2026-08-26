"""
scripts/fleet_tier_sb_worker.py
Scrape la Tier List Fleet (attaque et/ou defense) sur swgoh.gg/tier-list/fleet/.
Usage:
    python fleet_tier_sb_worker.py <output_file> [side] [league]
    side  : offense | defense  (defaut: offense)
    league: kyber | aurodium | chromium | bronzium | carbonite  (defaut: kyber)
"""
import sys
import os
import json
import platform
import re

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from seleniumbase import SB

# Mapping slug ligue > parametre URL
LEAGUE_MAP = {
    "kyber":     "",
    "aurodium":  "aurodium",
    "chromium":  "chromium",
    "bronzium":  "bronzium",
    "carbonite": "carbonite",
}

# Mapping nom affiche sur la page > base_id capital ship
CAPITAL_SHIP_NAME_TO_ID = {
    "Leviathan":         "CAPITALLEVIATHAN",
    "Profundity":        "CAPITALPROFUNDITY",
    "Executor":          "CAPITALEXECUTOR",
    "Negotiator":        "CAPITALNEGOTIATOR",
    "Home One":          "CAPITALHOMEONE",
    "Chimaera":          "CAPITALCHIMAERA",
    "Finalizer":         "CAPITALFINALIZER",
    "Executrix":         "CAPITALMACE",
    "Malevolence":       "CAPITALMALEVOLENCE",
    "Raddus":            "CAPITALRADDUS",
    "Venator":           "CAPITALVENATOR",
}

# Mapping alt name > base_id vaisseaux de soutien (fallback statique)
SUPPORT_SHIP_FALLBACK = {
    "Hound's Tooth":                    "HOUNDSTOOTH",
    "Razor Crest":                       "RAZOR_CREST",
    "Boba Fett's Starfighter":          "BOBAFETTSHIP",
    "IG-2000":                           "IG2000",
    "Xanadu Blood":                      "XANADUBLOOD",
    "Gauntlet Starfighter":              "GAUNTLETSTARFIGHTER",
    "Scimitar":                          "SCIMITAR",
    "Sun Fac's Geonosian Starfighter":  "SUNFACSHIP",
    "Geonosian Spy's Starfighter":      "GEONOSIANSPYSHIP",
    "Geonosian Solar Sailer":            "GEOSOLARSHIP",
    "Han's Millennium Falcon":          "HANSOLO_SHIP",
    "Millennium Falcon":                 "MILLENNIUMFALCON",
    "Ghost":                             "GHOST",
    "Phantom II":                        "PHANTOM2",
    "Outrider":                          "OUTRIDER",
    "Ebon Hawk":                         "EBONHAWK",
    "A-wing":                            "AWING",
    "B-wing":                            "BWING",
    "Y-wing":                            "YWING",
    "TIE Advanced x1":                   "TIEADVX1",
    "TIE Bomber":                        "TIEBOMBER",
    "TIE Fighter":                       "TIEFIGHTER",
    "TIE Interceptor":                   "TIEINTERCEPTOR",
    "TIE Silencer":                      "TIESILENCER",
    "TIE Reaper":                        "TIEREAPER",
    "Vulture Droid":                     "VULTUREDROID",
    "Hyena Bomber":                      "HYENABOMBER",
    "Magnaguard Fighter":                "MAGNAGUARDSHIP",
    "Sith Bomber":                       "SITHBOMBER",
    "Sith Fighter":                      "SITHFIGHTER",
    "Fury-class Interceptor":            "FURY_FIGHTER",
    "Anakin's Eta-2 Starfighter":       "ANAKINETA2",
    "ARC-170 Starfighter":               "ARC170CLONESERGEANT",
    "Clone Z-95":                        "Z95CLONESERGEANT",
    "Plo Koon's Delta-7 Starfighter":   "PLOKOONSHIP",
    "BTL-B Y-wing":                      "BTLBYWING",
    "UT-60D U-wing":                     "UWING",
    "Darth Vader's TIE Advanced":       "TIEADVDARTHVADER",
    "TIE Defender":                      "TIEDEFENDER",
    "TIE Echelon":                       "TIEECHELON",
    "First Order TIE Fighter":           "FOTIESILENCER",
    "First Order TIE Silencer":          "FOTIESILENCER",
    "Kylo Ren's Command Shuttle":       "KYLORENATSHUTTLE",
    "First Order Special Forces TIE":    "FOTIESPECIALFORCES",
    "Mace Windu's Jedi Starfighter":    "MACEWINDUSHIP",
    "Rex's ARC-170":                    "ARC170REX",
    "Ahsoka Tano's Jedi Starfighter":   "AHSOKATANOSHIP",
    "Biggs Darklighter's X-wing":       "BIGGSXWING",
    "Wedge Antilles's X-wing":          "WEDGEXWING",
    "Poe Dameron's X-wing":             "POEDAMERONXWING",
    "T-70 X-wing":                       "T70XWING",
}


def extract_base_id_from_alt(alt_text: str) -> str:
    if not alt_text:
        return ""
    for name, bid in CAPITAL_SHIP_NAME_TO_ID.items():
        if name.lower() in alt_text.lower():
            return bid
    for name, bid in SUPPORT_SHIP_FALLBACK.items():
        if name.lower() in alt_text.lower() or alt_text.lower() in name.lower():
            return bid
    normalized = re.sub(r"[^a-zA-Z0-9]", "_", alt_text).upper().strip("_")
    return normalized


def parse_tier_list_page(page_source: str, side: str, league: str) -> list:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_source, "html.parser")
    results = []
    rank = 0
    current_tier = "S"

    # Detecter les entetes de tier (S Tier, A Tier, etc.)
    # swgoh.gg utilise des sections avec titres
    all_divs = soup.find_all("div")
    processed_capitals = set()

    for div in all_divs:
        # Detecter un changement de tier via le texte du div
        direct_text = "".join(t for t in div.strings if t.parent == div).strip()
        tier_match = re.match(r"^\s*([SABCD])\s*(?:Tier)?\s*$", direct_text, re.I)
        if tier_match:
            current_tier = tier_match.group(1).upper()
            continue

        # Chercher les images avec w-12 (capital) et w-10 (supports)
        large_imgs = div.find_all("img", class_=lambda c: c and "w-12" in c if c else False)
        small_imgs = div.find_all("img", class_=lambda c: c and ("w-10" in c or "w-8" in c) if c else False)

        if not large_imgs and not small_imgs:
            continue

        if large_imgs:
            cap_img = large_imgs[0]
            supports = small_imgs[:3]
        else:
            continue

        capital_alt = cap_img.get("alt") or cap_img.get("title") or ""
        capital_id = extract_base_id_from_alt(capital_alt)

        if not capital_id or capital_id in processed_capitals:
            continue
        processed_capitals.add(capital_id)

        member_ids = []
        for img in supports:
            alt = img.get("alt") or img.get("title") or ""
            mid = extract_base_id_from_alt(alt)
            if mid and mid != capital_id:
                member_ids.append(mid)

        # Stats
        elo = win_pct = hold_pct = battles = builds_count = None
        for span in div.select("span, div"):
            t = span.get_text(strip=True)
            if "%" in t and len(t) < 10:
                try:
                    v = float(t.replace("%", "").replace(",", ".").strip())
                    if side == "defense" and hold_pct is None:
                        hold_pct = v
                    elif win_pct is None:
                        win_pct = v
                except:
                    pass
            elif re.match(r"^[0-9,]{3,6}$", t):
                n = int(t.replace(",", ""))
                if n > 500 and elo is None:
                    elo = n
                elif battles is None:
                    battles = n

        rank += 1
        results.append({
            "tier":         current_tier,
            "rank":         rank,
            "side":         side,
            "league":       league,
            "season":       "current",
            "format":       "5v5",
            "capital_ship": capital_id,
            "members_ids":  member_ids,
            "elo":          elo,
            "win_pct":      win_pct,
            "hold_pct":     hold_pct,
            "battles":      battles,
            "builds_count": builds_count,
            "capital_name": capital_alt,
        })

    return results


def scrape_fleet_tier(output_file: str, side: str = "offense", league: str = "kyber"):
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if not os.path.exists(project_dir):
        project_dir = os.getcwd()

    is_windows = (platform.system() == "Windows")
    if not is_windows:
        os.environ["HOME"] = project_dir
        os.environ["XDG_CONFIG_HOME"] = os.path.join(project_dir, ".config")

    display = None
    exit_code = 1

    try:
        if not is_windows:
            from pyvirtualdisplay import Display
            display = Display(visible=0, size=(1920, 1080))
            display.start()

        profile_dir = os.path.join(project_dir, "chrome_profile")
        out_dir = os.path.dirname(os.path.abspath(output_file))
        os.makedirs(out_dir, exist_ok=True)

        base_url = "https://swgoh.gg/tier-list/fleet/?rank=best"
        if side == "defense":
            base_url = "https://swgoh.gg/tier-list/fleet/?side=defense&rank=best"
        league_param = LEAGUE_MAP.get(league.lower(), "")
        if league_param:
            base_url += f"&league={league_param}"

        print(f"[FLEET-TIER] URL: {base_url}", flush=True)

        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            sb.uc_open_with_reconnect(base_url, reconnect_time=4)

            quick_check = sb.get_page_source()
            if any(cf in quick_check for cf in ["Just a moment", "Un instant", "cf-turnstile", "Checking your browser"]):
                print("[FLEET-TIER] Cloudflare detecte, tentative CAPTCHA...", flush=True)
                try:
                    sb.uc_gui_click_captcha()
                except:
                    pass
                sb.sleep(10)
            else:
                sb.sleep(5)

            # Attendre le chargement de la page
            for _ in range(30):
                src = sb.get_page_source()
                if "w-12" in src or "tier-list" in src.lower():
                    break
                sb.sleep(1)

            page_source = sb.get_page_source()

        # Sauvegarder le HTML pour debug
        debug_html = output_file.replace(".json", "_debug.html")
        with open(debug_html, "w", encoding="utf-8") as f:
            f.write(page_source)
        print(f"[FLEET-TIER] HTML brut sauvegarde: {debug_html}", flush=True)

        results = parse_tier_list_page(page_source, side, league)
        print(f"[FLEET-TIER] {len(results)} equipes trouvees pour {side}/{league}", flush=True)

        final = {
            "side":    side,
            "league":  league,
            "season":  "current",
            "format":  "5v5",
            "entries": results,
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final, f, ensure_ascii=False, indent=2)

        print(f"[FLEET-TIER] Resultat sauvegarde: {output_file}", flush=True)
        exit_code = 0

    except Exception as e:
        import traceback
        print(f"[FLEET-TIER] ERREUR CRITIQUE: {e}", flush=True)
        traceback.print_exc()
        exit_code = 1
    finally:
        if display is not None:
            try:
                display.stop()
            except:
                pass
        sys.exit(exit_code)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python fleet_tier_sb_worker.py <output_file> [offense|defense] [kyber|aurodium|...]")
        sys.exit(1)

    out_file = sys.argv[1]
    side_arg = sys.argv[2] if len(sys.argv) > 2 else "offense"
    league_arg = sys.argv[3] if len(sys.argv) > 3 else "kyber"

    print(f"[FLEET-TIER] Lancement side={side_arg} league={league_arg} -> {out_file}", flush=True)
    scrape_fleet_tier(out_file, side_arg, league_arg)
