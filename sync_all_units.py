"""
sync_all_units.py — Récupère et filtre les unités avec dédoublonnage strict
"""
import asyncio
import json
from pathlib import Path
from services.comlink import get_game_data, get_localization

OUTPUT_FILE = Path("database/all_units.json")

async def sync():
    print("🚀 Synchronisation du référentiel GAC...")

    try:
        # 1. Récupération des données brutes
        print("🔍 Récupération des unités...")
        raw_units = await get_game_data()
        if not raw_units:
            print("❌ Aucune unité reçue.")
            return
        print(f"✅ {len(raw_units)} unités brutes reçues.")

        # 2. Récupération des traductions via swgoh.gg (Noms propres garantis)
        print("🌍 Récupération des noms depuis swgoh.gg...")
        name_map = {}
        import aiohttp
        try:
            # On ajoute un faux User-Agent de navigateur pour contourner Cloudflare
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
            }
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get("https://swgoh.gg/api/characters/") as resp:
                    if resp.status == 200:
                        chars = await resp.json()
                        for c in chars:
                            name_map[c["base_id"]] = c["name"]
                    else:
                        print(f"⚠️  Erreur HTTP swgoh.gg caractères : {resp.status}")
                        
                async with session.get("https://swgoh.gg/api/ships/") as resp:
                    if resp.status == 200:
                        ships = await resp.json()
                        for s in ships:
                            name_map[s["base_id"]] = s["name"]
                    else:
                        print(f"⚠️  Erreur HTTP swgoh.gg vaisseaux : {resp.status}")
                        
            print(f"✅ {len(name_map)} noms récupérés depuis swgoh.gg.")
        except Exception as e:
            print(f"⚠️  Erreur swgoh.gg : {e}")

        # 3. Filtrage, Structuration et Dédoublonnage
        # Logique : baseId unique + obtainable
        processed_ids = set()
        all_units = []

        for u in raw_units:
            bid = u.get("baseId", "")
            if not bid or bid in processed_ids:
                continue

            # Filtrage selon ta logique shell
            # obtainable == True ET obtainableTime == "0"
            if not (u.get("obtainable") is True and u.get("obtainableTime") == "0"):
                continue

            thumb = u.get("thumbnailName", "").replace("tex.avatars_", "")
            
            # SWGOH.gg mappe directement le baseId au vrai nom
            name = name_map.get(bid, bid.replace("_", " ").title())
            
            combat_type = u.get("combatType", 1)

            all_units.append({
                "base_id": bid,
                "name": name,
                "thumbnail_name": thumb,
                "type": "character" if combat_type == 1 else "ship"
            })
            processed_ids.add(bid)

        # 4. Tri final
        all_units.sort(key=lambda x: x["name"])

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_units, f, indent=2, ensure_ascii=False)

        print(f"\n✨ Terminé ! {len(all_units)} unités uniques filtrées et enregistrées.")

        print("\n💾 Enregistrement dans la base de données SQLite...")
        from database.db import init_db, get_db
        from services.portrait_cache import get_portrait_path
        
        await init_db()
        async with get_db() as db:
            for unit in all_units:
                bid = unit["base_id"]
                name = unit["name"]
                thumb = unit["thumbnail_name"]
                # On détermine le chemin de l'image via la logique existante
                # On force _unit_data à se recharger (puisqu'on vient de l'écrire)
                path_obj = get_portrait_path(bid)
                image_path = path_obj.as_posix() if path_obj else None
                
                await db.execute("""
                    INSERT INTO units_directory (base_id, name, thumbnail_name, image_path)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(base_id) DO UPDATE SET
                        name=excluded.name,
                        thumbnail_name=excluded.thumbnail_name,
                        image_path=CASE WHEN units_directory.is_image_valid IS NOT 1 THEN excluded.image_path ELSE units_directory.image_path END
                """, (bid, name, thumb, image_path))
            await db.commit()
        print("✅ Base de données mise à jour.")

    except Exception as e:
        print(f"\n❌ Erreur fatale : {e}")

if __name__ == "__main__":
    asyncio.run(sync())
