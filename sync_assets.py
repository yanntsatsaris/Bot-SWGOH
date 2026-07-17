import os
import asyncio
import aiohttp
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

ASSETS_DIR = Path("assets/overlays")
BASE_URL = "https://game-assets.swgoh.gg"
ALT_URL = "https://swgoh.gg/static/img/assets"

ASSETS_TO_FETCH = [
    # Alignements
    "tex.charui_portrait_bg_lightside.png",
    "tex.charui_portrait_bg_darkside.png",
    "tex.charui_portrait_bg_neutral.png",
    # Reliques
    "tex.charui_relic_1.png", "tex.charui_relic_2.png", "tex.charui_relic_3.png",
    "tex.charui_relic_4.png", "tex.charui_relic_5.png", "tex.charui_relic_6.png",
    "tex.charui_relic_7.png", "tex.charui_relic_8.png", "tex.charui_relic_9.png",
    # Etoiles
    "tex.charui_star_character.png", "tex.charui_star_character_empty.png",
    # Zetas / Omicrons
    "tex.charui_zeta.png", "tex.charui_omicron.png",
]

# Ajout dynamique des gears (1 à 12)
for i in range(1, 13):
    # Différentes variantes possibles de noms dans les assets du jeu
    ASSETS_TO_FETCH.append(f"tex.charui_portraithold_gear{i}.png")
    ASSETS_TO_FETCH.append(f"tex.charui_portrait_frame_gear{i}.png")
    ASSETS_TO_FETCH.append(f"tex.charui_gear{i}.png")

async def download_asset(session: aiohttp.ClientSession, asset_name: str) -> None:
    filepath = ASSETS_DIR / asset_name
    if filepath.exists():
        log.info(f"Déjà présent: {asset_name}")
        return

    # Try BASE_URL with and without /textures/
    urls_to_try = [
        f"{BASE_URL}/textures/{asset_name}",
        f"{BASE_URL}/{asset_name}",
        f"{ALT_URL}/{asset_name}"
    ]
    
    for url in urls_to_try:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    filepath.write_bytes(data)
                    log.info(f"✅ Téléchargé: {asset_name} (depuis {url})")
                    return
        except Exception as e:
            pass
            
    log.error(f"❌ Impossible de télécharger {asset_name}")

async def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        tasks = [download_asset(session, name) for name in ASSETS_TO_FETCH]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
