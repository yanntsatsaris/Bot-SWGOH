"""
scripts/ship_counters_sb_worker.py
Scrape les counters de vaisseaux sur swgoh.gg/gac/ship-counters/{CAPITAL_ID}/
"""
import sys
import os
import json
import platform
import re

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

from seleniumbase import SB

ALL_CAPITAL_IDS = [
    "CAPITALLEVIATHAN",
    "CAPITALPROFUNDITY",
    "CAPITALEXECUTOR",
    "CAPITALNEGOTIATOR",
    "CAPITALMONCALAMARICRUISER",
    "CAPITALCHIMAERA",
    "CAPITALFINALIZER",
    "CAPITALSTARDESTROYER",
    "CAPITALMALEVOLENCE",
    "CAPITALRADDUS",
    "CAPITALJEDICRUISER",
]


def extract_seasons_from_dropdown(soup):
    import urllib.parse
    discovered = []
    dropdown_menu = soup.select_one("details.dropdown ul.dropdown-content")
    elements_to_scan = dropdown_menu.find_all("a") if dropdown_menu else soup.find_all("a")
    for a in elements_to_scan:
        href = a.get("href", "")
        parsed = urllib.parse.urlparse(href)
        params = urllib.parse.parse_qs(parsed.query)
        if "season_id" in params:
            sid = params["season_id"][0]
            if sid not in discovered:
                discovered.append(sid)
    return discovered


def parse_ship_counter_panel(panel, def_capital_id: str) -> dict | None:
    # 1. Equipe attaquante (droite)
    atk_container = panel.select_one("div.justify-center.lg\\:justify-end")
    if not atk_container:
        for div in panel.find_all("div"):
            cls = div.get("class", [])
            if any("justify-end" in c for c in cls):
                atk_container = div
                break
                
    if not atk_container:
        j_divs = panel.select("div.justify-center")
        if len(j_divs) >= 2:
            atk_container = j_divs[1]
        elif len(j_divs) == 1:
            atk_container = j_divs[0]

    if not atk_container:
        return None

    atk_units = [
        div.get("data-unit-def-tooltip-app")
        for div in atk_container.select("[data-unit-def-tooltip-app]")
        if div.get("data-unit-def-tooltip-app")
    ]
    if not atk_units:
        for a in atk_container.find_all("a"):
            href = a.get("href", "")
            if "/ships/" in href:
                s_id = href.rstrip("/").split("/")[-1].upper()
                if s_id:
                    atk_units.append(s_id)

    if not atk_units:
        return None

    atk_capital = atk_units[0]
    atk_members = atk_units[1:]

    # 2. Equipe defensive (gauche)
    def_container = panel.select_one("div.justify-center.lg\\:justify-start")
    if not def_container:
        for div in panel.find_all("div"):
            cls = div.get("class", [])
            if any("justify-start" in c for c in cls):
                def_container = div
                break

    def_members = []
    if def_container:
        def_units = [
            div.get("data-unit-def-tooltip-app")
            for div in def_container.select("[data-unit-def-tooltip-app]")
            if div.get("data-unit-def-tooltip-app")
        ]
        if not def_units:
            for a in def_container.find_all("a"):
                href = a.get("href", "")
                if "/ships/" in href:
                    s_id = href.rstrip("/").split("/")[-1].upper()
                    if s_id:
                        def_units.append(s_id)
        def_members = def_units[1:] if len(def_units) > 1 else []

    # 3. Stats
    seen = 0
    win_pct = 0.0
    avg_banners = 0.0
    stats_container = panel.select_one("div.whitespace-nowrap")
    if not stats_container:
        for div in panel.find_all("div"):
            if "whitespace-nowrap" in " ".join(div.get("class", [])):
                stats_container = div
                break

    if stats_container:
        stat_divs = stats_container.select("div.flex-1 > div.font-bold")
        if not stat_divs:
            stat_divs = stats_container.select(".font-bold")
        if len(stat_divs) >= 3:
            try:
                seen = int(stat_divs[0].text.strip().replace(",", ""))
                win_pct = float(stat_divs[1].text.strip().replace("%", ""))
                avg_banners = float(stat_divs[2].text.strip())
            except (ValueError, IndexError):
                pass
        elif len(stat_divs) >= 2:
            try:
                seen = int(stat_divs[0].text.strip().replace(",", ""))
                win_pct = float(stat_divs[1].text.strip().replace("%", ""))
            except:
                pass

    return {
        "def_capital":     def_capital_id,
        "def_members_ids": def_members,
        "atk_capital":     atk_capital,
        "atk_members_ids": atk_members,
        "seen":            seen,
        "win_pct":         win_pct,
        "avg_banners":     avg_banners,
    }


def scrape_ship_counters(def_capital_id: str, output_file: str, season_id: str = "current"):
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

        capital_slug = def_capital_id.upper()
        print(f"[SHIP-COUNTERS] Capital: {def_capital_id} -> URL slug: {capital_slug}", flush=True)

        counters_data = []
        detected_seasons = []

        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            from bs4 import BeautifulSoup

            # 1. Détection saison si 'current'
            target_season = season_id
            if season_id == "current":
                init_url = f"https://swgoh.gg/gac/ship-counters/{capital_slug}/?cutoff=0"
                print(f"[SHIP-COUNTERS] Detection saison via {init_url}...", flush=True)
                sb.uc_open_with_reconnect(init_url, reconnect_time=4)

                quick_check = sb.get_page_source()
                if any(cf in quick_check for cf in ["Just a moment", "Un instant", "cf-turnstile", "Checking your browser"]):
                    print("[SHIP-COUNTERS] Cloudflare detecte...", flush=True)
                    try:
                        sb.uc_gui_click_captcha()
                    except:
                        pass
                    sb.sleep(10)
                else:
                    sb.sleep(4)

                soup = BeautifulSoup(sb.get_page_source(), "html.parser")
                detected_seasons = extract_seasons_from_dropdown(soup)
                
                if detected_seasons:
                    target_season = detected_seasons[0]
                    print(f"[SHIP-COUNTERS] Saison detectee: {target_season}", flush=True)
                else:
                    target_season = ""

            base_url = f"https://swgoh.gg/gac/ship-counters/{capital_slug}/?cutoff=0"
            if target_season:
                base_url += f"&season_id={target_season}"

            for page in range(1, 6):
                page_url = f"{base_url}&page={page}"
                print(f"[SHIP-COUNTERS] Page {page}: {page_url}", flush=True)
                sb.uc_open_with_reconnect(page_url, reconnect_time=3)

                quick_check = sb.get_page_source()
                if page == 1 and any(cf in quick_check for cf in ["Just a moment", "Un instant", "cf-turnstile", "Checking your browser"]):
                    try:
                        sb.uc_gui_click_captcha()
                    except:
                        pass
                    sb.sleep(10)
                else:
                    sb.sleep(3 if page == 1 else 2)

                panels_found = False
                for _ in range(15):
                    if sb.is_element_present("div.panel"):
                        panels_found = True
                        break
                    sb.sleep(0.4)

                if not panels_found:
                    print(f"[SHIP-COUNTERS] Page {page}: fin des panels.", flush=True)
                    break

                page_source = sb.get_page_source()
                soup = BeautifulSoup(page_source, "html.parser")

                counter_panels = soup.select("div.panel.panel--size-sm") or soup.select("div.panel")
                print(f"[SHIP-COUNTERS] Page {page}: {len(counter_panels)} panneaux trouves.", flush=True)

                page_counters = []
                for panel in counter_panels:
                    parsed = parse_ship_counter_panel(panel, def_capital_id)
                    if parsed and parsed["atk_capital"]:
                        page_counters.append(parsed)

                if not page_counters:
                    print(f"[SHIP-COUNTERS] Page {page}: 0 counters extraits.", flush=True)
                    break

                counters_data.extend(page_counters)
                print(f"[SHIP-COUNTERS] Page {page}: +{len(page_counters)} counters. Total: {len(counters_data)}", flush=True)

                if len(page_counters) < 40:
                    break

        final = {
            "def_capital": def_capital_id,
            "season_id":   target_season or "current",
            "counters":    counters_data,
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(final, f, ensure_ascii=False, indent=2)

        print(f"[SHIP-COUNTERS] Total: {len(counters_data)} counters sauvegardes -> {output_file}", flush=True)
        exit_code = 0

    except Exception as e:
        import traceback
        print(f"[SHIP-COUNTERS] ERREUR CRITIQUE: {e}", flush=True)
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
    if len(sys.argv) < 3:
        print("Usage: python ship_counters_sb_worker.py <def_capital_id> <output_file> [season_id]")
        sys.exit(1)

    capital_id = sys.argv[1].upper()
    out_file = sys.argv[2]
    season = sys.argv[3] if len(sys.argv) > 3 else "current"

    print(f"[SHIP-COUNTERS] Lancement capital={capital_id} season={season} -> {out_file}", flush=True)
    scrape_ship_counters(capital_id, out_file, season)
