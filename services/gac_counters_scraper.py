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
        
        temp_dir = os.path.join(project_dir, "temp_counters")
        os.makedirs(temp_dir, exist_ok=True)
        out_file_path = os.path.join(temp_dir, f"counters_{real_leader_id}.json")
        
        log.info(f"Scraping counters pour {def_leader_slug} ({format_type})...")
        
        args = [
            sys.executable, worker_path, def_leader_slug, out_file_path, format_type, season_id
        ]
        if d_members:
            args.append(d_members)
            
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=project_dir
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            log.error(f"Erreur worker counters {def_leader_slug}:\nSTDERR: {stderr.decode('utf-8', errors='ignore')}\nSTDOUT: {stdout.decode('utf-8', errors='ignore')}")
            return False
            
        if not os.path.exists(out_file_path):
            log.error(f"Le fichier {out_file_path} n'a pas été généré.")
            return False
            
        import json
        from database.db import save_counters_to_db
            
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

    async def ensure_counters_available(self, leaders_dict: dict, format_type: str, progress_callback=None) -> None:
        """
        Vérifie si les counters sont récents pour chaque leader fourni,
        et lance le scraper si les données manquent ou sont trop vieilles.
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
            log.info(f"Extraction nécessaire pour {len(missing_leaders)} leaders exacts : {list(missing_leaders.keys())}")
            
            total_missing = len(missing_leaders)
            for i, (leader_id, members) in enumerate(missing_leaders.items()):
                # Protection : si la prédiction (venant de 5v5) donne trop de membres pour du 3v3, on annule d_members
                # pour récupérer au moins les counters génériques du leader plutôt que 0 counter.
                members_list = members.split(",") if members else []
                max_members = 2 if format_type == "3v3" else 4
                
                if len(members_list) > max_members:
                    members_list = members_list[:max_members]
                    members = ",".join(members_list)
                    log.info(f"L'équipe de {leader_id} a été tronquée à {max_members} membres pour coller au format {format_type}.")
                    
                await self.refresh_counters_for_leader(leader_id, leader_id, format_type, d_members=members)
                
                if progress_callback:
                    pct = int(((i + 1) / total_missing) * 10) + 90
                    bars = int((pct / 100) * 10)
                    bar_str = "■" * bars + "□" * (10 - bars)
                    try:
                        await progress_callback(f"⏳ **[{bar_str}] {pct}%** : Extraction des contres ({i+1}/{total_missing})...")
                    except Exception as e:
                        log.error(f"Erreur UI callback counters: {e}")
