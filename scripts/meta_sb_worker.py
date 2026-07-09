import sys
import os
import platform
import time

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

if __name__ == "__main__":
    if len(sys.argv) >= 5:
        print(f"[WORKER] Lancement du script meta pour {sys.argv[1]} ({sys.argv[3]} - {sys.argv[4]})...", flush=True)

from pyvirtualdisplay import Display
from seleniumbase import SB

def scrape(target_url, output_file, format_type, mode):
    print(f"[WORKER] Démarrage de la fonction scrape...")
    
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
        
        print(f"[WORKER] Lancement de SeleniumBase...")
        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            print("[WORKER] Navigateur démarré. Chargement de la page...")
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
                
            # Attente active du chargement initial du tableau
            for _ in range(20):
                if sb.is_element_visible("table"):
                    break
                sb.sleep(0.5)

            print(f"[WORKER] Interaction avec l'UI pour {format_type} et {mode}...")
            
            # Le site n'est PAS une SPA, ce sont des liens <a> normaux !
            # 1. Obtenir l'URL de la bonne saison
            print(f"[WORKER] Recherche de la saison pour le format {format_type}...")
            
            # On ouvre le menu déroulant
            trigger = sb.find_element("*:contains('Season:')")
            if trigger:
                trigger.click()
                sb.sleep(1)
            
            # On cherche le lien <a> qui correspond à la saison
            season_link = sb.find_element(f"a:contains('- {format_type}')")
            season_href = season_link.get_attribute("href")
            print(f"[WORKER] URL de saison trouvée : {season_href}")
            
            # 2. Ajouter le paramètre perspective si on est en attaque
            final_url = season_href
            if mode.lower() == "attack":
                if "?" in final_url:
                    final_url += "&perspective=attack"
                else:
                    final_url += "?perspective=attack"
                    
            print(f"[WORKER] Navigation vers l'URL finale : {final_url}")
            # On navigue vers la nouvelle page (qui va recharger entièrement)
            sb.uc_open_with_reconnect(final_url, reconnect_time=4)
            
            # Attente active du chargement du tableau sur la nouvelle page
            for _ in range(20):
                if sb.is_element_visible("table.stat-table"):
                    break
                sb.sleep(0.5)
                
            sb.sleep(2) # Petit buffer
            
            print("[WORKER] Récupération du code source final HTML...")
            page_source = sb.get_page_source()
            
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(page_source)
                
            print(f"SUCCES: HTML sauvegardé dans {output_file}")
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
    if len(sys.argv) < 5:
        print("Usage: python meta_sb_worker.py <url> <output_file> <format_type> <mode>")
        sys.exit(1)
        
    url = sys.argv[1]
    out = sys.argv[2]
    fmt = sys.argv[3]
    md = sys.argv[4]
    scrape(url, out, fmt, md)
