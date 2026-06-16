"""
debug_portraits.py — Diagnostic des portraits manquants
"""
import os
from pathlib import Path
from services.unit_names import STATIC_NAMES
from services.portrait_cache import get_portrait_path, PORTRAITS_DIR

def main():
    print("🔍 Diagnostic des portraits...")
    print(f"Dossier : {PORTRAITS_DIR.absolute()}")

    if not PORTRAITS_DIR.exists():
        print("❌ Le dossier des portraits n'existe pas !")
        return

    files = list(PORTRAITS_DIR.glob("*.png"))
    print(f"Nombre de fichiers .png trouvés : {len(files)}")

    missing = []
    found = 0

    for bid, name in STATIC_NAMES.items():
        path = get_portrait_path(bid)
        if path.exists():
            found += 1
        else:
            missing.append((bid, name))

    print(f"✅ Portraits liés avec succès : {found}")
    print(f"❌ Portraits manquants ou non liés : {len(missing)}")

    if missing:
        print("\nListe des manquants :")
        for bid, name in missing[:20]:
            print(f"- {bid:.<25} ({name})")
        if len(missing) > 20:
            print(f"... et {len(missing)-20} autres.")

    print("\nExemples de fichiers présents pour comparaison :")
    for f in files[:10]:
        print(f"  {f.name}")

if __name__ == "__main__":
    main()
