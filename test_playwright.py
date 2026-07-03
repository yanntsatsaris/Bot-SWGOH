import asyncio
import time
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

async def main():
    print("🚀 Démarrage du test de Scraping Lourd (Playwright + Stealth V2)")
    start_time = time.time()
    target_url = "https://swgoh.gg/p/266539582/gac-history/"

    try:
        print("1. Initialisation de Playwright avec le mode Stealth activé globalement...")
        # C'est la méthode recommandée par la doc que tu m'as envoyée
        async with Stealth().use_async(async_playwright()) as p:
            
            print("2. Lancement du navigateur Chromium (headless)...")
            browser = await p.chromium.launch(headless=True)
            
            print("3. Création de la page camouflée...")
            # Le camouflage s'applique automatiquement sur les pages créées ici
            page = await browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            
            print(f"4. Navigation vers {target_url} ...")
            try:
                # Cloudflare maintient des connexions réseau actives, 'networkidle' provoque donc un timeout.
                # On utilise 'domcontentloaded' pour passer à la suite dès que le HTML de base est là.
                await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                print(f"⚠️ Erreur ou Timeout lors du chargement : {e}")

            print("5. Recherche de la case à cocher Cloudflare...")
            print("5. Tentative de clic à l'aveugle (Coordonnées exactes d'après ton image)...")
            try:
                # J'ai analysé ton image : le contenu n'est pas centré au milieu, 
                # il est dans une colonne qui commence environ à un quart de l'écran (X ~ 520).
                # La case est située sous le texte, environ à un tiers de la hauteur (Y ~ 330).
                x, y = 520, 330
                
                print(f"🎯 Mouvement de souris humain simulé vers la case (X={x}, Y={y})...")
                await page.mouse.move(x, y, steps=35)
                await page.wait_for_timeout(800) # Petite pause "humaine"
                
                print("🖱️ Clic !")
                await page.mouse.click(x, y, delay=150)
                
                # On attend 2 petites secondes et on prend tout de suite une photo pour voir si la case a réagi !
                await page.wait_for_timeout(2000)
                await page.screenshot(path="cloudflare_after_click.png", full_page=True)
                print("📸 Capture d'écran juste après le clic sauvegardée sous 'cloudflare_after_click.png'")
                
            except Exception as e:
                print(f"⚠️ Le clic a échoué : {e}")

            print("6. Attente de 15 secondes pour laisser l'IA Cloudflare analyser notre clic...")
            await page.wait_for_timeout(15000)
            
            print("7. Analyse du résultat...")
            title = await page.title()
            content = await page.content()

            if "Just a moment" in title or "Cloudflare" in title:
                print("\n❌ ÉCHEC : Cloudflare nous a repérés et bloqués au portillon (Turnstile).")
                
                # Sauvegarde du HTML pour inspection
                with open("cloudflare_block.html", "w", encoding="utf-8") as f:
                    f.write(content)
                print("💾 Le code HTML complet a été sauvegardé dans 'cloudflare_block.html'")
                
                # Sauvegarde d'une capture d'écran (très utile pour voir à quoi ressemble le blocage)
                await page.screenshot(path="cloudflare_block.png", full_page=True)
                print("📸 Une capture d'écran a été sauvegardée sous 'cloudflare_block.png'")
                
            elif "Not Found" in title or "404" in title:
                print("\n⚠️ Page introuvable.")
            else:
                print(f"\n✅ SUCCÈS ! Cloudflare a été contourné. Titre de la page : '{title}'")
                if "GAC History" in content:
                    print("🏆 L'historique GAC a bien été trouvé dans le HTML !")
                else:
                    print("🤔 La page a chargé, mais l'historique GAC n'est pas visible.")

            await browser.close()
            
    except Exception as e:
        print(f"\n❌ Erreur technique critique : {e}")

    end_time = time.time()
    print(f"\n⏱️ Durée totale de l'opération : {round(end_time - start_time, 2)} secondes.")

if __name__ == "__main__":
    asyncio.run(main())
