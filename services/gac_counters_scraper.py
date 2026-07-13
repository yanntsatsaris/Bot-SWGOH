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

    async def refresh_counters_for_leader(self, def_leader_slug: str, real_leader_id: str, format_type: str, season_id: str = "current", d_members: str = "") -> None:
        """
        Lance le worker SeleniumBase pour scrapper les counters d'un leader défensif.
        d_members: liste des IDs séparés par des virgules (ex: "CAPTAINREX,CHOPPERS3")
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
            d_members,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_dir
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            log.error(f"Erreur worker counters {def_leader_slug}:\nSTDERR: {stderr.decode('utf-8', errors='ignore')}\nSTDOUT: {stdout.decode('utf-8', errors='ignore')}")
            return False
            
        import os
        import json
        from database.db import save_counters_to_db
        
        if not os.path.exists(out_file_path):
            log.error(f"Le fichier {out_file_path} n'a pas été généré.")
            return False
            
        try:
            with open(out_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            counters = data.get("counters", [])
            if counters:
                await save_counters_to_db(season_id, format_type, real_leader_id, counters)
                log.info(f"{len(counters)} counters sauvegardés pour {real_leader_id} ({format_type}).")
            else:
                log.warning(f"Aucun counter trouvé pour {real_leader_id}.")
            return True
        except json.JSONDecodeError as e:
            log.error(f"Erreur de décodage JSON: {e}")
            return False

    async def ensure_counters_available(self, leaders_dict: dict, format_type: str) -> None:
        """
        leaders_dict: dictionnaire { leader_id: "MEMBRE1,MEMBRE2,..." }
        """
        from database.db import get_db
        import datetime
        
        missing_leaders = {}
        async with get_db() as db:
            for l_id, members in leaders_dict.items():
                if not l_id or l_id in ["USED", "None"]:
                    continue
                    
                # Vérifie si le leader existe avec un âge < 7 jours
                cursor = await db.execute(
                    "SELECT last_updated FROM gac_counters WHERE def_leader_id = ? AND format = ? ORDER BY last_updated DESC LIMIT 1",
                    (l_id, format_type)
                )
                row = await cursor.fetchone()
                
                needs_scrape = True
                if row:
                    last_updated_str = row["last_updated"]
                    try:
                        last_updated = datetime.datetime.strptime(last_updated_str, "%Y-%m-%d %H:%M:%S")
                        age = (datetime.datetime.utcnow() - last_updated).days
                        if age > 7:
                            missing_leaders[l_id] = members
                        else:
                            needs_scrape = False
                    except Exception as e:
                        log.error(f"Erreur date: {e}")
                else:
                    missing_leaders[l_id] = members
        
        if missing_leaders:
            log.info(f"Scraping nécessaire pour {len(missing_leaders)} leaders exacts : {list(missing_leaders.keys())}")
            for leader_id, members in missing_leaders.items():
                # swgoh.gg utilise directement le base_id pour l'URL
                await self.refresh_counters_for_leader(leader_id, leader_id, format_type, d_members=members)
