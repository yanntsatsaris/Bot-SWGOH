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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
