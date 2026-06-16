"""
download_portraits.py — Télécharge les portraits SWGOH via swgoh-ae2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import os
import sys
import requests
import time
import json
from pathlib import Path

# Tentative de chargement du mapping
try:
    from services.unit_names import STATIC_NAMES
    BASE_IDS = list(STATIC_NAMES.keys())
except ImportError:
    BASE_IDS = ["SITHPALPATINE", "DARTHVADER", "JEDIMASTERKENOBI"]

AE2_URL = "http://localhost:3001"
COMLINK_URL = "http://localhost:3000"
DEST_DIR = Path("assets/portraits")
THUMB_MAP_FILE = Path("utils/unit_thumbs.json")

def get_comlink_thumbs():
    """Récupère le mapping officiel thumbnailName depuis Comlink."""
    print(f"🔍 Récupération du mapping Comlink sur {COMLINK_URL}...")
    try:
        r = requests.post(f"{COMLINK_URL}/data", json={"payload": {"collection": "unitsList"}}, timeout=10)
        if r.status_code == 200:
            units = r.json()
            if isinstance(units, dict): units = units.get("unitsList", [])
            mapping = {u["baseId"]: u["thumbnailName"] for u in units if u.get("baseId") and u.get("thumbnailName")}

            # Sauvegarde pour le bot
            THUMB_MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(THUMB_MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=2)
            print(f"✅ Mapping sauvegardé ({len(mapping)} unités)")
            return mapping
    except Exception as e:
        print(f"⚠️ Impossible de contacter Comlink : {e}")
    return {}

def download_portrait(base_id, thumb_name=None):
    # Liste des variations de noms d'assets à tester
    variations = []
    if thumb_name:
        variations.append(thumb_name)
        variations.append(thumb_name.replace("tex.avatars_", "charui_"))

    variations.extend([
        f"charui_{base_id.lower()}",
        f"charui_{base_id.upper()}",
        base_id.lower(),
        f"tex.avatars_{base_id.lower()}"
    ])

    # On retire les doublons tout en gardant l'ordre
    variations = list(dict.fromkeys(variations))

    for asset_name in variations:
        # Nettoyage pour AE2
        lookup = asset_name.replace(".png", "")
        url = f"{AE2_URL}/Asset/single?assetName={lookup}&forceReDownload=false"
        try:
            response = requests.get(url, timeout=20)
            if response.status_code == 200 and response.content.startswith(b'\x89PNG'):
                # On sauvegarde sous le nom 'charui_xxx.png' pour la cohérence
                save_name = lookup if lookup.startswith("charui_") else f"charui_{lookup}"
                if "tex.avatars_" in save_name:
                    save_name = save_name.replace("tex.avatars_", "charui_")

                dest_path = DEST_DIR / f"{save_name}.png"
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(response.content)
                return True, save_name
        except:
            continue
    return False, None

def main():
    print("🎨 SWGOH Portrait Downloader (AE2 + Comlink Mapping)")

    # 1. Mapping
    thumb_map = get_comlink_thumbs()

    # 2. Dossier
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    # 3. Manifest
    print("\n⏳ Mise à jour du Manifest AE2...")
    try:
        requests.get(f"{AE2_URL}/Asset/downloadManifest", timeout=45)
    except: pass

    total = len(BASE_IDS)
    print(f"\n📦 Traitement de {total} personnages...")

    ok = 0
    for i, bid in enumerate(BASE_IDS, 1):
        thumb = thumb_map.get(bid)
        success, saved_as = download_portrait(bid, thumb)

        if success:
            ok += 1
            if i % 10 == 0 or i == total:
                print(f"[{i}/{total}] ✓ Portraits en cours...")
        else:
            print(f"[{i}/{total}] ✗ {bid} (non trouvé)")

    print(f"\n✨ Terminé ! {ok}/{total} portraits disponibles dans {DEST_DIR}.")

if __name__ == "__main__":
    main()
