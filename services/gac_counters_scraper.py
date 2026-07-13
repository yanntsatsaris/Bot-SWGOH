"""
services/gac_counters_scraper.py
Service pour lancer le scraping des counters.
"""
import asyncio
import os
import sys
import logging

log = logging.getLogger(__name__)

class GacCountersScraper:
    async def fetch_html_for_leader(self, def_leader_slug: str, output_file: str):
        """
        Lance le worker pour récupérer le HTML de la page des counters
        et le sauvegarde dans output_file.
        """
        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        worker_path = os.path.join(project_dir, "scripts", "counters_sb_worker.py")
        
        log.info(f"Lancement de la récupération HTML pour {def_leader_slug}...")
        
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_path,
            def_leader_slug,
            output_file,
            "5v5",
            "current",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_dir
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            log.error(f"Erreur lors de la récupération HTML: {stderr.decode('utf-8', errors='ignore')}")
            return False
            
        log.info(f"HTML sauvegardé dans {output_file}")
        return True
