"""
sync_all_units.py — Récupère personnages et vaisseaux via Comlink
"""
import asyncio
import json
import os
from pathlib import Path
from services.comlink import _post

OUTPUT_FILE = Path("database/all_units.json")

async def sync():
    print("🔍 Récupération des unités (persos + vaisseaux) via Comlink...")

    # 1. Données brutes
    try:
        data = await _post("data", {
            "collection": "unitsList",
            "includePveUnits": False
        })
        units = data if isinstance(data, list) else data.get("unitsList", [])
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return

    # 2. Traductions
    print("🌍 Récupération des noms...")
    name_map = {}
    try:
        loc = await _post("localization", {"id": "Loc_ENG_TXT"})
        bundle = loc.get("localizationBundle", "")
        for line in bundle.splitlines():
            if "_NAME:" in line and "UNIT_" in line:
                key, _, value = line.partition(":")
                base_id = key.replace("UNIT_", "").replace("_NAME", "")
                name_map[base_id] = value.strip()
    except:
        print("⚠️  Traductions indisponibles.")

    # 3. Structuration
    all_units = []
    for u in units:
        bid = u.get("baseId", "")
        thumb = u.get("thumbnailName", "").replace("tex.avatars_", "")
        name = name_map.get(bid, bid.replace("_", " ").title())

        # Type 1 = Perso, Type 2 = Vaisseau
        combat_type = u.get("combatType", 1)

        all_units.append({
            "base_id": bid,
            "name": name,
            "thumbnail_name": thumb,
            "type": "character" if combat_type == 1 else "ship"
        })

    # 4. Sauvegarde
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_units, f, indent=2, ensure_ascii=False)

    print(f"✅ {len(all_units)} unités enregistrées.")

if __name__ == "__main__":
    asyncio.run(sync())
