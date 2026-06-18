"""
debug_comlink_meta.py — Affiche la structure des métadonnées Comlink
"""
import asyncio
import json
from services.comlink import _post_raw

async def main():
    print("🔍 Récupération des metadata...")
    try:
        meta = await _post_raw("metadata", {})
        print(f"Clés disponibles : {list(meta.keys())}")

        if "localization" in meta:
            print("\nContenu de 'localization' :")
            print(json.dumps(meta["localization"], indent=2))
        elif "strings" in meta:
            print("\nContenu de 'strings' :")
            print(json.dumps(meta["strings"], indent=2))
        else:
            print("\nSection de localisation introuvable dans les clés.")

    except Exception as e:
        print(f"❌ Erreur : {e}")

if __name__ == "__main__":
    asyncio.run(main())
