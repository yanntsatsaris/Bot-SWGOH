import asyncio
import os
import sys
import aiohttp
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

async def fetch_json(session: aiohttp.ClientSession, url: str):
    print(f"🌍 Téléchargement API : {url}...")
    async with session.get(url, headers=HEADERS) as response:
        response.raise_for_status()
        return await response.json()

async def download_image(session: aiohttp.ClientSession, img_url: str, dest_path: Path) -> bool:
    if dest_path.exists():
        return True
        
    try:
        async with session.get(img_url, headers=HEADERS) as response:
            if response.status == 200:
                content = await response.read()
                dest_path.write_bytes(content)
                return True
            else:
                print(f"⚠️ Erreur {response.status} pour l'image {img_url}")
                return False
    except Exception as e:
        print(f"❌ Erreur réseau pour {img_url}: {e}")
        return False

async def process_swgoh_gg():
    print("🚀 Début de la synchro des personnages via l'API SWGOH.GG...")
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
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

    downloaded_list = []
    chars = []
    ships = []

    async with aiohttp.ClientSession() as session:
        # 1. Personnages
        try:
            chars = await fetch_json(session, "https://swgoh.gg/api/characters/")
            print(f"👥 {len(chars)} personnages récupérés depuis l'API.")
            
            for item in chars:
                base_id = item.get("base_id", "").upper()
                name = item.get("name", "")
                img_url = item.get("image", "")
                
                if not base_id or not img_url:
                    continue
                    
                filename = img_url.split("/")[-1]
                thumbnail_name = filename.replace(".png", "")
                dest_path = PORTRAITS_DIR / filename
                
                is_new = not dest_path.exists()
                success = await download_image(session, img_url, dest_path)
                
                if success:
                    if is_new:
                        downloaded_list.append(name)
                    cursor.execute("""
                        INSERT INTO game_characters (base_id, name, type, thumbnail_name, image_path, is_image_valid)
                        VALUES (?, ?, 1, ?, ?, 1)
                        ON CONFLICT(base_id) DO UPDATE SET
                            name = excluded.name,
                            thumbnail_name = excluded.thumbnail_name,
                            image_path = excluded.image_path,
                            is_image_valid = 1
                    """, (base_id, name, thumbnail_name, str(dest_path.as_posix())))
            conn.commit()
        except Exception as e:
            print(f"❌ Erreur API Personnages : {e}")

        # 2. Vaisseaux
        try:
            ships = await fetch_json(session, "https://swgoh.gg/api/ships/")
            print(f"✈️ {len(ships)} vaisseaux récupérés depuis l'API.")
            
            for item in ships:
                base_id = item.get("base_id", "").upper()
                name = item.get("name", "")
                img_url = item.get("image", "")
                
                if not base_id or not img_url:
                    continue
                    
                filename = img_url.split("/")[-1]
                thumbnail_name = filename.replace(".png", "")
                dest_path = SHIPS_DIR / filename
                
                is_new = not dest_path.exists()
                success = await download_image(session, img_url, dest_path)
                
                if success:
                    if is_new:
                        downloaded_list.append(name)
                    cursor.execute("""
                        INSERT INTO game_characters (base_id, name, type, thumbnail_name, image_path, is_image_valid)
                        VALUES (?, ?, 2, ?, ?, 1)
                        ON CONFLICT(base_id) DO UPDATE SET
                            name = excluded.name,
                            thumbnail_name = excluded.thumbnail_name,
                            image_path = excluded.image_path,
                            is_image_valid = 1
                    """, (base_id, name, thumbnail_name, str(dest_path.as_posix())))
            conn.commit()
        except Exception as e:
            print(f"❌ Erreur API Vaisseaux : {e}")
            
    conn.close()
    
    summary = {
        "total_chars": len(chars),
        "total_ships": len(ships),
        "new_downloads_count": len(downloaded_list),
        "new_downloaded_names": downloaded_list
    }
    print(f"✅ Synchro terminée ! {len(downloaded_list)} nouveaux portraits téléchargés : {downloaded_list}")
    return summary

if __name__ == "__main__":
    asyncio.run(process_swgoh_gg())
