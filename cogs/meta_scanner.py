"""
cogs/meta_scanner.py — Tâche de fond pour scanner la méta GAC via Comlink
"""
import asyncio
import json
import logging
from collections import Counter

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.db import get_db
from services.comlink import scan_all_leaderboards, get_player
from services.scouting import get_omicron_dict, get_zeta_dict, _build_roster_index, _predict_zones, get_ship_base_ids
from utils.gac_config import get_gac_quotas

log = logging.getLogger(__name__)

async def analyze_player_meta(ally_code: str | None = None, player_id: str | None = None, fmt: str = "5v5", league_name: str = "KYBER") -> list[dict]:
    """
    Récupère le roster d'un joueur et prédit ses équipes probables
    en utilisant le moteur de scouting existant.
    """
    profile = await get_player(ally_code=ally_code, player_id=player_id)
    roster = profile.get("rosterUnit", [])
    if not roster:
        return []
    
    omicron_dict = await get_omicron_dict()
    zeta_dict = await get_zeta_dict()
    ship_base_ids = await get_ship_base_ids()
    index = _build_roster_index(roster, omicron_dict, zeta_dict, ship_base_ids)
    
    # On utilise les quotas correspondant à la ligue
    quotas = get_gac_quotas(league_name, fmt)
    
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


async def build_meta_report(players: list[dict], fmt: str = "5v5", league_name: str = "KYBER") -> list[dict]:
    """
    Pour chaque joueur, on prédit ses équipes, puis on agrège
    pour trouver les compositions les plus fréquentes.
    """
    team_counter = Counter()    # (leader, frozenset(members)) -> count
    total_players = 0
    
    for player in players:
        # L'API peut renvoyer la donnée sous divers noms selon le format
        ally_code = player.get("allyCode")
        player_id = player.get("playerId") or player.get("player") or player.get("id") or player.get("player_id")
        
        # Si 'player' est directement une string (l'ID du joueur)
        if isinstance(player, str):
            player_id = player
            
        if not ally_code and not player_id:
            log.warning(f"Impossible de trouver l'ID pour l'entrée: {player}")
            continue
            
        try:
            teams = await analyze_player_meta(ally_code=ally_code, player_id=player_id, fmt=fmt, league_name=league_name)
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
            log.warning("Échec de l'analyse pour le joueur %s (ID %s): %s", ally_code, player_id, e)
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
        # CRON DÉSACTIVÉ — redondant avec le scraping swgoh.gg (gac_global_meta).
        # Le scan Comlink reste disponible via la commande /meta-scan-force.
        # self.daily_meta_scan.start()

    def cog_unload(self) -> None:
        if self.daily_meta_scan.is_running():
            self.daily_meta_scan.cancel()

    import datetime

    @tasks.loop(time=datetime.time(hour=3, minute=0, tzinfo=datetime.timezone.utc))  # Nuit lundi→mardi à 3h00 UTC
    async def daily_meta_scan(self) -> None:
        """Scan les classements de chaque ligue et reconstruit les statistiques méta. Exécuté une fois par semaine la nuit de lundi à mardi (après la fin du dernier combat GAC)."""
        log.info("Démarrage du scan méta quotidien...")
        
        leagues = {
            100: "KYBER",
            80: "AURODIUM",
            60: "CHROMIUM",
            40: "BRONZIUM",
            20: "CARBONITE"
        }
        
        try:
            for league_num, league_name in leagues.items():
                log.info(f"--- Démarrage scan ligue : {league_name} ---")
                # Divisions: 5,10,15,20,25.
                top_players = await scan_all_leaderboards(leagues=[league_num], divisions=[5, 10, 15, 20, 25])
                log.info("%d joueurs trouvés dans les leaderboards %s.", len(top_players), league_name)
                
                if not top_players:
                    log.warning("Aucun joueur trouvé pour %s. Scan ignoré.", league_name)
                    continue
    
                for fmt in ["5v5", "3v3"]:
                    log.info("Analyse de la méta %s (%s)...", fmt, league_name)
                    meta = await build_meta_report(top_players, fmt=fmt, league_name=league_name)
                    
                    async with get_db() as db:
                        # On supprime les anciennes équipes scannées pour ce format et cette ligue
                        await db.execute(
                            "DELETE FROM meta_teams WHERE source_url = 'comlink_scan' AND format = ? AND league = ?",
                            (fmt, league_name)
                        )
                        
                        # On insère le nouveau Top 20
                        for team in meta[:20]:
                            await db.execute(
                                """
                                INSERT INTO meta_teams (
                                    leader_name, members, counters, format, league, win_rate, usage_rate, source_url
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    team["leader_id"],
                                    json.dumps(team["members_ids"]),
                                    "[]",
                                    fmt,
                                    league_name,
                                    None,
                                    team["usage_rate"],
                                    "comlink_scan"
                                )
                            )
                        await db.commit()
                    log.info("Scan méta %s (%s) terminé : %d équipes identifiées.", fmt, league_name, len(meta))
        except Exception as e:
            log.exception("Erreur lors du scan méta quotidien : %s", e)

    @daily_meta_scan.before_loop
    async def before_daily_meta_scan(self) -> None:
        """Attend que le bot soit prêt avant de lancer la boucle."""
        await self.bot.wait_until_ready()

    @app_commands.command(name="meta-scan-force", description="Force le lancement immédiat du scan de la méta GAC")
    @app_commands.default_permissions(administrator=True)
    async def force_scan(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("Lancement du scan méta forcé... Vérifiez les logs pour l'avancement.")
        # On lance la tâche en asynchrone pour ne pas bloquer l'interaction
        self.bot.loop.create_task(self.daily_meta_scan())

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MetaScannerCog(bot))
