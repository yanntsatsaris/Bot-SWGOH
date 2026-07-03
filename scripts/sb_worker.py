import sys
import os
from seleniumbase import SB

def scrape(target_url, ally_code):
    print(f"Démarrage du scraping pour {target_url}...")
    try:
        # On utilise le mode UC avec Xvfb exactement comme dans ton test manuel
        with SB(uc=True, xvfb=True, headless=False) as sb:
            sb.uc_open_with_reconnect(target_url, reconnect_time=4)
            
            try:
                sb.uc_gui_click_captcha()
            except Exception as e:
                print(f"Captcha non trouvé ou passé automatiquement : {e}")
            
            sb.sleep(8)
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
