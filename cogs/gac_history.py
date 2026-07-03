"""
cogs/gac_history.py — Enregistrement des actions GAC
"""
import logging
import json
import discord
from discord import app_commands
from discord.ext import commands
from database.db import get_db

log = logging.getLogger(__name__)

class GacHistoryCog(commands.Cog, name="GacHistory"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gac-log",
        description="Enregistre un combat GAC (Attaque ou Défense).",
    )
    @app_commands.describe(
        action="Type d'action (Attaque ou Défense)",
        enemy_name="Nom de l'adversaire",
        my_leader="Ton leader utilisé",
        enemy_leader="Le leader adverse",
        result="Résultat (WIN, LOSS, DRAW)",
        banners="Nombre de bannières obtenues"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Attaque", value="attack"),
        app_commands.Choice(name="Défense", value="defense"),
    ])
    @app_commands.choices(result=[
        app_commands.Choice(name="Victoire", value="WIN"),
        app_commands.Choice(name="Défaite", value="LOSS"),
        app_commands.Choice(name="Match nul", value="DRAW"),
    ])
    async def gac_log(
        self,
        interaction: discord.Interaction,
        action: str,
        enemy_name: str,
        my_leader: str,
        enemy_leader: str,
        result: str,
        banners: int = 0
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        discord_id = str(interaction.user.id)
        is_attack = 1 if action == "attack" else 0

        async with get_db() as db:
            # 1. Trouver le player_id
            cursor = await db.execute("SELECT id FROM players WHERE discord_id = ?", (discord_id,))
            row = await cursor.fetchone()
            if not row:
                await interaction.followup.send("Tu dois d'abord t'enregistrer avec `/register`.", ephemeral=True)
                return

            player_id = row["id"]

            # 2. Insertion
            await db.execute(
                """
                INSERT INTO gac_history
                (player_id, season_id, enemy_name, my_team_leader, my_team_members,
                 enemy_team_leader, enemy_team_members, is_attack, banners, result)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (player_id, "S_CURRENT", enemy_name, my_leader, "[]", enemy_leader, "[]", is_attack, banners, result)
            )

        await interaction.followup.send(f"✅ Combat contre **{enemy_name}** enregistré !", ephemeral=True)

    @app_commands.command(
        name="gac-history-fetch",
        description="Extrait l'historique GAC d'un joueur depuis swgoh.gg (Processus long : ~20s).",
    )
    @app_commands.describe(
        ally_code="Code allié du joueur (ex: 123456789 ou 123-456-789)"
    )
    async def gac_history_fetch(
        self,
        interaction: discord.Interaction,
        ally_code: str
    ) -> None:
        await interaction.response.defer()
        
        if ally_code.startswith("http"):
            ally_code_clean = ally_code.strip()
        else:
            ally_code_clean = ally_code.replace("-", "").strip()
        
        # On vérifie que le scraper est bien initialisé
        if not hasattr(self.bot, "gac_scraper"):
            await interaction.followup.send("❌ Le service d'extraction GAC (Scraper) n'est pas actif sur ce serveur.")
            return
            
        await self.bot.gac_scraper.queue_scrape(ally_code_clean, interaction)
        
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacHistoryCog(bot))
