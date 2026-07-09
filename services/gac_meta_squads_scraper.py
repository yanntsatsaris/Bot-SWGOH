import asyncio
import logging
import json
import os
from bs4 import BeautifulSoup
from database.db import get_db

logger = logging.getLogger("gac_squads_scraper")

class GacMetaSquadsScraper:
    def __init__(self, bot):
        self.bot = bot

    async def fetch_and_parse(self, format_type: str = "5v5", mode: str = "defense"):
        """
        Génère l'URL, demande à sb_worker.py de récupérer le HTML (via le VPS),
        et parse les résultats.
        """
        # On passe directement à swgoh.gg/gac/squads/
        target_url = "https://swgoh.gg/gac/squads/"
        
        logger.info(f"Début du scraping global meta ({format_type} {mode}) via SPA worker...")

        output_file = "gac_meta_squads.html"
        
        # Ce code sera exécuté sur le VPS.
        import subprocess
        import sys
        try:
            # Lancement du worker SeleniumBase spécial SPA
            process = await asyncio.create_subprocess_exec(
                sys.executable, "scripts/meta_sb_worker.py", target_url, output_file, format_type, mode,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Erreur meta_sb_worker (Code {process.returncode})\nSTDOUT: {stdout.decode()}\nSTDERR: {stderr.decode()}")
                return False

            if not os.path.exists(output_file):
                logger.error("Fichier HTML non généré par le worker.")
                return False

            with open(output_file, 'r', encoding='utf-8') as f:
                html = f.read()

            squads = self._parse_html(html)
            
            if squads:
                await self._save_to_db(squads, format_type, mode)
                logger.info(f"{len(squads)} squads {mode} ({format_type}) sauvegardées.")
                return True
            else:
                logger.warning("Aucune squad trouvée dans le HTML.")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors du scraping meta squads: {e}")
            return False

    def _parse_html(self, html: str) -> list[dict]:
        """
        Parse le tableau HTML pour extraire Units, Seen, Hold %, Banners.
        """
        soup = BeautifulSoup(html, 'html.parser')
        squads = []

        # Cherche la table
        table = soup.find('table')
        if not table:
            return squads

        tbody = table.find('tbody')
        if not tbody:
            return squads

        for row in tbody.find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 4:
                # 1. Units
                units = []
                # Les unités ont l'attribut 'data-unit-def-tooltip-app' contenant le base_id
                unit_divs = cols[0].find_all(lambda tag: tag.has_attr('data-unit-def-tooltip-app'))
                for u in unit_divs:
                    units.append(u['data-unit-def-tooltip-app'])

                if not units:
                    continue

                # 2. Seen
                seen_str = cols[1].text.strip().replace(',', '')
                # Gestion des "K" et "M" (ex: 83.7K)
                seen = 0
                if 'K' in seen_str:
                    seen = int(float(seen_str.replace('K', '')) * 1000)
                elif 'M' in seen_str:
                    seen = int(float(seen_str.replace('M', '')) * 1000000)
                else:
                    try:
                        seen = int(seen_str)
                    except ValueError:
                        pass

                # 3. Hold % / Win %
                hold_str = cols[2].text.strip().replace('%', '')
                try:
                    hold_percent = float(hold_str)
                except ValueError:
                    hold_percent = 0.0

                # 4. Banners
                banners_str = cols[3].text.strip()
                try:
                    avg_banners = float(banners_str)
                except ValueError:
                    avg_banners = 0.0

                squads.append({
                    "units": units,
                    "seen": seen,
                    "hold_percent": hold_percent,
                    "avg_banners": avg_banners
                })

        return squads

    async def _save_to_db(self, squads: list[dict], format_type: str, mode: str):
        # On considère la saison en cours (pour l'instant codé en dur ou récupéré autrement)
        season_id = "current" 
        
        async with get_db() as db:
            # On supprime les anciennes entrées pour ce format/mode
            await db.execute(
                "DELETE FROM gac_global_meta WHERE format = ? AND mode = ?",
                (format_type, mode)
            )
            
            for sq in squads:
                units_json = json.dumps(sq["units"])
                await db.execute("""
                    INSERT INTO gac_global_meta (season_id, format, mode, squad_units, seen, hold_percent, avg_banners)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (season_id, format_type, mode, units_json, sq["seen"], sq["hold_percent"], sq["avg_banners"]))
            
            await db.commit()
