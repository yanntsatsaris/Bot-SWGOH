"""
cogs/review_portraits.py — Commande pour valider manuellement les images associées aux unités.
"""
import logging
import discord
from discord import app_commands
from discord.ext import commands
from pathlib import Path
import os

from database.db import get_db

log = logging.getLogger(__name__)

class PortraitReviewView(discord.ui.View):
    def __init__(self, base_id: str, cog: commands.Cog):
        super().__init__(timeout=None)
        self.base_id = base_id
        self.cog = cog

    async def update_status(self, interaction: discord.Interaction, is_valid: bool):
        async with get_db() as db:
            await db.execute(
                "UPDATE units_directory SET is_image_valid = ? WHERE base_id = ?",
                (1 if is_valid else 0, self.base_id)
            )
        
        status_text = "✅ Image validée." if is_valid else "❌ Image signalée comme incorrecte."
        if not is_valid:
            log.warning(f"Image signalée comme incorrecte pour l'unité: {self.base_id}")
            
        await interaction.response.edit_message(content=f"{status_text} Chargement du suivant...", view=None, embed=None, attachments=[])
        await self.cog.send_next_review(interaction)

    @discord.ui.button(label="Valider (Correct)", style=discord.ButtonStyle.success, emoji="✅")
    async def btn_valid(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_status(interaction, True)

    @discord.ui.button(label="Incorrect", style=discord.ButtonStyle.danger, emoji="❌")
    async def btn_invalid(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_status(interaction, False)


class ReviewPortraitsCog(commands.Cog, name="ReviewPortraits"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def send_next_review(self, interaction: discord.Interaction):
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT base_id, name, image_path FROM units_directory WHERE is_image_valid IS NULL LIMIT 1"
            )
            row = await cursor.fetchone()

        if not row:
            if not interaction.response.is_done():
                await interaction.response.send_message("🎉 Toutes les images ont été vérifiées !", ephemeral=True)
            else:
                await interaction.followup.send("🎉 Toutes les images ont été vérifiées !", ephemeral=True)
            return

        base_id = row["base_id"]
        name = row["name"]
        image_path = row["image_path"]

        embed = discord.Embed(
            title="Revue des Portraits",
            description=f"Personnage : **{name}**\nID Interne : `{base_id}`",
            color=discord.Color.blue()
        )

        file = None
        if image_path and os.path.exists(image_path):
            file = discord.File(image_path, filename="portrait.png")
            embed.set_image(url="attachment://portrait.png")
            embed.add_field(name="Fichier", value=f"`{os.path.basename(image_path)}`")
        else:
            embed.add_field(name="Erreur", value="⚠️ Aucune image trouvée pour ce personnage.", inline=False)
            embed.color = discord.Color.red()

        view = PortraitReviewView(base_id, self)
        
        if not interaction.response.is_done():
            if file:
                await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            if file:
                await interaction.followup.send(embed=embed, file=file, view=view, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(
        name="review-portraits",
        description="Passe en revue les images associées aux unités pour les valider."
    )
    async def review_portraits(self, interaction: discord.Interaction) -> None:
        # On peut rajouter un check ici pour que seul un admin puisse utiliser la commande
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
            return
            
        await self.send_next_review(interaction)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReviewPortraitsCog(bot))
