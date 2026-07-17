import os
import asyncio
import aiohttp
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ASSETS_DIR = Path("assets/overlays")
BASE_URL = "https://assets.swgoh.gg/frontend/assets"
ALT_URL = "https://game-assets.swgoh.gg"

ASSETS_TO_FETCH = [
    # Zetas / Omicrons
    "tex.charui_zeta.png", "tex.charui_omicron.png",
]

# Ajout dynamique des gears (0 à 13)
# On utilise la structure de lien fournie par l'utilisateur
for i in range(0, 14):
    ASSETS_TO_FETCH.append(f"character-gear-frame--g{i}.webp")

# Assets spécifiques avec leur URL exacte (récupérés depuis swgoh.gg)
SPECIFIC_URLS = {
    "tex.charui_zeta.png": "https://assets.swgoh.gg/frontend/assets/tex.skill_zeta_glow-CGUj_-iS.png",
    "tex.charui_omicron.png": "https://assets.swgoh.gg/frontend/assets/omicron-badge-DF6neN1s.png"
}

for i in range(0, 14):
    # Ajout des URLs complètes pour les cadres de gear (en supposant le même hash ou s'il est ignoré)
    SPECIFIC_URLS[f"character-gear-frame--g{i}.webp"] = f"https://assets.swgoh.gg/frontend/assets/character-gear-frame--g{i}-qGoNykIE.webp"

async def download_asset(session: aiohttp.ClientSession, asset_name: str) -> None:
    filepath = ASSETS_DIR / asset_name
    if filepath.exists():
        log.info(f"Déjà présent: {asset_name}")
        return

    # Si on a une URL exacte pour cet asset, on l'utilise en priorité
    if asset_name in SPECIFIC_URLS:
        urls_to_try = [SPECIFIC_URLS[asset_name]]
    else:
        # Sinon on tente les URLs génériques
        urls_to_try = [
            f"{BASE_URL}/textures/{asset_name}",
            f"{BASE_URL}/{asset_name}",
            f"{ALT_URL}/{asset_name}"
        ]
    
    for url in urls_to_try:
        log.info(f"Tentative de téléchargement depuis : {url}")
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    filepath.write_bytes(data)
                    log.info(f"✅ Téléchargé: {asset_name} (depuis {url})")
                    return
                else:
                    log.debug(f"Code {resp.status} pour {url}")
        except Exception as e:
            log.debug(f"Erreur pour {url} : {e}")
            
    log.error(f"❌ Impossible de télécharger {asset_name}. URLs testées : {', '.join(urls_to_try)}")

async def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = [download_asset(session, name) for name in ASSETS_TO_FETCH]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
