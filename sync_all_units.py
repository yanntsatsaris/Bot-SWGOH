"""
sync_all_units.py — Récupère et filtre les unités avec dédoublonnage strict
"""
import asyncio
import json
from pathlib import Path
from services.comlink import get_game_data, get_localization

OUTPUT_FILE = Path("database/all_units.json")

async def sync():
    import aiohttp
    
    print("🚀 Initialisation du référentiel depuis Comlink...")
    headers = {"Content-Type": "application/json"}
    base_url = "http://localhost:3200"

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # ÉTAPE 1 : EXTRACTION DES VERSIONS (POST /metadata)
            print("1️⃣ Récupération des versions (metadata)...")
            async with session.post(f"{base_url}/metadata", json={"payload": {}}) as resp:
                resp.raise_for_status()
                meta = await resp.json()
            
            game_version = meta.get("latestGamedataVersion")
            loc_version = meta.get("latestLocalizationBundleVersion")
            
            if not game_version or not loc_version:
                print("❌ Versions introuvables.")
                return

            # ÉTAPE 2 : TÉLÉCHARGEMENT DU ROSTER (POST /data)
            print(f"2️⃣ Récupération du roster (version: {game_version})...")
            payload_data = {
                "payload": {
                    "version": game_version,
                    "includePveUnits": True,
                    "requestSegment": 0
                },
                "enums": False
            }
            async with session.post(f"{base_url}/data", json=payload_data) as resp:
                resp.raise_for_status()
                data = await resp.json()

            raw_units = data.get("units", [])
            playable_units = []
            processed_ids = set()

            for u in raw_units:
                if u.get("obtainable") is True and str(u.get("obtainableTime")) == "0":
                    bid = u.get("baseId", "")
                    if bid and bid not in processed_ids:
                        playable_units.append(u)
                        processed_ids.add(bid)

            print(f"✅ {len(playable_units)} unités jouables trouvées.")

            # ÉTAPE 3 : TÉLÉCHARGEMENT DES TRADUCTIONS (POST /localization)
            print(f"3️⃣ Récupération des traductions (id: {loc_version})...")
            payload_loc = {
                "payload": {
                    "id": loc_version
                },
                "unzip": True
            }
            async with session.post(f"{base_url}/localization", json=payload_loc) as resp:
                resp.raise_for_status()
                loc_data = await resp.json()

            # Extraction récursive pour trouver Loc_ENG_US.txt
            def find_eng(obj):
                if isinstance(obj, dict):
                    if "Loc_ENG_US.txt" in obj:
                        return obj["Loc_ENG_US.txt"]
                    for v in obj.values():
                        res = find_eng(v)
                        if res: return res
                elif isinstance(obj, list):
                    for v in obj:
                        res = find_eng(v)
                        if res: return res
                return None

            bundle = find_eng(loc_data)
            name_map = {}
            if bundle:
                for line in bundle.split("\n"):
                    if "|" in line:
                        k, v = line.split("|", 1)
                        name_map[k.strip()] = v.strip()
                print(f"✅ {len(name_map)} noms extraits.")
            else:
                print("⚠️  Loc_ENG_US.txt introuvable dans le bundle.")

            # ÉTAPE 4 : CROISEMENT ET SAUVEGARDE BDD (MERGE)
            print("4️⃣ Sauvegarde en base de données...")
            
            from database.db import init_db, get_db
            from services.portrait_cache import get_portrait_path
            
            await init_db()
            async with get_db() as db:
                for unit in playable_units:
                    bid = unit.get("baseId", "")
                    name_key = unit.get("nameKey", "")
                    
                    # Fallback sur le baseId si non trouvé
                    final_name = name_map.get(name_key, bid.replace("_", " ").title())
                    
                    combat_type = unit.get("combatType", 1)
                    unit_type = "character" if combat_type == 1 else "ship"
                    thumb = unit.get("thumbnailName", "").replace("tex.avatars_", "")
                    
                    path_obj = get_portrait_path(bid)
                    image_path = path_obj.as_posix() if path_obj else None
                    
                    await db.execute("""
                        INSERT INTO units_directory (base_id, name, thumbnail_name, image_path)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(base_id) DO UPDATE SET
                            name=excluded.name,
                            thumbnail_name=excluded.thumbnail_name,
                            image_path=CASE WHEN units_directory.is_image_valid IS NOT 1 THEN excluded.image_path ELSE units_directory.image_path END
                    """, (bid, final_name, thumb, image_path))
                await db.commit()
            print("✅ Synchronisation terminée avec succès.")

    except Exception as e:
        print(f"❌ Erreur lors de la synchronisation : {e}")

if __name__ == "__main__":
    asyncio.run(sync())
