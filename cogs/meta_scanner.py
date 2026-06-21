"""
cogs/meta_scanner.py — Tâche de fond pour scanner la méta GAC via Comlink
"""
import asyncio
import json
import logging
from collections import Counter

from discord.ext import commands, tasks

from database.db import get_db
from services.comlink import scan_all_leaderboards, get_player
from services.scouting import get_omicron_dict, _build_roster_index, _predict_zones
from utils.gac_config import get_gac_quotas

log = logging.getLogger(__name__)

async def analyze_player_meta(ally_code: str, fmt: str = "5v5") -> list[dict]:
    """
    Récupère le roster d'un joueur et prédit ses équipes probables
    en utilisant le moteur de scouting existant.
    """
    profile = await get_player(ally_code)
    roster = profile.get("rosterUnit", [])
    if not roster:
        return []
    
    omicron_dict = await get_omicron_dict()
    index = _build_roster_index(roster, omicron_dict)
    
    # On scanne les joueurs Kyber, on utilise donc les quotas Kyber
    league = "KYBER"
    quotas = get_gac_quotas(league, fmt)
    
    zones = _predict_zones(index, quotas, fmt)
    
    predicted_teams = []
    for zone_name, teams in zones.items():
        if zone_name == "Fleet":
            continue # Pour l'instant on se concentre sur les escouades de personnages
            
        for team in teams:
            if team.get("leader_id") and team["source"] != "empty":
                predicted_teams.append({
                    "leader_id": team["leader_id"],
                    "members_ids": team["members_ids"],
                    "zone": zone_name,
                    "source": team["source"],
                })
    
    return predicted_teams


async def build_meta_report(players: list[dict], fmt: str = "5v5") -> list[dict]:
    """
    Pour chaque joueur, on prédit ses équipes, puis on agrège
    pour trouver les compositions les plus fréquentes.
    """
    team_counter = Counter()    # (leader, frozenset(members)) -> count
    total_players = 0
    
    for player in players:
        ally_code = player.get("allyCode")
        if not ally_code:
            continue
            
        try:
            teams = await analyze_player_meta(ally_code, fmt)
            if not teams:
                continue
                
            total_players += 1
            
            for team in teams:
                leader = team["leader_id"]
                members = tuple(sorted(team["members_ids"]))
                team_counter[(leader, members)] += 1
                
            # Limite de taux pour /player : ~100 req/sec, mais on reste très prudent
            await asyncio.sleep(0.15)
            
        except Exception as e:
            log.warning("Échec de l'analyse pour le joueur %s: %s", ally_code, e)
            continue
            
    meta_teams = []
    for (leader, members), count in team_counter.most_common(50):
        meta_teams.append({
            "leader_id": leader,
            "members_ids": list(members),
            "seen_count": count,
            "usage_rate": count / total_players if total_players > 0 else 0,
        })
    
    return meta_teams


class MetaScannerCog(commands.Cog, name="MetaScanner"):
    """Cog responsable du scan quotidien de la méta via Comlink."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.daily_meta_scan.start()

    def cog_unload(self) -> None:
        self.daily_meta_scan.cancel()

    @tasks.loop(hours=24)
    async def daily_meta_scan(self) -> None:
        """Scan les classements Kyber et reconstruit les statistiques méta."""
        log.info("Démarrage du scan méta quotidien...")
        
        try:
            # Ligues: 100 = Kyber. Divisions: 5,10,15,20,25.
            top_players = await scan_all_leaderboards(leagues=[100], divisions=[5, 10, 15, 20, 25])
            log.info("%d joueurs trouvés dans les leaderboards Kyber.", len(top_players))
            
            if not top_players:
                log.warning("Aucun joueur trouvé. Scan méta annulé.")
                return

            for fmt in ["5v5", "3v3"]:
                log.info("Analyse de la méta %s...", fmt)
                meta = await build_meta_report(top_players, fmt=fmt)
                
                async with get_db() as db:
                    # On supprime les anciennes équipes scannées pour ce format
                    await db.execute(
                        "DELETE FROM meta_teams WHERE source_url = 'comlink_scan' AND format = ?",
                        (fmt,)
                    )
                    
                    # On insère le nouveau Top 20
                    for team in meta[:20]:
                        await db.execute(
                            """
                            INSERT INTO meta_teams (
                                leader_name, members, counters, format, win_rate, usage_rate, source_url
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                team["leader_id"],
                                json.dumps(team["members_ids"]),
                                "[]",
                                fmt,
                                None,
                                team["usage_rate"],
                                "comlink_scan"
                            )
                        )
                    await db.commit()
                log.info("Scan méta %s terminé : %d équipes identifiées.", fmt, len(meta))
        except Exception as e:
            log.exception("Erreur lors du scan méta quotidien : %s", e)

    @daily_meta_scan.before_loop
    async def before_daily_meta_scan(self) -> None:
        """Attend que le bot soit prêt avant de lancer la boucle."""
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MetaScannerCog(bot))
