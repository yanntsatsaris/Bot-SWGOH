"""
download_portraits.py — Télécharge les portraits SWGOH depuis GitHub swgoh-assets
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ce script permet de récupérer l'intégralité des portraits de personnages
directement depuis le dépôt communautaire Aetb/swgoh-assets.

Usage :
    python3 download_portraits.py
"""
import os
import sys
import requests
from pathlib import Path

# --- Configuration ---
# Dépôt source (fourni par l'utilisateur)
REPO_OWNER = "Aetb"
REPO_NAME = "swgoh-assets"
REPO_PATH = "tex/characters"

# URLs
API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents/{REPO_PATH}"
HEADERS = {"User-Agent": "SWGOH-Portrait-Downloader"}

# Dossier local de destination (doit correspondre à la config du bot)
DEST_DIR = Path("assets/portraits")

def download_portraits():
    """
    Liste et télécharge tous les portraits PNG du dépôt GitHub.
    """
    print("🚀 Initialisation du téléchargement des portraits...")

    # 1. Création du dossier si nécessaire
    if not DEST_DIR.exists():
        DEST_DIR.mkdir(parents=True, exist_ok=True)
        print(f"✅ Dossier créé : {DEST_DIR}")
    else:
        print(f"ℹ️  Dossier cible : {DEST_DIR}")

    # 2. Récupération de la liste des fichiers via l'API GitHub
    print(f"🔍 Connexion à GitHub ({REPO_OWNER}/{REPO_NAME})...")
    try:
        response = requests.get(API_URL, headers=HEADERS, timeout=20)

        if response.status_code == 404:
            print(f"❌ Erreur : Le chemin '{REPO_PATH}' n'a pas été trouvé dans le dépôt '{REPO_OWNER}/{REPO_NAME}'.")
            return
        elif response.status_code == 403:
            print("❌ Erreur : Limite de taux API GitHub atteinte. Réessayez plus tard.")
            return

        response.raise_for_status()
        files = response.json()
    except Exception as e:
        print(f"❌ Impossible de récupérer la liste des fichiers : {e}")
        return

    # 3. Filtrage des fichiers (uniquement les images PNG)
    images = [f for f in files if f['type'] == 'file' and f['name'].endswith('.png')]
    total = len(images)

    if total == 0:
        print("⚠️ Aucun portrait trouvé dans le répertoire distant.")
        return

    print(f"📦 {total} portraits détectés. Début du transfert...\n")

    # 4. Boucle de téléchargement
    downloaded = 0
    errors = 0

    for index, file_info in enumerate(images, 1):
        raw_name = file_info['name']
        download_url = file_info['download_url']

        # Nettoyage du nom pour le format attendu par le bot (base_id.png)
        # On retire le préfixe 'tex.avatars_' et on passe en minuscule
        clean_name = raw_name.replace("tex.avatars_", "").lower()
        save_path = DEST_DIR / clean_name

        try:
            # Téléchargement effectif
            img_res = requests.get(download_url, headers=HEADERS, timeout=15)
            img_res.raise_for_status()
            save_path.write_bytes(img_res.content)
            downloaded += 1
        except Exception:
            errors += 1
            # On continue malgré l'erreur sur ce fichier

        # --- Barre de progression simple ---
        progress = (index / total) * 100
        bar_len = 35
        filled_len = int(bar_len * index // total)
        bar = '█' * filled_len + '-' * (bar_len - filled_len)

        # Affichage dynamique sur la même ligne
        sys.stdout.write(f"\r|{bar}| {progress:3.0f}% ({index}/{total}) {clean_name[:20]:<20}")
        sys.stdout.flush()

    print(f"\n\n✨ Opération terminée !")
    print(f"✅ Portraits téléchargés : {downloaded}")
    if errors > 0:
        print(f"❌ Échecs : {errors}")
    print(f"📂 Localisation : {DEST_DIR.absolute()}")

if __name__ == "__main__":
    download_portraits()
