from seleniumbase import SB

def main():
    print("🚀 Démarrage de l'arme lourde : SeleniumBase UC Mode")
    
    # On lance SeleniumBase en mode UC (Undetected Chromedriver)
    # Sur un serveur CLI, on DOIT utiliser xvfb=True pour simuler un écran physique
    # et headless=False pour que Chrome ne passe pas en mode "robot d'arrière-plan"
    with SB(uc=True, xvfb=True, headless=False) as sb:
        target_url = "https://swgoh.gg/p/266539582/gac-history/"
        print(f"1. Navigation vers {target_url}")
        
        # Le mode UC utilise une technique de déconnexion/reconnexion pour purger les variables d'automatisation
        try:
            sb.uc_open_with_reconnect(target_url, reconnect_time=4)
        except Exception as e:
            print(f"Erreur de navigation : {e}")
        
        print("2. Recherche et résolution de Cloudflare Turnstile...")
        # SeleniumBase intègre une IA native conçue spécifiquement pour Turnstile et ReCaptcha
        try:
            sb.uc_gui_click_captcha()
            print("✅ Fonction de contournement Cloudflare exécutée !")
        except Exception as e:
            print(f"⚠️ Erreur ou widget introuvable : {e}")
            
        print("3. Attente de 10 secondes pour le verdict...")
        sb.sleep(10)
        
        # Capture d'écran
        sb.save_screenshot("selenium_result.png")
        print("📸 Résultat sauvegardé dans 'selenium_result.png'")
        
        # Analyse finale
        page_source = sb.get_page_source()
        if "GAC History" in page_source:
            print("\n🏆 VICTOIRE TOTALE ! Cloudflare a été vaincu, on a les données !")
        else:
            print("\n❌ Défaite. Cloudflare a tenu bon. L'architecture de notre bot est définitivement sauvée !")

if __name__ == "__main__":
    main()
