import sys
import os

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

if __name__ == "__main__":
    if len(sys.argv) >= 3:
        print(f"[WORKER] Lancement du script pour {sys.argv[1]}...", flush=True)

import time
import platform
from pyvirtualdisplay import Display
from seleniumbase import SB

def scrape(target_url, ally_code):
    print(f"[WORKER] Démarrage de la fonction scrape pour {target_url}...")
    
    # Déterminer le dossier racine du projet
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if not os.path.exists(project_dir):
        project_dir = os.getcwd()
        
    is_windows = (platform.system() == "Windows")
    if not is_windows:
        os.environ["HOME"] = project_dir
        os.environ["XDG_CONFIG_HOME"] = os.path.join(project_dir, ".config")
    
    print(f"[DEBUG] Utilisateur : {os.environ.get('USER', 'Inconnu')}")
    print(f"[DEBUG] Dossier HOME : {os.environ.get('HOME', 'Inconnu')}")
    
    display = None
    exit_code = 1
    try:
        if not is_windows:
            print("[WORKER] Démarrage manuel de l'écran virtuel (Xvfb)...")
            display = Display(visible=0, size=(1920, 1080))
            display.start()
            print("[WORKER] Écran virtuel Xvfb démarré avec succès !")
        else:
            print("[WORKER] Environnement Windows détecté, pas d'écran virtuel Xvfb.")
        
        # On définit un profil Chrome spécifique à l'intérieur du projet pour éviter
        # que Chrome n'essaie d'écrire dans /home/botswgoh qui n'existe peut-être pas
        profile_dir = os.path.join(project_dir, "chrome_profile")
        
        print(f"[WORKER] Lancement de SeleniumBase (Profil: {profile_dir})...")
        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            print("[WORKER] Navigateur démarré. Chargement de la page avec Reconnect...")
            sb.uc_open_with_reconnect(target_url, reconnect_time=4)
            
            # Check rapide : est-ce que Cloudflare est présent ?
            quick_check = sb.get_page_source()
            
            cloudflare_present = (
                "Just a moment" in quick_check
                or "cf-turnstile" in quick_check
                or "Checking your browser" in quick_check
            )
            
            if cloudflare_present:
                print("[WORKER] ⚠️ Cloudflare détecté, clic en cours...")
                try:
                    sb.uc_gui_click_captcha()
                    print("[WORKER] ✅ Clic effectué")
                except Exception as e:
                    print(f"[WORKER] Clic échoué : {e}")
                wait_time = 8  # Attente longue après challenge
            else:
                print("[WORKER] ✅ Pas de Cloudflare")
                wait_time = 2  # Attente courte pour rendu JS
            
            # Attente adaptive : poll au lieu de sleep fixe
            print(f"[WORKER] Attente adaptative jusqu'à {wait_time}s pour chargement...")
            for _ in range(wait_time * 2):  # Check toutes les 500ms
                sb.sleep(0.5)
                source = sb.get_page_source()
                # On check soit le bloc stat, soit l'accueil des historiques
                if "gac-counters-battle-summary" in source or "class=\"col-sm-6 col-md-6\"" in source:
                    print("[WORKER] ✅ Contenu GAC détecté, stop de l'attente !")
                    break
            
            print("[WORKER] Récupération du code source HTML...")
            page_source = sb.get_page_source()
            
            if "Just a moment" in page_source or "Cloudflare" in page_source:
                print("ECHEC: Toujours bloqué par Cloudflare.")
                exit_code = 1
                return
            
            safe_name = ally_code.replace("/", "_").replace(":", "")
            with open(f"gac_history_{safe_name}.html", "w", encoding="utf-8") as f:
                f.write(page_source)
                
            print(f"SUCCES: HTML sauvegardé (gac_history_{safe_name}.html)")
            exit_code = 0
    except Exception as e:
        print(f"ERREUR CRITIQUE: {e}")
        exit_code = 1
    finally:
        if display is not None:
            print("[WORKER] Arrêt de l'écran virtuel (Xvfb)...")
            try:
                display.stop()
                print("[WORKER] Écran virtuel Xvfb arrêté.")
            except Exception as e:
                print(f"[WORKER] Erreur lors de l'arrêt de Xvfb : {e}")
        sys.exit(exit_code)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python sb_worker.py <url> <ally_code>")
        sys.exit(1)
        
    url = sys.argv[1]
    code = sys.argv[2]
    scrape(url, code)
