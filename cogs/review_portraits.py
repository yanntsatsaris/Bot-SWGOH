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
                "UPDATE game_characters SET is_image_valid = ? WHERE base_id = ?",
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


async def unit_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    async with get_db() as db:
        # Recherche par nom OU par base_id, insensible à la casse
        cursor = await db.execute(
            "SELECT base_id, name FROM game_characters WHERE name LIKE ? OR base_id LIKE ? LIMIT 25",
            (f"%{current}%", f"%{current}%")
        )
        rows = await cursor.fetchall()
        # On limite le nom à 100 caractères (limite Discord)
        return [
            app_commands.Choice(name=f"{row['name']} ({row['base_id']})", value=row["base_id"])
            for row in rows
        ]

async def image_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    import os
    results = []
    current_lower = current.lower()
    for directory in ["assets/portraits", "assets/vaisseaux"]:
        if os.path.exists(directory):
            for f in os.listdir(directory):
                if f.endswith(".png") and current_lower in f.lower():
                    results.append(app_commands.Choice(name=f, value=f))
                    if len(results) >= 25:
                        return results
    return results

class ReviewPortraitsCog(commands.Cog, name="ReviewPortraits"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def send_next_review(self, interaction: discord.Interaction):
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT base_id, name, image_path FROM game_characters WHERE is_image_valid IS NULL LIMIT 1"
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

    @app_commands.command(
        name="reset-portrait",
        description="Réinitialise le statut de validation d'un personnage (pour qu'il repasse en revue)."
    )
    @app_commands.describe(recherche="Nom ou ID du personnage à réinitialiser")
    @app_commands.autocomplete(recherche=unit_autocomplete)
    async def reset_portrait(self, interaction: discord.Interaction, recherche: str) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
            return
            
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT base_id, name FROM game_characters WHERE name LIKE ? OR base_id LIKE ?",
                (f"%{recherche}%", f"%{recherche}%")
            )
            rows = await cursor.fetchall()
            
            if not rows:
                await interaction.response.send_message(f"⚠️ Aucun personnage trouvé pour `{recherche}`.", ephemeral=True)
                return
                
            updated = 0
            names = []
            for row in rows:
                await db.execute("UPDATE game_characters SET is_image_valid = NULL WHERE base_id = ?", (row["base_id"],))
                names.append(row["name"])
                updated += 1
                
            await db.commit()
            
        await interaction.response.send_message(
            f"🔄 **{updated}** personnage(s) réinitialisé(s) et remis dans la file de validation :\n" + "\n".join([f"- {n}" for n in names]), 
            ephemeral=True
        )

    @app_commands.command(
        name="list-incorrect-portraits",
        description="Génère un fichier texte listant les portraits validés puis les portraits incorrects."
    )
    async def list_incorrect_portraits(self, interaction: discord.Interaction) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
            return

        async with get_db() as db:
            # Récupère les validés
            cursor_valid = await db.execute("SELECT base_id, name, image_path FROM game_characters WHERE is_image_valid = 1 ORDER BY name")
            rows_valid = await cursor_valid.fetchall()
            
            # Récupère les invalides
            cursor_invalid = await db.execute("SELECT base_id, name, image_path FROM game_characters WHERE is_image_valid = 0 ORDER BY name")
            rows_invalid = await cursor_invalid.fetchall()

        import io
        content = "=== PORTRAITS VALIDÉS (Ne pas réutiliser ces images) ===\n"
        for row in rows_valid:
            img = row['image_path'] or "Aucune image"
            content += f"- Nom   : {row['name']}\n  ID    : {row['base_id']}\n  Image : {img}\n\n"

        content += "\n" + "="*55 + "\n\n"
        content += "=== PORTRAITS INCORRECTS (À corriger) ===\n"
        for row in rows_invalid:
            img = row['image_path'] or "Aucune image"
            content += f"- Nom   : {row['name']}\n  ID    : {row['base_id']}\n  Image : {img}\n\n"

        file = discord.File(io.BytesIO(content.encode('utf-8')), filename="bilan_portraits.txt")
        await interaction.response.send_message(
            f"Voici le bilan avec **{len(rows_valid)}** validés et **{len(rows_invalid)}** incorrects.\nCela t'aidera à voir quelles images sont déjà prises !",
            file=file,
            ephemeral=True
        )

    @app_commands.command(
        name="fix-portrait",
        description="Associe manuellement une image à un personnage et la valide."
    )
    @app_commands.describe(
        base_id="L'ID exact du personnage (ex: AHSOKATANO)",
        nom_image="Le nom exact de l'image (ex: charui_ahsoka.png)"
    )
    @app_commands.autocomplete(
        base_id=unit_autocomplete,
        nom_image=image_autocomplete
    )
    async def fix_portrait(self, interaction: discord.Interaction, base_id: str, nom_image: str) -> None:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Tu dois être administrateur pour utiliser cette commande.", ephemeral=True)
            return
            
        base_id = base_id.upper()
        
        # Vérifie si l'unité existe en BDD
        async with get_db() as db:
            cursor = await db.execute("SELECT name, type FROM game_characters WHERE base_id = ?", (base_id,))
            row = await cursor.fetchone()
            
            if not row:
                await interaction.response.send_message(f"⚠️ Aucun personnage trouvé avec l'ID `{base_id}`.", ephemeral=True)
                return
                
            name = row["name"]
            unit_type = row["type"]
            
            # Heuristique pour forcer le type vaisseau si besoin
            KNOWN_SHIPS = {
                "TIEFIGHTER", "SLAVE1", "EBONHAWK", "RAZORCREST", "XANADUBLOOD", "IG2000",
                "HOUNDSTOOTH", "CAPITALEXECUTOR", "CAPITALCHIMAERA", "CAPITALSTARDESTROYER",
                "SITHFIGHTER", "TIEBOMBER", "TIEADVANCED", "TIEECHELON", "TIESILENCER",
                "MALEVOLENCE", "NEGOTIATOR", "ENDURANCE", "HOMEONE", "PROFUNDITY", "EXECUTRIX"
            }
            if base_id in KNOWN_SHIPS:
                unit_type = "ship"
            
            # Détermine le dossier en fonction du type
            folder = "vaisseaux" if unit_type == "ship" else "portraits"
            image_path = f"assets/{folder}/{nom_image}"
            
            # Mise à jour en base de données
            await db.execute(
                "UPDATE game_characters SET image_path = ?, is_image_valid = 1 WHERE base_id = ?",
                (image_path, base_id)
            )
            await db.commit()
            
        embed = discord.Embed(
            title="✅ Portrait Corrigé",
            description=f"L'image de **{name}** a été remplacée par `{nom_image}` dans le dossier `{folder}`.",
            color=discord.Color.green()
        )
        
        # On essaie d'envoyer l'image en prévisualisation si elle existe localement
        if os.path.exists(image_path):
            file = discord.File(image_path, filename=nom_image)
            embed.set_thumbnail(url=f"attachment://{nom_image}")
            await interaction.response.send_message(embed=embed, file=file, ephemeral=True)
        else:
            embed.add_field(name="⚠️ Attention", value="L'image n'a pas été trouvée sur le disque du serveur, mais le chemin a été enregistré.", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ReviewPortraitsCog(bot))
