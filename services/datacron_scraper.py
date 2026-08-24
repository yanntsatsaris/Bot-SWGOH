"""
services/datacron_scraper.py — Service de scraping et gestion des Datacrons (Sets, Variantes, Affixes)
"""
import sys
import os
import json
import logging
import asyncio
from pathlib import Path
from database.db import save_datacron_data, get_active_datacron_sets

log = logging.getLogger(__name__)

class DatacronScraper:
    def __init__(self):
        self.lock = asyncio.Lock()

    async def scrape_and_sync(self, progress_callback=None) -> int:
        """
        Lance le scraping de swgoh.gg pour les Datacrons actifs et les enregistre en BDD.
        """
        async with self.lock:
            if progress_callback:
                await progress_callback("🔄 Démarrage du scraping des Datacrons depuis swgoh.gg...")

            project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            worker_path = os.path.join(project_dir, "scripts", "datacrons_sb_worker.py")
            temp_dir = os.path.join(project_dir, "temp_data")
            os.makedirs(temp_dir, exist_ok=True)
            out_file_path = os.path.join(temp_dir, "datacrons_report.json")

            log.info("Lancement du worker SeleniumBase pour les Datacrons...")
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
                    log.info("[Datacrons Worker] %s", line_str)

            await process.wait()

            if process.returncode != 0:
                log.error("Worker Datacrons terminé avec code d'erreur : %d", process.returncode)
                if progress_callback:
                    await progress_callback(f"❌ Erreur lors du scraping des Datacrons (code {process.returncode}).")
                return 0

            if not os.path.exists(out_file_path):
                log.error("Fichier de sortie Datacrons introuvable : %s", out_file_path)
                return 0

            try:
                with open(out_file_path, "r", encoding="utf-8") as f:
                    datacrons_data = json.load(f)
            except Exception as e:
                log.error("Erreur lecture JSON Datacrons : %s", e)
                return 0

            # Sauvegarde en BDD
            count = await save_datacron_data(datacrons_data)
            log.info("✅ %d templates de Datacrons synchronisés en BDD.", count)

            if progress_callback:
                await progress_callback(f"✅ **{len(datacrons_data)} sets de Datacrons** ({count} templates/variantes) synchronisés avec succès en BDD.")

            return count

# Instance globale
datacron_scraper_service = DatacronScraper()
