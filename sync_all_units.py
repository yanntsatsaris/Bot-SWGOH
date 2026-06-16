"""
sync_all_units.py — Récupère l'intégralité des unités depuis Comlink
"""
import requests
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

COMLINK_URL = os.getenv("COMLINK_URL", "http://localhost:3000")
OUTPUT_FILE = Path("database/all_units.json")

def main():
    print(f"🔍 Interrogation de Comlink sur {COMLINK_URL}...")

    # 1. Récupération de unitsList
    try:
        r = requests.post(f"{COMLINK_URL}/data", json={"payload": {"collection": "unitsList"}}, timeout=15)
        r.raise_for_status()
        units = r.json()
        if isinstance(units, dict): units = units.get("unitsList", [])
    except Exception as e:
        print(f"❌ Erreur lors de la récupération de la liste des unités : {e}")
        return

    # 2. Récupération des noms (localization)
    print("🌍 Récupération des traductions...")
    name_map = {}
    try:
        r = requests.post(f"{COMLINK_URL}/localization", json={"id": "Loc_ENG_TXT"}, timeout=20)
        if r.status_code == 200:
            bundle = r.json().get("localizationBundle", "")
            for line in bundle.splitlines():
                if "_NAME:" in line and "UNIT_" in line:
                    key, _, value = line.partition(":")
                    base_id = key.replace("UNIT_", "").replace("_NAME", "")
                    name_map[base_id] = value.strip()
    except:
        print("⚠️  Traductions indisponibles, utilisation des BaseID.")

    # 3. Structuration des données
    all_units = []
    for u in units:
        if u.get("combatType") != 1: continue # On ne garde que les personnages (pas les vaisseaux)

        bid = u.get("baseId", "")
        thumb = u.get("thumbnailName", "")
        name = name_map.get(bid, bid.replace("_", " ").title())

        all_units.append({
            "base_id": bid,
            "name": name,
            "thumbnail_name": thumb.replace("tex.avatars_", "")
        })

    # 4. Sauvegarde
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_units, f, indent=2, ensure_ascii=False)

    print(f"✅ Terminé ! {len(all_units)} personnages enregistrés dans {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
