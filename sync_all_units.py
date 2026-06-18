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

        # 2. Récupération des traductions via Comlink (Noms en Français)
        print("🌍 Récupération des noms...")
        name_map = {}
        try:
            bundle = await get_localization()
            if bundle:
                for line in bundle.splitlines():
                    # Le séparateur standard de SWGOH est "|"
                    if "|" in line:
                        key, _, value = line.partition("|")
                        name_map[key] = value.strip()
                    elif ":" in line:
                        key, _, value = line.partition(":")
                        name_map[key] = value.strip()
                print(f"✅ {len(name_map)} clés de traduction trouvées.")
            else:
                print("⚠️  Traductions indisponibles.")
        except Exception as e:
            print(f"⚠️  Erreur localization : {e}")

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
            
            # Utilisation directe du nameKey fourni par l'API
            name_key = u.get("nameKey", "")
            name = name_map.get(name_key, bid.replace("_", " ").title())
            
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
