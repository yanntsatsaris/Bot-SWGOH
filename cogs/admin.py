"""
cogs/admin.py — Commandes d'administration réservées aux administrateurs du serveur
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

log = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Admin"):
    """Commandes d'administration du bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /ping — Latence du bot
    # ------------------------------------------------------------------
    @app_commands.command(name="ping", description="Vérifie la latence du bot.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong ! Latence : **{latency} ms**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /sync — Resynchronisation manuelle des slash commands (admin only)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="sync",
        description="[Admin] Force la resynchronisation des slash commands.",
    )
    @app_commands.default_permissions(administrator=True)
    async def sync_commands(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(
                f"{len(synced)} commande(s) synchronisée(s) globalement.", ephemeral=True
            )
        except Exception:
            log.exception("Erreur lors de la synchronisation des commandes")
            await interaction.followup.send(
                "Erreur lors de la synchronisation.", ephemeral=True
            )

    @app_commands.command(name="logs", description="Affiche les 15 dernières lignes de bot.log")
    async def logs(self, inter: discord.Interaction):
        if inter.user.id not in ADMIN_IDS:
            await inter.response.send_message("❌ Réservé aux admins.", ephemeral=True)
            return

        try:
            with open("bot.log", "r", encoding="utf-8") as f:
                lines = f.readlines()
                last_lines = lines[-15:]
                content = "".join(last_lines)
            
            if not content.strip():
                await inter.response.send_message("Le fichier log est vide.", ephemeral=True)
            else:
                await inter.response.send_message(f"```log\n{content}\n```", ephemeral=True)
        except FileNotFoundError:
            await inter.response.send_message("Fichier bot.log introuvable.", ephemeral=True)
            
    @app_commands.command(name="dump-html", description="Télécharge et envoie le HTML d'une URL SWGOH.GG")
    async def dump_html(self, inter: discord.Interaction, url: str):
        if inter.user.id not in ADMIN_IDS:
            await inter.response.send_message("❌ Réservé aux admins.", ephemeral=True)
            return
            
        await inter.response.defer()
        import aiohttp
        from bs4 import BeautifulSoup
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as r:
                    html = await r.text()
            
            soup = BeautifulSoup(html, "html.parser")
            pretty_html = soup.prettify()
            
            import io
            file_obj = io.BytesIO(pretty_html.encode('utf-8'))
            file = discord.File(file_obj, filename="swgoh_round.html")
            await inter.followup.send(f"Voici le code HTML pour {url} :", file=file)
        except Exception as e:
            await inter.followup.send(f"Erreur lors du téléchargement : {e}")

    # ------------------------------------------------------------------
    # /reset-player-history — Réinitialisation des données GAC scrapées
    # ------------------------------------------------------------------
    @app_commands.command(
        name="reset-player-history",
        description="[Admin] Supprime tout l'historique GAC scrapé d'un joueur (via son ally code).",
    )
    @app_commands.describe(ally_code="L'ally code du joueur à réinitialiser (ex: 123456789)")
    @app_commands.default_permissions(administrator=True)
    async def reset_player_history(self, interaction: discord.Interaction, ally_code: str) -> None:
        await interaction.response.defer(ephemeral=True)
        clean_code = ally_code.replace("-", "").strip()
        try:
            from database.db import get_db
            async with get_db() as db:
                await db.execute("DELETE FROM gac_rounds WHERE player_code = ?", (clean_code,))
                # La suppression en cascade effacera les gac_matches associés
            
            await interaction.followup.send(
                f"✅ Historique supprimé avec succès pour l'ally code **{clean_code}**.", ephemeral=True
            )
        except Exception:
            log.exception(f"Erreur lors de la suppression de l'historique pour {clean_code}")
            await interaction.followup.send(
                "Erreur lors de la suppression.", ephemeral=True
            )


    # ------------------------------------------------------------------
    # /refresh-counters — Forcer le scraping de counters
    # ------------------------------------------------------------------
    @app_commands.command(
        name="refresh-counters",
        description="[Admin] Force la récupération des counters pour un leader spécifique.",
    )
    @app_commands.describe(
        leader_id="L'ID du personnage leader (ex: SUPREMELEADERKYLOREN)",
        membres_ids="Membres optionnels séparés par des virgules (ex: SITHROOPER,GENERALHUX)",
        format_gac="Format 5v5 ou 3v3"
    )
    @app_commands.choices(
        format_gac=[
            app_commands.Choice(name="5 contre 5", value="5v5"),
            app_commands.Choice(name="3 contre 3", value="3v3"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def refresh_counters(self, interaction: discord.Interaction, leader_id: str, format_gac: app_commands.Choice[str], membres_ids: str = None) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from services.gac_counters_scraper import GacCountersScraper
            scraper = GacCountersScraper()
            l_id = leader_id.strip().upper()
            m_ids = membres_ids.strip().upper() if membres_ids else ""
            
            await interaction.edit_original_response(content=f"⏳ Lancement du scraping forcé pour {l_id} (membres: {m_ids})...")
            await scraper.refresh_counters_for_leader(l_id, l_id, format_gac.value, d_members=m_ids)
            
            await interaction.edit_original_response(content=f"✅ Scraping terminé pour {l_id} !")
        except Exception as e:
            log.exception("Erreur lors du refresh-counters")
            await interaction.edit_original_response(content=f"❌ Erreur lors du scraping : {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
