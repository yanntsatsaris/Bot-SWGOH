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
            
            # 1. Sélection du Mode (Attack ou Defense)
            # Fait en premier car ça recharge parfois des éléments
            try:
                target_text = "Attack" if mode.lower() == "attack" else "Defense"
                # Sélecteur qui cherche exactement le texte complet "Attack" ou "Defense"
                # Dans l'UI swgoh.gg, ce sont des boutons groupés
                sb.click(f'button:contains("{target_text}")')
                print(f"[WORKER] Bouton de mode '{target_text}' cliqué.")
            except Exception as e:
                print(f"[WORKER] Avertissement: Impossible de changer le mode: {e}")
                
            sb.sleep(2)
            
            # 2. Sélection de la saison (3v3 ou 5v5)
            # Le dropdown affiche "Season XX - 5v5" par défaut.
            try:
                # Cherche un select
                if sb.is_element_visible("select"):
                    sb.select_option_by_text("select", format_type, "partial")
                    print(f"[WORKER] Option de saison contenant '{format_type}' cliquée (select natif).")
                else:
                    print("[WORKER] Pas de <select> visible, tentative de clic sur menu personnalisé...")
                    # On cherche l'élément qui affiche "Season: " pour ouvrir le menu
                    trigger = sb.find_element("*:contains('Season:')")
                    if trigger:
                        trigger.click()
                        sb.sleep(1) # Attendre l'animation du menu
                        # Cliquer sur la première option contenant "- 3v3" ou "- 5v5"
                        # En CSS: *:contains('- 3v3') trouvera le texte. On prend le premier.
                        sb.click(f"*:contains('- {format_type}')")
                        print(f"[WORKER] Option de saison contenant '{format_type}' cliquée (menu custom).")
            except Exception as e:
                print(f"[WORKER] Avertissement: Impossible de changer la saison (format): {e}")
                
            print("[WORKER] Attente du rafraîchissement JS...")
            sb.sleep(4)
            
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
