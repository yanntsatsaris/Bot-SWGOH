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
                
                # URL cible
                url = f"https://swgoh.gg/gac/counters/{def_leader_slug}/?cutoff=0"
                if season_id and season_id != "current":
                    url += f"&season_id={season_id}"
                if d_members:
                    import urllib.parse
                    url += f"&d_member={urllib.parse.quote(d_members)}"
                dprint(f"[WORKER] URL de base : {url}")
                
                counters_data = []
                
                for page in range(1, 11):
                    page_url = url + f"&page={page}"
                    dprint(f"[WORKER] Navigation vers {page_url}...")
                    sb.uc_open_with_reconnect(page_url, reconnect_time=4)
                    
                    quick_check = sb.get_page_source()
                    cloudflare_present = (
                        "Just a moment" in quick_check
                        or "Un instant" in quick_check
                        or "cf-turnstile" in quick_check
                        or "Checking your browser" in quick_check
                    )
                    
                    if cloudflare_present:
                        dprint(f"[WORKER] Page {page} : Cloudflare détecté, tentative de clic...")
                        try:
                            sb.uc_gui_click_captcha()
                        except:
                            pass
                        wait_time = 12
                    else:
                        dprint(f"[WORKER] Page {page} : Pas de Cloudflare.")
                        wait_time = 6
    
                    dprint(f"[WORKER] Page {page} : Attente adaptative ({wait_time}s max)...")
                    for _ in range(wait_time * 2):
                        sb.sleep(0.5)
                        source_check = sb.get_page_source()
                        if "data-unit-def-tooltip-app" in source_check or "panel--size-sm" in source_check:
                            dprint(f"[WORKER] Page {page} : Contenu counter détecté, stop de l'attente !")
                            break
    
                    panels_found = False
                    for _ in range(10):
                        if sb.is_element_present("div.panel"):
                            panels_found = True
                            break
                        sb.sleep(0.5)
    
                    if not panels_found:
                        dprint(f"[WORKER] Page {page} : Aucun panneau de counter trouvé (fin des résultats ou erreur).")
                        dprint(f"[DEBUG HTML snippet]: {quick_check[:500]}")
                        break
                        
                    sb.sleep(2)
                    page_source = sb.get_page_source()
                    
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(page_source, "html.parser")
                    
                    page_counters = []
                    counter_panels = soup.select("div.panel.panel--size-sm")
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
