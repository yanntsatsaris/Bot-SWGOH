import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import datetime

from services.gac_meta_squads_scraper import GacMetaSquadsScraper
from database.db import get_db

logger = logging.getLogger("gac_global_meta")

class GacGlobalMetaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.scraper = GacMetaSquadsScraper(bot)
        self.daily_meta_update.start()

    def cog_unload(self):
        self.daily_meta_update.cancel()

    @tasks.loop(time=datetime.time(hour=3, minute=0)) # Exécution tous les jours à 3h00 du matin
    async def daily_meta_update(self):
        """
        Tâche de fond quotidienne pour mettre à jour la Meta GAC globale (Attack & Defense pour 5v5 et 3v3).
        """
        logger.info("Démarrage de la mise à jour quotidienne de la Meta GAC...")
        
        # 5v5 Attack
        await self.scraper.fetch_and_parse(format_type="5v5", mode="attack")
        # 5v5 Defense
        await self.scraper.fetch_and_parse(format_type="5v5", mode="defense")
        # 3v3 Attack
        await self.scraper.fetch_and_parse(format_type="3v3", mode="attack")
        # 3v3 Defense
        await self.scraper.fetch_and_parse(format_type="3v3", mode="defense")
        
        logger.info("Mise à jour quotidienne de la Meta GAC terminée.")

    @daily_meta_update.before_loop
    async def before_daily_meta_update(self):
        await self.bot.wait_until_ready()

    @app_commands.command(
        name="update-meta-squads",
        description="[ADMIN] Force la mise à jour immédiate de la Meta GAC globale."
    )
    @app_commands.default_permissions(administrator=True)
    async def update_meta_squads(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(ephemeral=True, content="🔄 Lancement de la mise à jour de la Meta GAC (ça va prendre environ 1 à 2 minutes)...")
        
        # 5v5 Attack
        await self.scraper.fetch_and_parse(format_type="5v5", mode="attack")
        # 5v5 Defense
        await self.scraper.fetch_and_parse(format_type="5v5", mode="defense")
        # 3v3 Attack
        await self.scraper.fetch_and_parse(format_type="3v3", mode="attack")
        # 3v3 Defense
        await self.scraper.fetch_and_parse(format_type="3v3", mode="defense")
        
        await interaction.followup.send(ephemeral=True, content="✅ Mise à jour des Meta Squads (5v5 et 3v3, 3 dernières saisons) terminée avec succès !")

    @app_commands.command(
        name="gac-meta-squads",
        description="Affiche les meilleures équipes de la meta GAC actuelle."
    )
    @app_commands.choices(
        format_type=[
            app_commands.Choice(name="5v5", value="5v5"),
            app_commands.Choice(name="3v3", value="3v3")
        ],
        mode=[
            app_commands.Choice(name="Attaque", value="attack"),
            app_commands.Choice(name="Défense", value="defense")
        ]
    )
    async def gac_meta_squads(self, interaction: discord.Interaction, format_type: str = "5v5", mode: str = "defense"):
        await interaction.response.defer()
        
        async with get_db() as db:
            async with db.execute(
                "SELECT squad_units, seen, hold_percent, avg_banners FROM gac_global_meta WHERE format = ? AND mode = ? ORDER BY hold_percent DESC LIMIT 10",
                (format_type, mode)
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await interaction.followup.send("❌ Aucune donnée Meta trouvée. La synchronisation quotidienne n'a peut-être pas encore tourné.")
            return

        embed = discord.Embed(
            title=f"🏆 Top 10 Meta Squads - {format_type} {mode.capitalize()}",
            description=f"Basé sur les données globales de SWGOH.gg",
            color=discord.Color.blue()
        )

        for i, row in enumerate(rows, 1):
            import json
            units = json.loads(row["squad_units"])
            leader = units[0] if units else "Inconnu"
            team_size = len(units)
            
            # Simple affichage texte pour l'instant (les portraits viendront plus tard avec l'image generation)
            squad_str = f"**Leader:** {leader} (+ {team_size-1} alliés)"
            stats_str = f"👀 Vu: {row['seen']} | 🛡️ Hold: {row['hold_percent']}% | 🚩 Bannières: {row['avg_banners']}"
            
            embed.add_field(name=f"#{i}", value=f"{squad_str}\n{stats_str}", inline=False)

        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(GacGlobalMetaCog(bot))
