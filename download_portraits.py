import os
import sys
import requests
import time
from pathlib import Path

# Tentative de chargement du mapping
try:
    from services.unit_names import STATIC_NAMES
    BASE_IDS = list(STATIC_NAMES.keys())
except ImportError:
    BASE_IDS = ["SITHPALPATINE", "DARTHVADER", "JEDIMASTERKENOBI"]

# --- CONFIGURATION ---
# On va tester ces deux URLs pour voir laquelle répond
AE2_URLS = ["http://127.0.0.1:3001", "http://localhost:3001"]
DEST_DIR = Path("assets/portraits")

def check_ae2():
    print("🔍 Recherche du conteneur swgoh-ae2 sur le port 3001...")
    for url in AE2_URLS:
        try:
            r = requests.get(url, timeout=3)
            print(f"✅ AE2 trouvé sur {url} (HTTP {r.status_code})")
            return url
        except:
            continue
    print("❌ AE2 est introuvable sur le port 3001 (testé localhost et 127.0.0.1).")
    print("Vérifie que ton Docker run a bien le paramètre -p 3001:8080.")
    return None

def download_portrait(ae2_url, base_id):
    # Variations de noms d'assets possibles dans les fichiers du jeu
    variations = [
        f"charui_{base_id.lower()}",
        f"tex.avatars_{base_id.lower()}",
        base_id.lower(),
        f"charui_{base_id.upper()}"
    ]

    for asset_name in variations:
        url = f"{ae2_url}/Asset/single?assetName={asset_name}&forceReDownload=false"
        try:
            # Extraction longue donc timeout élevé
            response = requests.get(url, timeout=25)
            if response.status_code == 200:
                if response.content.startswith(b'\x89PNG'):
                    dest_path = DEST_DIR / f"{base_id.lower()}.png"
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_bytes(response.content)
                    return True, asset_name
        except:
            continue
    return False, None

def main():
    print("🎨 --- DIAGNOSTIC PORTRAITS AE2 ---")

    ae2_url = check_ae2()
    if not ae2_url:
        return

    # Création du dossier
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    print("\n⏳ Mise à jour du Manifest (étape cruciale)...")
    try:
        r = requests.get(f"{ae2_url}/Asset/downloadManifest", timeout=45)
        print(f"✅ Manifest mis à jour (HTTP {r.status_code})")
    except Exception as e:
        print(f"⚠️  Impossible de mettre à jour le manifest : {e}")

    total = len(BASE_IDS)
    print(f"\n📦 Analyse de {total} personnages...")

    ok = 0
    for i, bid in enumerate(BASE_IDS, 1):
        success, found_name = download_portrait(ae2_url, bid)

        if success:
            print(f"[{i}/{total}] ✓ {bid} trouvé sous le nom '{found_name}'")
            ok += 1
        else:
            print(f"[{i}/{total}] ✗ {bid} : Aucune variation trouvée")

        # On s'arrête au bout de 5 échecs pour ne pas polluer ton terminal
        if i >= 5 and ok == 0:
            print("\n🛑 Trop d'échecs consécutifs. AE2 ne semble pas avoir ces textures.")
            print("As-tu bien lancé 'SwgohAssetGetterConsole.exe -downloadManifest' dans le conteneur ?")
            break

        time.sleep(0.1)

    print(f"\n✨ Résultat final : {ok}/{i} portraits récupérés.")

if __name__ == "__main__":
    main()
