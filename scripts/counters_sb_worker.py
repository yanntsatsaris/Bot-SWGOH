import sys
import os
import platform

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        print(f"[WORKER] Lancement du script counters pour {sys.argv[1]}...", flush=True)

from pyvirtualdisplay import Display
from seleniumbase import SB

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
    try:
        if not is_windows:
            display = Display(visible=0, size=(1920, 1080))
            display.start()
        
        profile_dir = os.path.join(project_dir, "chrome_profile")
        
        print(f"[WORKER] Lancement de SeleniumBase pour {len(targets)} cibles...", flush=True)
        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            for target in targets:
                def_leader_slug = target.get("def_leader_slug")
                output_file = target.get("out_file")
                d_members = target.get("d_members", "")
                
                debug_log = open(output_file + ".debug.log", "w", encoding="utf-8")
                def dprint(msg):
                    print(msg, flush=True)
                    debug_log.write(msg + "\n")
                    debug_log.flush()
                    
                dprint(f"[WORKER] Démarrage du scraping pour le leader {def_leader_slug} (membres: {d_members})...")
                
                # URL cible avec format explicite (3v3 ou 5v5)
                url = f"https://swgoh.gg/gac/counters/{def_leader_slug}/?cutoff=0&gac_f={format_type}&format={format_type}"
                if season_id and season_id != "current":
                    url += f"&season_id={season_id}"
                if d_members:
                    import urllib.parse
                    url += f"&d_member={urllib.parse.quote(d_members)}"
                dprint(f"[WORKER] URL de base : {url}")

                
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
                        wait_time = 4
                    else:
                        wait_time = 2  # Cookies déjà actifs pour les pages suivantes
    
                    for _ in range(int(wait_time * 5)):
                        sb.sleep(0.2)
                        source_check = sb.get_page_source()
                        if "data-unit-def-tooltip-app" in source_check or "panel--size-sm" in source_check:
                            break
    
                    panels_found = False
                    for _ in range(5):
                        if sb.is_element_present("div.panel"):
                            panels_found = True
                            break
                        sb.sleep(0.2)
    
                    if not panels_found:
                        dprint(f"[WORKER] Page {page} : Fin des contres disponibles.")
                        break
                        
                    sb.sleep(0.5)
                    page_source = sb.get_page_source()

                    
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(page_source, "html.parser")
                    
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

                # ── Passe générale de fallback si d_members donne peu de contres (< 8) ──────
                if d_members and len(counters_data) < 8:
                    dprint(f"[WORKER] Seulement {len(counters_data)} contres spécifiques pour {def_leader_slug} (membres: {d_members}). Lancement de la passe générale...")
                    general_url = f"https://swgoh.gg/gac/counters/{def_leader_slug}/?cutoff=0&gac_f={format_type}&format={format_type}"
                    if season_id and season_id != "current":
                        general_url += f"&season_id={season_id}"
                    
                    seen_combos = set((c["atk_leader_id"], tuple(c.get("atk_members_ids", []))) for c in counters_data)
                    
                    for page in range(1, 3):
                        p_url = general_url + f"&page={page}"
                        dprint(f"[WORKER] Passe générale page {page} : {p_url}...")
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
                                
                            dprint(f"[WORKER] Passe générale page {page} : {added_gen} nouveaux contres ajoutés.")
                            if added_gen == 0:
                                break
                        except Exception as ex_gen:
                            dprint(f"[WORKER] Erreur lors de la passe générale: {ex_gen}")
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
