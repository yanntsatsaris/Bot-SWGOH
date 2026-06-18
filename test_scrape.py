import asyncio
from curl_cffi.requests import AsyncSession

async def main():
    url = "https://swgoh.gg/gac/squads/?season_id=CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_78"
    print(f"Tentative de connexion à swgoh.gg avec l'empreinte de Chrome 110...")
    
    try:
        # On utilise "impersonate" pour imiter parfaitement la signature TLS d'un vrai navigateur
        async with AsyncSession(impersonate="chrome110") as s:
            response = await s.get(url)
            print(f"Code HTTP reçu : {response.status_code}")
            
            if response.status_code == 200:
                # Vérifie si on est tombé sur la page "Just a moment..." de Cloudflare
                if "Just a moment..." in response.text or "Cloudflare" in response.title if hasattr(response, 'title') else "":
                    print("\n❌ Aïe... On a reçu un code 200, mais c'est le défi Cloudflare qui nous bloque au portillon.")
                else:
                    print("\n✅ BINGO ! Contournement réussi. Voici le titre et un extrait du HTML :")
                    print("-" * 50)
                    # Affiche une petite partie pour prouver qu'on a bien la page
                    print(response.text[:800])
                    print("-" * 50)
            else:
                print(f"\n❌ Échec du contournement (Code {response.status_code}).")
    except Exception as e:
        print(f"Erreur technique lors de la requête : {e}")

if __name__ == "__main__":
    # curl_cffi nécessite parfois une politique d'event loop spécifique sur Windows
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())
