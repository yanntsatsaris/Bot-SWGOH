import cloudscraper

def main():
    url = "https://swgoh.gg/gac/squads/?season_id=CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_78"
    print(f"Tentative de connexion à swgoh.gg avec cloudscraper...")
    
    try:
        # cloudscraper inclut un moteur JS basique pour résoudre les défis Cloudflare
        scraper = cloudscraper.create_scraper(browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        })
        
        response = scraper.get(url)
        print(f"Code HTTP reçu : {response.status_code}")
        
        if response.status_code == 200:
            if "Just a moment..." in response.text or "Cloudflare" in response.text:
                print("\n❌ Code 200, mais bloqué par le défi JavaScript (Turnstile).")
            else:
                print("\n✅ BINGO ! cloudscraper a réussi à passer !")
        else:
            print(f"\n❌ Échec du contournement (Code {response.status_code}).")
    except Exception as e:
        print(f"Erreur technique : {e}")

if __name__ == "__main__":
    main()
