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
from dotenv import load_dotenv

load_dotenv()

AE2_URL = "http://localhost:3001"
COMLINK_URL = os.getenv("COMLINK_URL", "http://localhost:3000")
DEST_DIR = Path("assets/portraits")
ALL_UNITS_FILE = Path("database/all_units.json")

def get_units_from_comlink():
    """Récupère la liste complète des unités et leur thumbnailName."""
    print(f"🔍 Connexion à Comlink ({COMLINK_URL})...")
    try:
        r = requests.post(f"{COMLINK_URL}/data", json={"payload": {"collection": "unitsList"}}, timeout=15)
        r.raise_for_status()
        data = r.json()
        units = data if isinstance(data, list) else data.get("unitsList", [])
        return {u["baseId"]: u["thumbnailName"] for u in units if u.get("baseId") and u.get("thumbnailName")}
    except Exception as e:
        print(f"❌ Erreur Comlink : {e}")
        return {}

def download_portrait(base_id, thumbnail_name):
    """Tente de télécharger un portrait via AE2."""
    # On teste le thumbnail officiel puis des variantes
    variations = [thumbnail_name, thumbnail_name.replace("tex.avatars_", "charui_"), f"charui_{base_id.lower()}"]

    for asset in variations:
        clean_asset = asset.replace(".png", "")
        url = f"{AE2_URL}/Asset/single?assetName={clean_asset}&forceReDownload=false"
        try:
            resp = requests.get(url, timeout=20)
            if resp.status_code == 200 and resp.content.startswith(b'\x89PNG'):
                # Sauvegarde normalisée charui_xxx.png
                save_name = clean_asset if clean_asset.startswith("charui_") else f"charui_{clean_asset}"
                dest = DEST_DIR / f"{save_name}.png"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                return True
        except:
            continue
    return False

def main():
    print("🎨 SWGOH Portrait Downloader (Full Sync)")

    # 1. Liste des persos
    thumb_map = get_units_from_comlink()
    if not thumb_map:
        print("Abandon : impossible de récupérer la liste des unités.")
        return

    # 2. Manifest
    print("⏳ Mise à jour du Manifest AE2...")
    try: requests.get(f"{AE2_URL}/Asset/downloadManifest", timeout=45)
    except: pass

    # 3. Boucle de téléchargement sur TOUS les persos trouvés
    total = len(thumb_map)
    print(f"📦 {total} unités à traiter...")

    ok = 0
    for i, (bid, thumb) in enumerate(thumb_map.items(), 1):
        if download_portrait(bid, thumb):
            ok += 1

        if i % 20 == 0 or i == total:
            print(f"[{i}/{total}] Portraits en cours...")

    print(f"\n✨ Terminé ! {ok}/{total} portraits récupérés.")

if __name__ == "__main__":
    main()
