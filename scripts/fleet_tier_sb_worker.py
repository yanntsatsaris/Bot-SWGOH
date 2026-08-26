"""
scripts/fleet_tier_sb_worker.py
Scrape la Tier List Fleet (attaque et/ou defense) sur swgoh.gg/tier-list/fleet/.
"""
import sys
import os
import json
import platform
import re

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from seleniumbase import SB

LEAGUE_MAP = {
    "kyber":     "",
    "aurodium":  "aurodium",
    "chromium":  "chromium",
    "bronzium":  "bronzium",
    "carbonite": "carbonite",
}

CAPITAL_SHIP_NAME_TO_ID = {
    "LEVIATHAN":         "CAPITALLEVIATHAN",
    "PROFUNDITY":        "CAPITALPROFUNDITY",
    "EXECUTOR":          "CAPITALEXECUTOR",
    "NEGOTIATOR":        "CAPITALNEGOTIATOR",
    "HOME ONE":          "CAPITALMONCALAMARICRUISER",
    "CHIMAERA":          "CAPITALCHIMAERA",
    "FINALIZER":         "CAPITALFINALIZER",
    "EXECUTRIX":         "CAPITALSTARDESTROYER",
    "MALEVOLENCE":       "CAPITALMALEVOLENCE",
    "RADDUS":            "CAPITALRADDUS",
    "ENDURANCE":         "CAPITALJEDICRUISER",
}

ALL_CAPITALS = set(CAPITAL_SHIP_NAME_TO_ID.values()) | set(CAPITAL_SHIP_NAME_TO_ID.keys())


def normalize_ship_id(raw_str: str) -> str:
    if not raw_str:
        return ""
    upper = raw_str.upper().strip()
    if upper in CAPITAL_SHIP_NAME_TO_ID:
        return CAPITAL_SHIP_NAME_TO_ID[upper]
    for name, bid in CAPITAL_SHIP_NAME_TO_ID.items():
        if name in upper:
            return bid
    return re.sub(r"[^a-zA-Z0-9_]", "", upper)


def parse_tier_list_page(page_source: str, side: str, league: str) -> list:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(page_source, "html.parser")
    results = []
    rank = 0
    processed_capitals = set()

    # Stratégie robuste : trouver tous les éléments/liens/tooltips d'unités dans l'ordre du DOM
    # Chaque capital ship annonce une nouvelle composition
    
    # 1. Identifier tous les éléments d'unités sur la page
    unit_elements = []
    # Recherche large de tous les divs avec tooltip ou liens /ships/ ou images de vaisseaux
    for tag in soup.find_all(True):
        u_id = ""
        if tag.has_attr("data-unit-def-tooltip-app"):
            u_id = tag["data-unit-def-tooltip-app"]
        elif tag.name == "a" and "/ships/" in tag.get("href", ""):
            u_id = tag["href"].rstrip("/").split("/")[-1].upper()
        elif tag.name == "img" and tag.get("alt"):
            norm = normalize_ship_id(tag.get("alt"))
            if norm in ALL_CAPITALS or "CAPITAL" in norm:
                u_id = norm

        if u_id:
            norm_id = normalize_ship_id(u_id)
            if norm_id:
                # Stocker le tag et son id
                unit_elements.append((norm_id, tag))

    # Regrouper les compositions : un capital ship + les 3 unités suivantes
    i = 0
    current_tier = "S"
    while i < len(unit_elements):
        uid, tag = unit_elements[i]
        is_cap = (uid in CAPITAL_SHIP_NAME_TO_ID.values()) or ("CAPITAL" in uid)
        
        if is_cap and uid not in processed_capitals:
            processed_capitals.add(uid)
            cap_id = uid
            
            # Prendre les 3 unités suivantes qui ne sont pas des capital ships
            members = []
            j = i + 1
            while j < len(unit_elements) and len(members) < 3:
                next_uid, next_tag = unit_elements[j]
                next_is_cap = (next_uid in CAPITAL_SHIP_NAME_TO_ID.values()) or ("CAPITAL" in next_uid)
                if next_is_cap:
                    break  # Prochaine équipe
                if next_uid not in members and next_uid != cap_id:
                    members.append(next_uid)
                j += 1

            # Chercher le conteneur parent pour extraire stats et tier
            parent = tag.parent
            win_pct = None
            hold_pct = None
            elo = None
            battles = None
            
            # Remonter 3-4 niveaux de parents pour trouver les stats
            for _ in range(5):
                if not parent:
                    break
                p_text = parent.get_text()
                # Tier
                m_t = re.search(r"\b([SABCD])\s*(?:Tier)?\b", p_text, re.I)
                if m_t:
                    current_tier = m_t.group(1).upper()
                
                # Stats
                for txt in parent.select(".font-bold, span, td, div"):
                    t = txt.get_text(strip=True)
                    if "%" in t and len(t) <= 8:
                        try:
                            v = float(t.replace("%", "").replace(",", ".").strip())
                            if side == "defense" and hold_pct is None:
                                hold_pct = v
                            elif win_pct is None:
                                win_pct = v
                        except:
                            pass
                    elif re.match(r"^\d{3,6}$", t):
                        n = int(t)
                        if n > 500 and elo is None:
                            elo = n
                        elif battles is None:
                            battles = n
                parent = parent.parent

            rank += 1
            results.append({
                "tier":         current_tier,
                "rank":         rank,
                "side":         side,
                "league":       league,
                "season":       "current",
                "format":       "5v5",
                "capital_ship": cap_id,
                "members_ids":  members,
                "elo":          elo,
                "win_pct":      win_pct,
                "hold_pct":     hold_pct,
                "battles":      battles,
                "builds_count": None,
            })
            i = j
        else:
            i += 1

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

            for _ in range(25):
                src = sb.get_page_source()
                if "tier-list" in src.lower() or "data-unit-def-tooltip-app" in src or "panel" in src:
                    break
                sb.sleep(0.5)

            page_source = sb.get_page_source()

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
