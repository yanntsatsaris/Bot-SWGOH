import asyncio
import time
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def main():
    print("🚀 Démarrage du test de Scraping Lourd (Playwright + Stealth)")
    start_time = time.time()
    
    # Remplacer cet ally code par le tien pour le test
    target_url = "https://swgoh.gg/p/123456789/gac-history/"
    
    async with async_playwright() as p:
        print("1. Lancement du navigateur Chromium en arrière-plan...")
        # Lancement en mode "headless" (invisible), indispensable sur un serveur Linux sans écran
        browser = await p.chromium.launch(headless=True)
        
        print("2. Création du contexte de navigation...")
        # On simule un utilisateur normal (User-Agent classique de Windows)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        page = await context.new_page()
        
        print("3. Application du camouflage (Stealth) pour tromper Cloudflare...")
        await stealth_async(page)
        
        print(f"4. Navigation vers {target_url} ...")
        # On attend que le réseau soit calme pour s'assurer que les scripts Cloudflare sont chargés
        try:
            await page.goto(target_url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"⚠️ Erreur de chargement de la page : {e}")
            
        print("5. Attente de 10 secondes pour laisser le défi Cloudflare se résoudre...")
        await page.wait_for_timeout(10000)
        
        print("6. Analyse du résultat...")
        title = await page.title()
        content = await page.content()
        
        if "Just a moment" in title or "Cloudflare" in title:
            print("\n❌ ÉCHEC : Cloudflare nous a repérés et bloqués au portillon (Turnstile).")
        elif "Not Found" in title or "404" in title:
            print("\n⚠️ Page introuvable. Remplace '123456789' par un vrai Ally Code dans le script.")
        else:
            print(f"\n✅ SUCCÈS ! Cloudflare a été contourné. Titre de la page : '{title}'")
            # Cherche s'il y a le mot "GAC History" ou similaire
            if "GAC History" in content:
                print("🏆 L'historique GAC a bien été trouvé dans le HTML !")
            else:
                print("🤔 La page a chargé, mais l'historique GAC n'y est pas visible immédiatement.")
        
        await browser.close()
        
        end_time = time.time()
        print(f"\n⏱️ Durée totale de l'opération : {round(end_time - start_time, 2)} secondes.")
        print("Sur un serveur, imagine que cette opération doit être répétée pour 50 joueurs de la guilde, soit environ", round((end_time - start_time) * 50 / 60, 1), "minutes !")

if __name__ == "__main__":
    asyncio.run(main())
