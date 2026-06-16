"""
debug_portraits.py — Diagnostic global des portraits (tous les persos)
"""
import os
import json
from pathlib import Path
from services.portrait_cache import get_portrait_path, PORTRAITS_DIR

UNITS_DATA_FILE = Path("database/all_units.json")

def main():
    print("🔍 Diagnostic global des portraits...")

    if not UNITS_DATA_FILE.exists():
        print("❌ Fichier database/all_units.json introuvable. Lance 'python3 sync_all_units.py' d'abord.")
        return

    with open(UNITS_DATA_FILE, "r", encoding="utf-8") as f:
        units = json.load(f)

    print(f"Persos connus en BDD : {len(units)}")
    print(f"Fichiers en local : {len(list(PORTRAITS_DIR.glob('*.png')))}")

    missing = []
    found = 0

    for u in units:
        bid = u["base_id"]
        path = get_portrait_path(bid)
        if path.exists():
            found += 1
        else:
            missing.append((bid, u["name"]))

    print(f"✅ Liés avec succès : {found}")
    print(f"❌ Non liés : {len(missing)}")

    if missing:
        print("\nExemples de personnages sans image :")
        for bid, name in missing[:15]:
            print(f"- {bid:.<25} ({name})")
        if len(missing) > 15:
            print(f"... et {len(missing)-15} autres.")

if __name__ == "__main__":
    main()
