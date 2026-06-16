"""
sync_all_units.py — Récupère et filtre les unités avec gestion d'erreurs localization
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
        print(f"✅ {len(raw_units)} unités reçues.")

        # 2. Récupération des traductions (Optionnel)
        print("🌍 Récupération des noms...")
        name_map = {}
        try:
            bundle = await get_localization()
            if bundle:
                for line in bundle.splitlines():
                    if "_NAME:" in line and "UNIT_" in line:
                        key, _, value = line.partition(":")
                        base_id = key.replace("UNIT_", "").replace("_NAME", "")
                        name_map[base_id] = value.strip()
                print(f"✅ {len(name_map)} noms traduits.")
            else:
                print("⚠️  Traductions vides ou indisponibles.")
        except Exception as e:
            print(f"⚠️  Erreur localization (ignorée) : {e}")
            print("Le bot continuera avec les BaseID.")

        # 3. Filtrage et Structuration
        all_units = []
        for u in raw_units:
            # Filtrage selon ta logique shell
            if not (u.get("obtainable") is True and u.get("obtainableTime") == "0"):
                continue

            bid = u.get("baseId", "")
            thumb = u.get("thumbnailName", "").replace("tex.avatars_", "")
            name = name_map.get(bid, bid.replace("_", " ").title())
            combat_type = u.get("combatType", 1)

            all_units.append({
                "base_id": bid,
                "name": name,
                "thumbnail_name": thumb,
                "type": "character" if combat_type == 1 else "ship"
            })

        all_units.sort(key=lambda x: x["name"])

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_units, f, indent=2, ensure_ascii=False)

        print(f"\n✨ Terminé ! {len(all_units)} unités filtrées et enregistrées.")

    except Exception as e:
        print(f"\n❌ Erreur fatale : {e}")

if __name__ == "__main__":
    asyncio.run(sync())
