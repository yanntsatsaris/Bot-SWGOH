"""
cogs/gac.py — Commandes slash liées à la Grande Arène (GAC)
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db
from utils.helpers import format_ally_code

log = logging.getLogger(__name__)


HELP_MESSAGE = """
🤖 **Bienvenue sur Bot-SWGOH !**

Ce bot est ton assistant personnel pour dominer la Grande Arène (GAC).
Voici les commandes principales que tu peux utiliser :

🔍 **`/gac-scout <code_allié_ennemi> <format>`**
> Scanne l'historique de ton adversaire et te génère un rapport visuel. Il va faire une **estimation** des équipes qu'il a l'habitude de poser en défense (les données peuvent être incomplètes).
> *Attention : la récupération de l'historique peut être longue (plusieurs minutes) en fonction de la ligue et du nombre de personnes dans la file d'attente. Patiente un peu !*

⚔️ **`/gac-counter <leader_ennemi> <format> [membres...]`**
> Tu bloques sur une équipe ? Cette commande va chercher les meilleurs contres possibles en tenant compte **de ton propre roster** ! Il ne te proposera que des personnages que tu possèdes.

🔄 **Boutons interactifs**
> Sur les suggestions de contres, utilise **[Victoire]** ou **[Défaite]** pour enregistrer le résultat de tes combats en base de données. Clique sur **[Autre option]** pour faire défiler les contres.

ℹ️ **`/help`**
> Affiche ce message d'aide à tout moment.
"""

class GacCog(commands.Cog, name="GAC"):
    """Commandes d'analyse de la Grande Arène."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /register — Enregistrement du compte SWGOH (PRIMORDIAL)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="register",
        description="Associe ton compte Discord à ton compte SWGOH.",
    )
    @app_commands.describe(ally_code="Ton code allié SWGOH (ex : 123-456-789)")
    async def register(self, interaction: discord.Interaction, ally_code: str) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            clean = format_ally_code(ally_code)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        discord_id = str(interaction.user.id)
        username = interaction.user.display_name

        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO players (discord_id, ally_code, username)
                VALUES (?, ?, ?)
                ON CONFLICT(discord_id) DO UPDATE SET
                    ally_code  = excluded.ally_code,
                    username   = excluded.username,
                    updated_at = datetime('now')
                """,
                (discord_id, clean, username),
            )

        success_msg = f"✅ **Compte enregistré avec succès (Code Allié : `{clean}`) !**\n\n{HELP_MESSAGE}"
        await interaction.followup.send(success_msg, ephemeral=True)

    # ------------------------------------------------------------------
    # /help — Manuel d'utilisation du bot
    # ------------------------------------------------------------------
    @app_commands.command(
        name="help",
        description="Affiche le manuel d'utilisation du bot.",
    )
    async def help_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(HELP_MESSAGE, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacCog(bot))
