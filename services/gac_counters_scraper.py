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

    async def refresh_counters_for_leader(self, def_leader_slug: str, def_leader_id: str, format_type: str = "5v5", season_id: str = "current"):
        """
        Lance le worker pour scraper les counters d'un leader, récupère le JSON
        en stdout, et enregistre les données dans gac_counters.
        """
        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        worker_path = os.path.join(project_dir, "scripts", "counters_sb_worker.py")
        
        log.info(f"Scraping counters pour {def_leader_slug} ({format_type})...")
        
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            worker_path,
            def_leader_slug,
            "None", # Pas de sauvegarde HTML
            format_type,
            season_id,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_dir
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            log.error(f"Erreur worker counters {def_leader_slug}: {stderr.decode('utf-8', errors='ignore')}")
            return False
            
        output_str = stdout.decode('utf-8', errors='ignore')
        
        # Extraire le JSON entre ---JSON_START--- et ---JSON_END---
        import re
        import json
        from database.db import save_counters_to_db
        
        match = re.search(r'---JSON_START---\n(.*?)\n---JSON_END---', output_str, re.DOTALL)
        if not match:
            log.error(f"Impossible de trouver le JSON dans la sortie du worker pour {def_leader_slug}.")
            return False
            
        try:
            data = json.loads(match.group(1))
            counters = data.get("counters", [])
            if counters:
                await save_counters_to_db(season_id, format_type, def_leader_id, counters)
                log.info(f"{len(counters)} counters sauvegardés pour {def_leader_id} ({format_type}).")
            else:
                log.warning(f"Aucun counter trouvé pour {def_leader_id}.")
            return True
        except json.JSONDecodeError as e:
            log.error(f"Erreur de décodage JSON: {e}")
            return False

    async def ensure_counters_available(self, def_leader_ids: list[str], format_type: str, max_age_days: int = 7) -> None:
        """
        Vérifie si les counters sont présents et récents en BDD pour chaque leader.
        Si manquant ou trop vieux, lance le scraping.
        """
        from database.db import get_db
        import datetime
        
        missing_leaders = []
        async with get_db() as db:
            for leader_id in def_leader_ids:
                if not leader_id or leader_id in ["USED", "None"]:
                    continue
                    
                cursor = await db.execute(
                    """
                    SELECT last_updated FROM gac_counters 
                    WHERE def_leader_id = ? AND format = ?
                    ORDER BY last_updated DESC LIMIT 1
                    """,
                    (leader_id, format_type)
                )
                row = await cursor.fetchone()
                
                needs_scrape = True
                if row:
                    last_updated_str = row["last_updated"]
                    try:
                        last_updated = datetime.datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")
                        age = (datetime.datetime.utcnow() - last_updated).days
                        if age <= max_age_days:
                            needs_scrape = False
                    except Exception:
                        pass
                        
                if needs_scrape:
                    missing_leaders.append(leader_id)
        
        if missing_leaders:
            log.info(f"Scraping nécessaire pour {len(missing_leaders)} leaders : {missing_leaders}")
            for leader_id in missing_leaders:
                # swgoh.gg utilise directement le base_id pour l'URL
                await self.refresh_counters_for_leader(leader_id, leader_id, format_type)
