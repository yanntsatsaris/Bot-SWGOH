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

def scrape(def_leader_slug, output_file, format_type="5v5", season_id="current"):
    print(f"[WORKER] Démarrage du scraping pour le leader {def_leader_slug}...")
    
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
        
        # URL cible : https://swgoh.gg/gac/counters/GU-REY/?cutoff=0
        target_url = f"https://swgoh.gg/gac/counters/{def_leader_slug}/?cutoff=0"
        
        print(f"[WORKER] Lancement de SeleniumBase...")
        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            print(f"[WORKER] Navigation vers {target_url}...")
            sb.uc_open_with_reconnect(target_url, reconnect_time=4)
            
            quick_check = sb.get_page_source()
            cloudflare_present = (
                "Just a moment" in quick_check
                or "cf-turnstile" in quick_check
                or "Checking your browser" in quick_check
            )
            
            if cloudflare_present:
                print("[WORKER] Cloudflare détecté, tentative de clic...")
                try:
                    sb.uc_gui_click_captcha()
                except:
                    pass
                sb.sleep(8)
            else:
                sb.sleep(3)
                
            # Attente active du chargement du tableau
            table_found = False
            for _ in range(20):
                # Cherche une table
                if sb.is_element_visible("table"):
                    table_found = True
                    break
                sb.sleep(0.5)

            if not table_found:
                print("[WORKER] ATTENTION: Aucune table trouvée. Le site a peut-être changé ou c'est une erreur 404.")
            else:
                print("[WORKER] Table de counters trouvée !")
                
            # Petit buffer supplémentaire pour être sûr que tout le JS s'est exécuté
            sb.sleep(2)
            
            # Récupération du code source complet
            page_source = sb.get_page_source()
            
            print(f"[WORKER] Sauvegarde du HTML dans {output_file}...")
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(page_source)
                
            print("[WORKER] Terminé.")
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
        print("Usage: python counters_sb_worker.py <def_leader_slug> <output_file> [format] [season_id]")
        sys.exit(1)
        
    slug = sys.argv[1]
    out = sys.argv[2]
    fmt = sys.argv[3] if len(sys.argv) > 3 else "5v5"
    season = sys.argv[4] if len(sys.argv) > 4 else "current"
    
    scrape(slug, out, fmt, season)
