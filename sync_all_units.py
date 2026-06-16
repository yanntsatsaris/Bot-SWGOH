"""
sync_all_units.py — Récupère et filtre les unités selon la logique validée par script shell
"""
import asyncio
import json
from pathlib import Path
from services.comlink import get_game_data, get_localization

OUTPUT_FILE = Path("database/all_units.json")

async def sync():
    print("🚀 Synchronisation du référentiel GAC (Logique Shell)...")

    try:
        # 1. Récupération des données brutes
        raw_units = await get_game_data()
        if not raw_units:
            print("❌ Aucune unité reçue.")
            return

        # 2. Récupération des traductions
        print("🌍 Récupération des noms...")
        name_map = {}
        bundle = await get_localization()
        if bundle:
            for line in bundle.splitlines():
                if "_NAME:" in line and "UNIT_" in line:
                    key, _, value = line.partition(":")
                    base_id = key.replace("UNIT_", "").replace("_NAME", "")
                    name_map[base_id] = value.strip()

        # 3. Filtrage et Structuration (Logique JQ)
        # .units[] | select(.obtainable == true and .obtainableTime == "0")
        all_units = []
        for u in raw_units:
            if not (u.get("obtainable") is True and u.get("obtainableTime") == "0"):
                continue

            bid = u.get("baseId", "")
            # Extraction propre du thumbnail
            thumb = u.get("thumbnailName", "").replace("tex.avatars_", "")
            name = name_map.get(bid, bid.replace("_", " ").title())
            combat_type = u.get("combatType", 1)

            all_units.append({
                "base_id": bid,
                "name": name,
                "thumbnail_name": thumb,
                "type": "character" if combat_type == 1 else "ship"
            })

        # 4. Tri par nom pour faciliter le débug
        all_units.sort(key=lambda x: x["name"])

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_units, f, indent=2, ensure_ascii=False)

        print(f"\n✨ Terminé ! {len(all_units)} unités filtrées et enregistrées.")

    except Exception as e:
        print(f"\n❌ Erreur : {e}")

if __name__ == "__main__":
    asyncio.run(sync())
