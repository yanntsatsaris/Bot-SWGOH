"""
sync_all_units.py — Récupère l'intégralité des unités via Comlink /metadata
"""
import asyncio
import json
from pathlib import Path
from services.comlink import _post

OUTPUT_FILE = Path("database/all_units.json")

async def sync():
    print("🔍 Récupération des données via Comlink /metadata...")

    try:
        # L'utilisateur indique que les unités sont dans /metadata
        data = await _post("metadata", {})

        # On cherche unitsList dans la réponse de metadata
        units = data.get("unitsList", [])
        if not units:
            # Fallback : certains Comlink mettent ça dans un sous-objet ou attendent /data
            print("⚠️  unitsList non trouvé dans /metadata, tentative via /data...")
            data_resp = await _post("data", {"collection": "unitsList", "includePveUnits": False})
            units = data_resp if isinstance(data_resp, list) else data_resp.get("unitsList", [])

        if not units:
            print("❌ Impossible de trouver la liste des unités.")
            return

        print(f"✅ {len(units)} unités trouvées.")

        # Récupération des noms (localization)
        print("🌍 Récupération des traductions...")
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

        # Structuration
        all_units = []
        for u in units:
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

        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(all_units, f, indent=2, ensure_ascii=False)

        print(f"✅ Terminé ! {len(all_units)} unités enregistrées dans {OUTPUT_FILE}")

    except Exception as e:
        print(f"❌ Erreur lors de la synchronisation : {e}")

if __name__ == "__main__":
    asyncio.run(sync())
