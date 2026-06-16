"""
debug_portraits.py — Diagnostic global (Persos + Vaisseaux)
"""
import os
import json
from pathlib import Path
from services.portrait_cache import get_portrait_path, PORTRAITS_DIR, SHIPS_DIR

ALL_UNITS_FILE = Path("database/all_units.json")

def main():
    print("🔍 Diagnostic global des portraits...")

    if not ALL_UNITS_FILE.exists():
        print("❌ Fichier database/all_units.json introuvable. Lance 'python3 sync_all_units.py' d'abord.")
        return

    with open(ALL_UNITS_FILE, "r", encoding="utf-8") as f:
        units = json.load(f)

    print(f"Unités connues : {len(units)}")
    print(f"Portraits persos : {len(list(PORTRAITS_DIR.glob('*.png')))}")
    print(f"Portraits vaisseaux : {len(list(SHIPS_DIR.glob('*.png')))}")

    stats = {"character": {"ok": 0, "fail": 0}, "ship": {"ok": 0, "fail": 0}}
    missing = []

    for u in units:
        utype = u.get("type", "character")
        path = get_portrait_path(u["base_id"])
        if path.exists():
            stats[utype]["ok"] += 1
        else:
            stats[utype]["fail"] += 1
            missing.append(u)

    print(f"\n📊 Résumé :")
    print(f"  Personnages : {stats['character']['ok']} ✅ / {stats['character']['fail']} ❌")
    print(f"  Vaisseaux   : {stats['ship']['ok']} ✅ / {stats['ship']['fail']} ❌")

    if missing:
        print("\n❌ Exemples de manquants :")
        for u in missing[:15]:
            print(f"- [{u['type']}] {u['base_id']:.<25} ({u['name']})")

if __name__ == "__main__":
    main()
