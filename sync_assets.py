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
    ASSETS_TO_FETCH.append(f"gear{i}.webp")

# Assets spécifiques avec leur URL exacte (récupérés depuis swgoh.gg)
SPECIFIC_URLS = {
    "tex.charui_zeta.png": "https://assets.swgoh.gg/frontend/assets/tex.skill_zeta_glow-CGUj_-iS.png",
    "tex.charui_omicron.png": "https://assets.swgoh.gg/frontend/assets/omicron-badge-DF6neN1s.png",
    "gear5.webp": "https://assets.swgoh.gg/frontend/assets/character-gear-frame--g5-Bv1rwaFN.webp",
    "gear8.webp": "https://assets.swgoh.gg/frontend/assets/character-gear-frame--g8-CiXvTrKe.webp",
    "gear9.webp": "https://assets.swgoh.gg/frontend/assets/character-gear-frame--g9-CDY2IiEe.webp",
    "gear10.webp": "https://assets.swgoh.gg/frontend/assets/character-gear-frame--g10-CXccoXYw.webp",
    "gear11.webp": "https://assets.swgoh.gg/frontend/assets/character-gear-frame--g11-qGoNykIE.webp",
    "gear12.webp": "https://assets.swgoh.gg/frontend/assets/character-gear-frame--g12-CUyRFt2B.webp",
}

async def download_asset(session: aiohttp.ClientSession, asset_name: str) -> None:
    filepath = ASSETS_DIR / asset_name
    if filepath.exists():
        log.info(f"Déjà présent: {asset_name}")
        return

    # Si on a une URL exacte pour cet asset, on l'utilise en priorité
    if asset_name in SPECIFIC_URLS:
        urls_to_try = [SPECIFIC_URLS[asset_name]]
    else:
        # Sinon on tente les URLs génériques en reconstituant le nom d'origine
        original_name = asset_name
        if asset_name.startswith("gear"):
            num = asset_name.replace("gear", "").replace(".webp", "")
            original_name = f"character-gear-frame--g{num}.webp"
            
        urls_to_try = [
            f"{BASE_URL}/textures/{original_name}",
            f"{BASE_URL}/{original_name}",
            f"{ALT_URL}/{original_name}"
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

async def download_alignments(session: aiohttp.ClientSession) -> None:
    filepath = Path("data/unit_alignments.json")
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    url = "https://swgoh.gg/api/characters/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                alignments = {char["base_id"]: char["alignment"] for char in data}
                import json
                filepath.write_text(json.dumps(alignments, indent=4), encoding="utf-8")
                log.info("✅ Fichier data/unit_alignments.json généré avec succès.")
            else:
                log.error(f"❌ Erreur {resp.status} lors de la récupération des alignements.")
    except Exception as e:
        log.error(f"❌ Exception lors de la récupération des alignements: {e}")

async def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    
    async with aiohttp.ClientSession() as session:
        # Téléchargement des alignements
        await download_alignments(session)
        
        # Téléchargement des assets
        tasks = [download_asset(session, asset) for asset in ASSETS_TO_FETCH]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())
