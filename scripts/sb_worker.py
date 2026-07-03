import sys
import os
import time
from pyvirtualdisplay import Display
from seleniumbase import SB

# Force Python à afficher les logs instantanément sans attendre la fin du script
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

def scrape(target_url, ally_code):
    print(f"[WORKER] Démarrage du scraping pour {target_url}...")
    # FORCER le dossier HOME vers le dossier du bot (qui est 100% accessible en écriture)
    # Souvent les utilisateurs systemd (botswgoh) n'ont pas de vrai /home/botswgoh physique
    project_dir = "/opt/bot-swgoh"
    os.environ["HOME"] = project_dir
    os.environ["XDG_CONFIG_HOME"] = os.path.join(project_dir, ".config")
    
    print(f"[DEBUG] Utilisateur : {os.environ.get('USER', 'Inconnu')}")
    print(f"[DEBUG] Dossier HOME forcé : {os.environ.get('HOME', 'Inconnu')}")
    
    try:
        print("[WORKER] Démarrage manuel de l'écran virtuel (Xvfb)...")
        display = Display(visible=0, size=(1920, 1080))
        display.start()
        print("[WORKER] Écran virtuel Xvfb démarré avec succès !")
        
        # On définit un profil Chrome spécifique à l'intérieur du projet pour éviter
        # que Chrome n'essaie d'écrire dans /home/botswgoh qui n'existe peut-être pas
        profile_dir = os.path.join(project_dir, "chrome_profile")
        
        print(f"[WORKER] Lancement de SeleniumBase (Profil: {profile_dir})...")
        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            print("[WORKER] Navigateur démarré. Chargement de la page avec Reconnect...")
            sb.uc_open_with_reconnect(target_url, reconnect_time=4)
            
            try:
                print("[WORKER] Tentative de clic sur le captcha Turnstile...")
                sb.uc_gui_click_captcha()
                print("[WORKER] Clic sur le Captcha effectué !")
            except Exception as e:
                print(f"[WORKER] Captcha non trouvé ou passé automatiquement : {e}")
            
            print("[WORKER] Attente de 8 secondes pour laisser la page charger...")
            sb.sleep(8)
            
            print("[WORKER] Récupération du code source HTML...")
            page_source = sb.get_page_source()
            
            if "Just a moment" in page_source or "Cloudflare" in page_source:
                print("ECHEC: Toujours bloqué par Cloudflare.")
                sys.exit(1)
            
            safe_name = ally_code.replace("/", "_").replace(":", "")
            with open(f"gac_history_{safe_name}.html", "w", encoding="utf-8") as f:
                f.write(page_source)
                
            print(f"SUCCES: HTML sauvegardé (gac_history_{safe_name}.html)")
            sys.exit(0)
    except Exception as e:
        print(f"ERREUR CRITIQUE: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python sb_worker.py <url> <ally_code>")
        sys.exit(1)
        
    url = sys.argv[1]
    code = sys.argv[2]
    scrape(url, code)
