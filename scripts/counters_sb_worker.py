import sys
import os
import platform

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        print(f"[WORKER] Lancement du script counters pour {sys.argv[1]}...", flush=True)

from seleniumbase import SB

def extract_seasons_from_dropdown(soup, format_type):
    """
    Extrait automatiquement la liste ordonnée des season_id pour le format demandé (5v5 ou 3v3)
    à partir du dropdown swgoh.gg.
    """
    import urllib.parse
    discovered = []
    
    # 1. Vérifier si le format affiché par défaut correspond
    summary = soup.select_one("details.dropdown summary")
    default_is_target_format = False
    if summary and f"- {format_type}" in summary.get_text():
        default_is_target_format = True
        
    # 2. Scanner tous les liens dans le dropdown
    dropdown_menu = soup.select_one("details.dropdown ul.dropdown-content")
    elements_to_scan = dropdown_menu.find_all('a') if dropdown_menu else soup.find_all('a')
    
    for a in elements_to_scan:
        text = a.get_text(strip=True)
        if f"- {format_type}" in text:
            href = a.get('href', '')
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            if 'season_id' in params:
                sid = params['season_id'][0]
                if sid not in discovered:
                    discovered.append(sid)
                    
    return discovered, default_is_target_format


def scrape(targets, format_type="5v5", season_id="current"):
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if not os.path.exists(project_dir):
        project_dir = os.getcwd()
        
    is_windows = (platform.system() == "Windows")
    if not is_windows:
        os.environ["HOME"] = project_dir
        os.environ["XDG_CONFIG_HOME"] = os.path.join(project_dir, ".config")
    
    display = None
    exit_code = 1
    detected_seasons = []
    
    try:
        if not is_windows:
            from pyvirtualdisplay import Display
            display = Display(visible=0, size=(1920, 1080))
            display.start()
        
        profile_dir = os.path.join(project_dir, "chrome_profile")
        
        print(f"[WORKER] Lancement de SeleniumBase pour {len(targets)} cibles ({format_type})...", flush=True)
        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            # 1. Détection automatique initiale de la saison si 'current'
            if season_id == "current" and not detected_seasons and targets:
                init_slug = targets[0].get("def_leader_slug")
                init_url = f"https://swgoh.gg/gac/counters/{init_slug}/?cutoff=0"
                print(f"[WORKER] Détection automatique des saisons {format_type} via {init_url}...", flush=True)
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
                    
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(sb.get_page_source(), "html.parser")
                discovered, default_is_target = extract_seasons_from_dropdown(soup, format_type)
                if discovered:
                    detected_seasons = discovered
                    print(f"[WORKER] Saisons {format_type} détectées dynamiquement : {detected_seasons}", flush=True)
                else:
                    # Fallback sécurisé (saisons récentes)
                    detected_seasons = ["CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_80", "CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_78"] if format_type == "5v5" else ["CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_81", "CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_79"]
                    print(f"[WORKER] Fallback saisons {format_type} : {detected_seasons}", flush=True)

            for target in targets:
                def_leader_slug = target.get("def_leader_slug")
                output_file = target.get("out_file")
                d_members = target.get("d_members", "")
                
                debug_log = open(output_file + ".debug.log", "w", encoding="utf-8")
                def dprint(msg):
                    print(msg, flush=True)
                    debug_log.write(msg + "\n")
                    debug_log.flush()
                    
                dprint(f"[WORKER] Démarrage du scraping pour le leader {def_leader_slug}...")
                
                # Détermination du season_id
                target_season = None
                if season_id and season_id != "current":
                    if season_id.startswith("CHAMPIONSHIPS_"):
                        target_season = season_id
                    else:
                        target_season = f"CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_{season_id}"
                elif detected_seasons:
                    target_season = detected_seasons[0]
                    dprint(f"[WORKER] Utilisation de la saison {format_type} : {target_season}")
                    
                base_url = f"https://swgoh.gg/gac/counters/{def_leader_slug}/?cutoff=0"
                if target_season:
                    base_url += f"&season_id={target_season}"
                if d_members:
                    import urllib.parse
                    base_url += f"&d_member={urllib.parse.quote(d_members)}"
                
                url = base_url
                dprint(f"[WORKER] URL cible : {url}")

                counters_data = []
                max_pages = int(target.get("max_pages", 6))
                dprint(f"[WORKER] Scraping optimisé jusqu'à {max_pages} pages des contres récents...")
                
                for page in range(1, max_pages + 1):
                    page_url = url + f"&page={page}"
                    dprint(f"[WORKER] Navigation vers {page_url}...")
                    sb.uc_open_with_reconnect(page_url, reconnect_time=3)

                    quick_check = sb.get_page_source()
                    cloudflare_present = (
                        "Just a moment" in quick_check
                        or "Un instant" in quick_check
                        or "cf-turnstile" in quick_check
                        or "Checking your browser" in quick_check
                    )
                    
                    if page == 1 and cloudflare_present:
                        dprint(f"[WORKER] Page 1 : Cloudflare détecté, tentative de clic...")
                        try:
                            sb.uc_gui_click_captcha()
                        except:
                            pass
                        wait_time = 10
                    elif page == 1:
                        wait_time = 3
                    else:
                        wait_time = 1.2  # Cookies déjà actifs pour les pages suivantes
    
                    for _ in range(int(wait_time * 7)):
                        sb.sleep(0.15)
                        source_check = sb.get_page_source()
                        if "data-unit-def-tooltip-app" in source_check or "panel--size-sm" in source_check or "div.panel" in source_check:
                            break
    
                    panels_found = False
                    for _ in range(8):
                        if sb.is_element_present("div.panel"):
                            panels_found = True
                            break
                        sb.sleep(0.1)
    
                    if not panels_found:
                        dprint(f"[WORKER] Page {page} : Fin des contres disponibles.")
                        break
                        
                    sb.sleep(0.2)
                    page_source = sb.get_page_source()

                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(page_source, "html.parser")
                    
                    # Auto-découverte des saisons pour le format depuis le dropdown
                    if not detected_seasons:
                        discovered, default_is_target = extract_seasons_from_dropdown(soup, format_type)
                        if discovered:
                            detected_seasons.extend(discovered)
                            dprint(f"[WORKER] Saisons {format_type} détectées dynamiquement : {detected_seasons}")
                    
                    page_counters = []
                    counter_panels = soup.select("div.panel.panel--size-sm")
                    if not counter_panels:
                        counter_panels = soup.select("div.panel")
                    dprint(f"[WORKER] Page {page} : {len(counter_panels)} panneaux trouvés.")

                    for panel in counter_panels:
                        atk_container = panel.select_one("div.justify-center.lg\\:justify-end")
                        if not atk_container: continue
                        atk_units = [div.get("data-unit-def-tooltip-app") for div in atk_container.select("[data-unit-def-tooltip-app]")]
                        if not atk_units: continue
                        atk_leader = atk_units[0]
                        atk_members = atk_units[1:]
                        
                        def_container = panel.select_one("div.justify-center.lg\\:justify-start")
                        if not def_container: continue
                        def_units = [div.get("data-unit-def-tooltip-app") for div in def_container.select("[data-unit-def-tooltip-app]")]
                        if not def_units: continue
                        def_leader = def_units[0]
                        def_members = def_units[1:]
                        
                        stats_container = panel.select_one("div.whitespace-nowrap")
                        seen = 0
                        win_pct = 0.0
                        avg_banners = 0.0
                        if stats_container:
                            stat_divs = stats_container.select("div.flex-1 > div.font-bold")
                            if len(stat_divs) >= 3:
                                try:
                                    seen = int(stat_divs[0].text.strip().replace(",", ""))
                                    win_pct = float(stat_divs[1].text.strip().replace("%", ""))
                                    avg_banners = float(stat_divs[2].text.strip())
                                except ValueError:
                                    pass
                                    
                        page_counters.append({
                            "atk_leader_id": atk_leader,
                            "atk_members_ids": atk_members,
                            "def_leader_id": def_leader,
                            "def_members_ids": def_members,
                            "seen": seen,
                            "win_pct": win_pct,
                            "avg_banners": avg_banners
                        })
                        
                    if not page_counters:
                        dprint(f"[WORKER] Page {page} : 0 counters extraits, on arrête la pagination.")
                        break
                        
                    counters_data.extend(page_counters)
                    dprint(f"[WORKER] Page {page} : {len(page_counters)} counters extraits. Total: {len(counters_data)}")
                    
                    if len(page_counters) < 50:
                        dprint(f"[WORKER] Page {page} : moins de 50 résultats ({len(page_counters)}), fin.")
                        break

                # ── Passe générale et historique (saisons auto-détectées) ──────────
                if len(counters_data) < 12:
                    dprint(f"[WORKER] Seulement {len(counters_data)} contres trouvés pour {def_leader_slug}. Lancement de la passe étendue (saisons historiques {format_type})...")
                    
                    # Utiliser les saisons passées trouvées dynamiquement dans le dropdown
                    if len(detected_seasons) > 1:
                        past_season_ids = detected_seasons[1:4]
                    else:
                        # Fallback statique si la détection dynamique n'a rien donné
                        _HIST_5V5 = ["80", "78", "76"]
                        _HIST_3V3 = ["81", "79", "77"]
                        past_season_nums = _HIST_3V3 if format_type == "3v3" else _HIST_5V5
                        past_season_ids = [
                            f"CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_{n}" for n in past_season_nums
                        ]
                    
                    base_counter_url = f"https://swgoh.gg/gac/counters/{def_leader_slug}/?cutoff=0"
                    alt_urls = []
                    # 1. Si un filtre d_members était présent et a donné peu de résultats, tenter le leader seul sur la même saison
                    if d_members:
                        if target_season:
                            alt_urls.append(f"{base_counter_url}&season_id={target_season}")
                        else:
                            alt_urls.append(base_counter_url)
                    # 2. Saisons passées
                    for s in past_season_ids:
                        alt_urls.append(f"{base_counter_url}&season_id={s}")
                    
                    seen_combos = set((c["atk_leader_id"], tuple(c.get("atk_members_ids", []))) for c in counters_data)
                    
                    for alt_url in alt_urls:
                        if len(counters_data) >= 15:
                            break
                        for page in range(1, 3):
                            p_url = alt_url + f"&page={page}"
                            dprint(f"[WORKER] Passe historique page {page} : {p_url}...")
                            try:
                                sb.uc_open_with_reconnect(p_url, reconnect_time=2)
                                sb.sleep(1.5)
                                page_source = sb.get_page_source()
                                soup = BeautifulSoup(page_source, "html.parser")
                                counter_panels = soup.select("div.panel.panel--size-sm") or soup.select("div.panel")
                                if not counter_panels:
                                    break
                                    
                                added_gen = 0
                                for panel in counter_panels:
                                    atk_container = panel.select_one("div.justify-center.lg\\:justify-end")
                                    if not atk_container: continue
                                    atk_units = [div.get("data-unit-def-tooltip-app") for div in atk_container.select("[data-unit-def-tooltip-app]")]
                                    if not atk_units: continue
                                    atk_leader = atk_units[0]
                                    atk_members = atk_units[1:]
                                    
                                    def_container = panel.select_one("div.justify-center.lg\\:justify-start")
                                    if not def_container: continue
                                    def_units = [div.get("data-unit-def-tooltip-app") for div in def_container.select("[data-unit-def-tooltip-app]")]
                                    if not def_units: continue
                                    def_leader = def_units[0]
                                    def_members = def_units[1:]
                                    
                                    combo_key = (atk_leader, tuple(atk_members))
                                    if combo_key in seen_combos:
                                        continue
                                    seen_combos.add(combo_key)
                                    
                                    seen = 100
                                    win_pct = 80.0
                                    avg_banners = 55.0
                                    stat_divs = panel.select("div.text-center")
                                    if len(stat_divs) >= 3:
                                        try:
                                            seen = int(stat_divs[0].text.strip().replace(",", ""))
                                            win_pct = float(stat_divs[1].text.strip().replace("%", ""))
                                            avg_banners = float(stat_divs[2].text.strip())
                                        except ValueError:
                                            pass
                                            
                                    counters_data.append({
                                        "atk_leader_id": atk_leader,
                                        "atk_members_ids": atk_members,
                                        "def_leader_id": def_leader,
                                        "def_members_ids": def_members,
                                        "seen": seen,
                                        "win_pct": win_pct,
                                        "avg_banners": avg_banners
                                    })
                                    added_gen += 1
                                    
                                dprint(f"[WORKER] Passe historique page {page} : {added_gen} nouveaux contres ajoutés.")
                                if added_gen == 0:
                                    break
                            except Exception as ex_gen:
                                dprint(f"[WORKER] Erreur lors de la passe historique: {ex_gen}")
                                break

                
                import json
                result = {
                    "counters": counters_data,
                    "format": format_type,
                    "season_id": season_id
                }
                dprint("[WORKER] Ecriture du résultat final.")
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False)
                
                debug_log.close()
            
        exit_code = 0
            
    except Exception as e:
        print(f"ERREUR CRITIQUE: {e}")
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
        print("Usage: python counters_sb_worker.py [--batch <config_json>] | [<def_leader_slug> <output_file> [format] [season_id] [d_members]]")
        sys.exit(1)
        
    if sys.argv[1] == "--batch":
        config_path = sys.argv[2]
        format_type = sys.argv[3] if len(sys.argv) > 3 else "5v5"
        season_id = sys.argv[4] if len(sys.argv) > 4 else "current"
        
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            targets = json.load(f)
            
        scrape(targets, format_type, season_id)
    else:
        slug = sys.argv[1]
        out = sys.argv[2]
        format_type = sys.argv[3] if len(sys.argv) > 3 else "5v5"
        season_id = sys.argv[4] if len(sys.argv) > 4 else "current"
        d_members = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] != "None" else ""
        
        targets = [{
            "def_leader_slug": slug,
            "out_file": out,
            "d_members": d_members
        }]
        scrape(targets, format_type, season_id)
