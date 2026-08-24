"""
services/gac_omicron_scraper.py — Service de scraping et gestion des Omicrons GAC
"""
import sys
import os
import json
import logging
import asyncio
from pathlib import Path
from database.db import get_db, save_gac_valid_omicrons, get_gac_valid_omicrons

log = logging.getLogger(__name__)

class GacOmicronScraper:
    def __init__(self):
        self.lock = asyncio.Lock()

    async def scrape_and_sync(self, progress_callback=None) -> int:
        """
        Lance le scraping de swgoh.gg pour les Omicrons GAC et les enregistre en base de données.
        """
        async with self.lock:
            if progress_callback:
                await progress_callback("🔄 Démarrage du scraping des Omicrons GAC depuis swgoh.gg...")

            project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            worker_path = os.path.join(project_dir, "scripts", "gac_omicrons_sb_worker.py")
            temp_dir = os.path.join(project_dir, "temp_data")
            os.makedirs(temp_dir, exist_ok=True)
            out_file_path = os.path.join(temp_dir, "gac_omicrons_report.json")

            log.info("Lancement du worker SeleniumBase pour les Omicrons GAC...")
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                worker_path,
                out_file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=project_dir
            )

            # Lecture et transmission des logs du worker en direct
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line_str = line.decode('utf-8', errors='ignore').strip()
                if line_str:
                    log.info("[Omicrons Worker] %s", line_str)

            await process.wait()

            if process.returncode != 0:
                log.error("Worker Omicrons GAC terminé avec code d'erreur : %d", process.returncode)
                if progress_callback:
                    await progress_callback(f"❌ Erreur lors du scraping des Omicrons GAC (code {process.returncode}).")
                return 0

            if not os.path.exists(out_file_path):
                log.error("Fichier de sortie Omicrons introuvable : %s", out_file_path)
                return 0

            try:
                with open(out_file_path, "r", encoding="utf-8") as f:
                    omicrons_data = json.load(f)
            except Exception as e:
                log.error("Erreur lecture JSON Omicrons GAC : %s", e)
                return 0

            # Sauvegarde en BDD
            count = await save_gac_valid_omicrons(omicrons_data)
            log.info("✅ %d Omicrons GAC synchronisés en BDD.", count)

            if progress_callback:
                await progress_callback(f"✅ **{count} Omicrons GAC** synchronisés avec succès en base de données.")

            return count
