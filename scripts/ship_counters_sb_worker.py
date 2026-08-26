"""
scripts/ship_counters_sb_worker.py
Scrape les counters de vaisseaux sur swgoh.gg/gac/ship-counters/{CAPITAL_ID}/
Supporte le mode single ('CAPITALLEVIATHAN') et le mode batch ('ALL') pour une vitesse maximale.
"""
import sys
import os
import json
import platform
import re
import time

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


def _scrape_single_capital_flow(sb, cap_id: str, season_id: str, is_first: bool = False, d_members: str = "", d_reinforcements: str = "") -> list:
    """Scrape les pages 1 a 5 d'un capital ship dans la session Chrome active."""
    from bs4 import BeautifulSoup

    capital_slug = cap_id.upper()
    counters_data = []

    base_url = f"https://swgoh.gg/gac/ship-counters/{capital_slug}/?cutoff=0"
    if season_id and season_id != "current":
        base_url += f"&season_id={season_id}"
    if d_members:
        base_url += f"&d_member={d_members}"
    if d_reinforcements:
        base_url += f"&d_reinforcement={d_reinforcements}"
    if d_reinforcements:
        base_url += f"&d_reinforcement={d_reinforcements}"

    for page in range(1, 6):
        page_url = f"{base_url}&page={page}"
        print(f"[SHIP-COUNTERS] [{cap_id}] Page {page}: {page_url}", flush=True)
        sb.uc_open_with_reconnect(page_url, reconnect_time=2)

        quick_check = sb.get_page_source()
        if is_first and page == 1 and any(cf in quick_check for cf in ["Just a moment", "Un instant", "cf-turnstile", "Checking your browser"]):
            print("[SHIP-COUNTERS] Cloudflare detecte au demarrage...", flush=True)
            try:
                sb.uc_gui_click_captcha()
            except:
                pass
            sb.sleep(8)
        else:
            # Attente reactive rapide (0.15s interval) des que les panels apparaissent
            for _ in range(20):
                if sb.is_element_present("div.panel"):
                    break
                sb.sleep(0.15)
            sb.sleep(0.3)  # Pause legere et naturelle anti-Cloudflare

        page_source = sb.get_page_source()
        soup = BeautifulSoup(page_source, "html.parser")

        counter_panels = soup.select("div.panel.panel--size-sm") or soup.select("div.panel")
        page_counters = []
        for panel in counter_panels:
            parsed = parse_ship_counter_panel(panel, cap_id)
            if parsed and parsed["atk_capital"]:
                page_counters.append(parsed)

        if not page_counters:
            break

        counters_data.extend(page_counters)
        if len(page_counters) < 40:
            break

    print(f"[SHIP-COUNTERS] [{cap_id}] OK: {len(counters_data)} counters", flush=True)
    return counters_data


def scrape_ship_counters(target_arg: str, output_path: str, season_id: str = "current", d_members: str = "", d_reinforcements: str = ""):
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if not os.path.exists(project_dir):
        project_dir = os.getcwd()

    is_windows = (platform.system() == "Windows")
    if not is_windows:
        os.environ["HOME"] = project_dir
        os.environ["XDG_CONFIG_HOME"] = os.path.join(project_dir, ".config")

    display = None
    exit_code = 1
    start_time = time.time()

    try:
        if not is_windows:
            from pyvirtualdisplay import Display
            display = Display(visible=0, size=(1920, 1080))
            display.start()

        profile_dir = os.path.join(project_dir, "chrome_profile")
        is_batch = (target_arg.upper() == "ALL")
        capitals_to_scrape = ALL_CAPITAL_IDS if is_batch else [target_arg.upper()]

        print(f"[SHIP-COUNTERS] Mode: {'BATCH (11 vaisseaux)' if is_batch else target_arg} -> {output_path}", flush=True)

        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            from bs4 import BeautifulSoup

            # 1. Detection saison
            target_season = season_id
            if season_id == "current":
                init_url = "https://swgoh.gg/gac/ship-counters/CAPITALLEVIATHAN/?cutoff=0"
                sb.uc_open_with_reconnect(init_url, reconnect_time=3)
                quick_check = sb.get_page_source()
                if any(cf in quick_check for cf in ["Just a moment", "Un instant", "cf-turnstile", "Checking your browser"]):
                    try:
                        sb.uc_gui_click_captcha()
                    except:
                        pass
                    sb.sleep(8)
                else:
                    sb.sleep(3)

                soup = BeautifulSoup(sb.get_page_source(), "html.parser")
                detected = extract_seasons_from_dropdown(soup)
                target_season = detected[0] if detected else "current"
                print(f"[SHIP-COUNTERS] Saison active: {target_season}", flush=True)

            # 2. Scraping des vaisseaux dans la MEME session Chrome
            all_results = {}
            for i, cap_id in enumerate(capitals_to_scrape):
                c_data = _scrape_single_capital_flow(sb, cap_id, target_season, is_first=(i == 0), d_members=d_members if not is_batch else "", d_reinforcements=d_reinforcements if not is_batch else "")
                all_results[cap_id] = {
                    "def_capital": cap_id,
                    "season_id": target_season,
                    "counters": c_data
                }

        # 3. Sauvegarde des fichiers de sortie
        if is_batch:
            os.makedirs(output_path, exist_ok=True)
            for cap_id, res in all_results.items():
                fpath = os.path.join(output_path, f"ship_counters_{cap_id}.json")
                with open(fpath, "w", encoding="utf-8") as f:
                    json.dump(res, f, ensure_ascii=False, indent=2)
        else:
            out_dir = os.path.dirname(os.path.abspath(output_path))
            os.makedirs(out_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(all_results.get(target_arg.upper(), {}), f, ensure_ascii=False, indent=2)

        elapsed = time.time() - start_time
        total_counters = sum(len(r.get("counters", [])) for r in all_results.values())
        print(f"[SHIP-COUNTERS] Termine en {elapsed:.1f}s ! Total: {total_counters} counters.", flush=True)
        exit_code = 0

    except Exception as e:
        import traceback
        print(f"[SHIP-COUNTERS] ERREUR: {e}", flush=True)
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
        print("Usage: python ship_counters_sb_worker.py <CAPITAL_ID|ALL> <output_file|output_dir> [season_id]")
        sys.exit(1)

    target_cmd = sys.argv[1].upper()
    out_target = sys.argv[2]
    season_arg = sys.argv[3] if len(sys.argv) > 3 else "current"
    d_mems_arg = sys.argv[4] if len(sys.argv) > 4 else ""
    d_reinf_arg = sys.argv[5] if len(sys.argv) > 5 else ""

    scrape_ship_counters(target_cmd, out_target, season_arg, d_mems_arg, d_reinf_arg)
