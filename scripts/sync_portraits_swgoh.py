import asyncio
import os
import sys
import aiohttp
from bs4 import BeautifulSoup
from pathlib import Path
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DATABASE_PATH

# Configuration des dossiers
ASSETS_DIR = Path("assets")
PORTRAITS_DIR = ASSETS_DIR / "portraits"
SHIPS_DIR = ASSETS_DIR / "vaisseaux"

PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
SHIPS_DIR.mkdir(parents=True, exist_ok=True)

async def fetch_page(session, url):
    print(f"🌍 Téléchargement de {url}...")
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()

async def download_image(session, img_url, dest_path):
    if dest_path.exists():
        return True # Déjà téléchargé
        
    try:
        async with session.get(img_url) as response:
            if response.status == 200:
                content = await response.read()
                with open(dest_path, "wb") as f:
                    f.write(content)
                return True
            else:
                print(f"⚠️ Erreur {response.status} pour l'image {img_url}")
                return False
    except Exception as e:
        print(f"❌ Erreur réseau pour {img_url}: {e}")
        return False

async def process_swgoh_gg():
    print("🚀 Début du scraping SWGOH.GG...")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # On crée la table si elle n'existe pas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_characters (
            base_id TEXT PRIMARY KEY,
            name TEXT,
            type INTEGER,
            thumbnail_name TEXT,
            image_path TEXT,
            is_image_valid INTEGER DEFAULT 0
        )
    """)
    conn.commit()

    async with aiohttp.ClientSession() as session:
        # 1. Personnages
        html = await fetch_page(session, "https://swgoh.gg/characters/")
        soup = BeautifulSoup(html, "html.parser")
        
        # Structure swgoh.gg: <li class="media list-group-item p-0 character">
        chars = soup.find_all("li", class_="character")
        if not chars:
            # Fallback ancienne structure
            chars = soup.find_all("div", class_="collection-char")
            
        print(f"👥 {len(chars)} personnages trouvés sur la page.")
        
        for char in chars:
            img_tag = char.find("img", class_="character-portrait__img")
            if not img_tag:
                continue
                
            img_url = img_tag.get("src")
            name = img_tag.get("alt", "")
            
            # Extract base_id from link
            link_tag = char.find("a")
            if not link_tag:
                continue
                
            href = link_tag.get("href", "")
            # /characters/darth-vader/ -> DARTHVADER
            parts = [p for p in href.split("/") if p]
            if len(parts) >= 2:
                slug = parts[1]
                # Approximation of Base ID (this might not be 100% accurate for weird names, but good enough as fallback)
                # The exact base_id is best fetched from Comlink. But here we just want to save the image.
                # Actually, SWGOH.GG stores the exact base_id in data attributes usually.
                # Let's check parent attributes.
            
            # Since we want to update existing characters:
            # We can find the character by matching the name or the image URL filename.
            filename = img_url.split("/")[-1] # tex.charui_vader.png
            thumbnail_name = filename.replace(".png", "")
            
            dest_path = PORTRAITS_DIR / filename
            success = await download_image(session, img_url, dest_path)
            
            if success:
                # Update DB using thumbnail_name which matches Comlink exactly!
                cursor.execute("""
                    UPDATE game_characters 
                    SET image_path = ?, is_image_valid = 1 
                    WHERE thumbnail_name = ?
                """, (str(dest_path.as_posix()), thumbnail_name))
        
        conn.commit()
        
        # 2. Vaisseaux
        html = await fetch_page(session, "https://swgoh.gg/ships/")
        soup = BeautifulSoup(html, "html.parser")
        
        ships = soup.find_all("li", class_="ship")
        if not ships:
            ships = soup.find_all("div", class_="collection-ship")
            
        print(f"✈️ {len(ships)} vaisseaux trouvés sur la page.")
        
        for ship in ships:
            img_tag = ship.find("img", class_="ship-portrait__img")
            if not img_tag:
                continue
                
            img_url = img_tag.get("src")
            filename = img_url.split("/")[-1]
            thumbnail_name = filename.replace(".png", "")
            
            dest_path = SHIPS_DIR / filename
            success = await download_image(session, img_url, dest_path)
            
            if success:
                cursor.execute("""
                    UPDATE game_characters 
                    SET image_path = ?, is_image_valid = 1 
                    WHERE thumbnail_name = ?
                """, (str(dest_path.as_posix()), thumbnail_name))
                
        conn.commit()
        conn.close()
        
        print("✅ Scraping et mise à jour terminés !")

if __name__ == "__main__":
    asyncio.run(process_swgoh_gg())
