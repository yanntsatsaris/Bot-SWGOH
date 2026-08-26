"""
services/gac_ship_counters_scraper.py
Service async pour scraper la tier list fleet et les ship counters.
"""
import asyncio
import os
import sys
import json
import logging
import tempfile
from pathlib import Path

log = logging.getLogger(__name__)

# Tous les capital ships connus
ALL_CAPITAL_IDS = [
    "CAPITALLEVIATHAN",
    "CAPITALPROFUNDITY",
    "CAPITALEXECUTOR",
    "CAPITALNEGOTIATOR",
    "CAPITALMONCALAMARICRUISER",
    "CAPITALCHIMAERA",
    "CAPITALFINALIZER",
    "CAPITALSTARDESTROYER",
    "CAPITALMALEVOLENCE",
    "CAPITALRADDUS",
    "CAPITALJEDICRUISER",
]

ALL_LEAGUES = ["kyber", "aurodium", "chromium", "bronzium", "carbonite"]


class GacShipCountersScraper:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(1)  # 1 navigateur a la fois pour les vaisseaux

    # ─── FLEET TIER LIST ─────────────────────────────────────────────────────────

    async def refresh_fleet_tier_list(
        self,
        side: str = "offense",
        league: str = "kyber",
        season: str = "current",
    ) -> int:
        """Lance le scraping de la tier list fleet pour un cote/ligue donnes.
        Retourne le nombre d'entrees sauvegardees (-1 en cas d'erreur)."""
        from database.db import save_fleet_tier_list

        project_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )
        worker_path = os.path.join(project_dir, "scripts", "fleet_tier_sb_worker.py")
        temp_dir = os.path.join(project_dir, "temp_fleet_tier")
        os.makedirs(temp_dir, exist_ok=True)
        out_file = os.path.join(temp_dir, f"fleet_tier_{side}_{league}.json")

        log.info(f"[FleetTier] Scraping tier list {side}/{league}...")

        async with self.semaphore:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                worker_path,
                out_file,
                side,
                league,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300)

        if process.returncode != 0:
            log.error(
                f"[FleetTier] Erreur worker {side}/{league}:\n"
                f"STDERR: {stderr.decode('utf-8', errors='ignore')}"
            )
            return -1

        if not os.path.exists(out_file):
            log.error(f"[FleetTier] Fichier de sortie introuvable: {out_file}")
            return -1

        try:
            with open(out_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("entries", [])
            if not entries:
                log.warning(f"[FleetTier] Aucune entree scrappee pour {side}/{league}")
                return 0
            saved = await save_fleet_tier_list(entries)
            log.info(f"[FleetTier] {saved} entrees sauvegardees pour {side}/{league}")
            try:
                if os.path.exists(out_file):
                    os.remove(out_file)
            except Exception:
                pass
            return saved
        except Exception as e:
            log.error(f"[FleetTier] Erreur parsing JSON {out_file}: {e}")
            return -1

    async def refresh_all_fleet_tier(self, leagues: list[str] | None = None) -> dict:
        """Refresh la tier list pour tous les cotes et toutes les ligues."""
        if leagues is None:
            leagues = ALL_LEAGUES[:2]  # Kyber + Aurodium par defaut
        results = {}
        for league in leagues:
            for side in ["offense", "defense"]:
                key = f"{side}_{league}"
                count = await self.refresh_fleet_tier_list(side=side, league=league)
                results[key] = count
        return results

    # ─── SHIP COUNTERS ─────────────────────────────────────────────────────────

    async def refresh_ship_counters(
        self,
        def_capital_id: str,
        season_id: str = "current",
        d_members: str = "",
        d_reinforcements: str = "",
    ) -> int:
        """Lance le scraping des counters pour un capital ship defensif.
        Retourne le nombre de counters sauvegardes (-1 en cas d'erreur)."""
        from database.db import save_ship_counters

        project_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..")
        )
        worker_path = os.path.join(project_dir, "scripts", "ship_counters_sb_worker.py")
        temp_dir = os.path.join(project_dir, "temp_ship_counters")
        os.makedirs(temp_dir, exist_ok=True)
        out_file = os.path.join(temp_dir, f"ship_counters_{def_capital_id}.json")

        log.info(f"[ShipCounters] Scraping counters pour {def_capital_id}...")

        cmd_args = [sys.executable, worker_path, def_capital_id, out_file, season_id]
        if d_members or d_reinforcements:
            cmd_args.append(d_members or "")
            if d_reinforcements:
                cmd_args.append(d_reinforcements)

        async with self.semaphore:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=project_dir,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=360)

        if process.returncode != 0:
            log.error(
                f"[ShipCounters] Erreur worker {def_capital_id}:\n"
                f"STDERR: {stderr.decode('utf-8', errors='ignore')}"
            )
            return -1

        if not os.path.exists(out_file):
            log.error(f"[ShipCounters] Fichier de sortie introuvable: {out_file}")
            return -1

        try:
            with open(out_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            counters = data.get("counters", [])
            actual_season = data.get("season_id", season_id)

            if not counters:
                log.warning(f"[ShipCounters] Aucun counter pour {def_capital_id}")
                return 0

            saved = await save_ship_counters(actual_season, def_capital_id, counters)
            log.info(f"[ShipCounters] {saved} counters sauvegardes pour {def_capital_id}")
            try:
                if os.path.exists(out_file):
                    os.remove(out_file)
            except Exception:
                pass
            return saved
        except Exception as e:
            log.error(f"[ShipCounters] Erreur parsing JSON: {e}")
            return -1

    async def ensure_ship_counters_available(
        self,
        capital_ids: list[str],
        max_age_hours: int = 24,
    ) -> dict[str, int]:
        """Verifie si les counters sont disponibles/recents pour les capitaux donnes.
        Lance le scraping pour ceux qui manquent ou sont trop vieux."""
        from database.db import get_ship_counters

        results = {}
        for capital_id in capital_ids:
            counters = await get_ship_counters(capital_id)
            if counters:
                # Verifier l'age
                import datetime
                last_upd = counters[0].get("last_updated", "")
                if last_upd:
                    try:
                        upd_dt = datetime.datetime.fromisoformat(last_upd)
                        age = datetime.datetime.now() - upd_dt
                        if age.total_seconds() < max_age_hours * 3600:
                            log.debug(f"[ShipCounters] {capital_id} deja a jour ({len(counters)} counters)")
                            results[capital_id] = len(counters)
                            continue
                    except:
                        pass
            log.info(f"[ShipCounters] {capital_id} absent ou trop vieux, lancement scraping...")
            count = await self.refresh_ship_counters(capital_id)
            results[capital_id] = max(count, 0)

        return results

    async def refresh_all_ship_counters(self, capital_ids: list[str] | None = None) -> dict:
        """Refresh tous les ship counters (sequentiel pour eviter les bans)."""
        if capital_ids is None:
            capital_ids = ALL_CAPITAL_IDS
        results = {}
        for cid in capital_ids:
            count = await self.refresh_ship_counters(cid)
            results[cid] = count
        return results
