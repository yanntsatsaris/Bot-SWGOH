"""
download_portraits.py — Télécharge les portraits SWGOH via swgoh-ae2
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ce script utilise l'API locale swgoh-ae2 (port 3001) pour extraire
les textures officielles du jeu.

Usage :
    python3 download_portraits.py
"""
import os
import sys
import requests
import time
from pathlib import Path

# Tentative de chargement du mapping des noms pour avoir les base_id réels
try:
    from services.unit_names import STATIC_NAMES
    BASE_IDS = list(STATIC_NAMES.keys())
except ImportError:
    # Fallback minimal si les services ne sont pas accessibles
    BASE_IDS = ["SITHPALPATINE", "DARTHVADER", "JEDIMASTERKENOBI"]

# --- Configuration ---
# L'Asset Extractor tourne sur le port 3001 (Docker)
AE2_URL = "http://localhost:3001"
DEST_DIR = Path("assets/portraits")

def download_portrait(base_id):
    """
    Télécharge un portrait unique.
    L'Asset Extractor utilise généralement le préfixe 'charui_' pour les unités.
    """
    # Le nom de l'asset dans les fichiers du jeu
    asset_name = f"charui_{base_id.lower()}"

    # Construction de l'URL AE2
    # On forceReDownload=false pour économiser les ressources si déjà extrait
    url = f"{AE2_URL}/Asset/single?assetName={asset_name}&forceReDownload=false"

    dest_path = DEST_DIR / f"{base_id.lower()}.png"

    try:
        response = requests.get(url, timeout=45) # Extraction peut être lente
        if response.status_code == 200:
            # On vérifie qu'on a bien reçu une image PNG
            if response.content.startswith(b'\x89PNG'):
                dest_path.write_bytes(response.content)
                return True
            else:
                # Log d'erreur si AE2 renvoie autre chose (ex: JSON d'erreur)
                log_msg = response.text[:100]
                return False
    except Exception:
        return False
    return False

def main():
    print("🎨 SWGOH Portrait Downloader (via AE2)")
    print(f"🔗 Connexion à swgoh-ae2 sur {AE2_URL}...")

    # 1. Préparation dossier
    if not DEST_DIR.exists():
        DEST_DIR.mkdir(parents=True, exist_ok=True)

    # 2. Synchronisation du Manifest (optionnel mais recommandé)
    print("⏳ Mise à jour du Manifest AE2...")
    try:
        requests.get(f"{AE2_URL}/Asset/downloadManifest", timeout=60)
    except:
        print("⚠️  Avertissement : Impossible de forcer la mise à jour du manifest.")

    # 3. Boucle de téléchargement
    total = len(BASE_IDS)
    print(f"📦 {total} personnages à traiter.\n")

    downloaded = 0
    for i, bid in enumerate(BASE_IDS, 1):
        # Barre de progression
        percent = (i / total) * 100
        bar = '█' * int(percent / 4) + '-' * (25 - int(percent / 4))

        sys.stdout.write(f"\r|{bar}| {percent:3.0f}% [{i}/{total}] {bid[:15]:<15}")
        sys.stdout.flush()

        if download_portrait(bid):
            downloaded += 1

        # Petit temps de pause pour laisser le conteneur respirer
        time.sleep(0.1)

    print(f"\n\n✨ Terminé ! {downloaded}/{total} portraits sont disponibles dans {DEST_DIR}.")

if __name__ == "__main__":
    main()
