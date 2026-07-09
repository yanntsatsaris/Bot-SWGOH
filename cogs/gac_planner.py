import discord
from discord.ext import commands
from discord import app_commands
import logging

from services.gac_planner import GacPlanner
from services.unit_names import get_name

logger = logging.getLogger("gac_planner_cog")

class GacPlannerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.planner = GacPlanner()

    @app_commands.command(
        name="gac-defense-plan",
        description="Génère une proposition de défenses optimisées pour votre roster."
    )
    @app_commands.describe(
        ally_code="Votre Ally Code (ex: 123456789)",
        format_type="Format GAC (5v5 ou 3v3)",
        min_relic="Niveau de Relique minimum requis pour le leader (ex: 0 pour G13 minimum)",
        min_gear="Niveau d'équipement minimum pour l'équipe (ex: 12)"
    )
    @app_commands.choices(
        format_type=[
            app_commands.Choice(name="5v5", value="5v5"),
            app_commands.Choice(name="3v3", value="3v3")
        ]
    )
    async def gac_defense_plan(
        self, 
        interaction: discord.Interaction, 
        ally_code: str, 
        format_type: str = "5v5",
        min_relic: int = -1,
        min_gear: int = 12
    ):
        await interaction.response.defer()
        
        suggestions = await self.planner.get_team_suggestions(
            ally_code=ally_code, 
            format_type=format_type, 
            mode="defense",
            min_relic=min_relic,
            min_gear=min_gear
        )

        if not suggestions:
            await interaction.followup.send("❌ Impossible de générer des suggestions ou aucune équipe meta trouvée dans votre roster avec ces critères.")
            return

        embed = discord.Embed(
            title=f"🛡️ Proposition de Défense GAC ({format_type})",
            description=f"Basé sur les Meta Squads SWGOH.gg et le roster de **{ally_code}**\n*(Critères: Leader Min Relic: {'N/A' if min_relic < 0 else min_relic} | Équipe Min Gear: {min_gear})*",
            color=discord.Color.brand_green()
        )

        for i, sugg in enumerate(suggestions[:10], 1):
            leader_name = get_name(sugg["leader"])
            valid_names = [get_name(u) for u in sugg["valid_members"] if u != sugg["leader"]]
            missing_names = [get_name(u) for u in sugg["missing_units"]]
            
            squad_text = f"**Leader : {leader_name}**\n"
            if valid_names:
                squad_text += f"✅ Présents : {', '.join(valid_names)}\n"
            if missing_names:
                squad_text += f"❌ Manquants/Faibles : {', '.join(missing_names)}\n"
                
            stats_text = f"🛡️ Hold: {sugg['hold_percent']}% | 👀 Vu: {sugg['seen']}"
            
            embed.add_field(name=f"Équipe #{i}", value=f"{squad_text}{stats_text}", inline=False)

        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="gac-offense-plan",
        description="Génère une proposition des meilleures équipes d'attaque pour votre roster."
    )
    @app_commands.describe(
        ally_code="Votre Ally Code (ex: 123456789)",
        format_type="Format GAC (5v5 ou 3v3)",
        min_relic="Niveau de Relique minimum requis pour le leader (ex: 0 pour G13 minimum)",
        min_gear="Niveau d'équipement minimum pour l'équipe (ex: 12)"
    )
    @app_commands.choices(
        format_type=[
            app_commands.Choice(name="5v5", value="5v5"),
            app_commands.Choice(name="3v3", value="3v3")
        ]
    )
    async def gac_offense_plan(
        self, 
        interaction: discord.Interaction, 
        ally_code: str, 
        format_type: str = "5v5",
        min_relic: int = -1,
        min_gear: int = 12
    ):
        await interaction.response.defer()
        
        suggestions = await self.planner.get_team_suggestions(
            ally_code=ally_code, 
            format_type=format_type, 
            mode="attack",
            min_relic=min_relic,
            min_gear=min_gear
        )

        if not suggestions:
            await interaction.followup.send("❌ Impossible de générer des suggestions ou aucune équipe meta trouvée dans votre roster avec ces critères.")
            return

        embed = discord.Embed(
            title=f"⚔️ Proposition d'Attaque GAC ({format_type})",
            description=f"Basé sur les Meta Squads SWGOH.gg et le roster de **{ally_code}**\n*(Critères: Leader Min Relic: {'N/A' if min_relic < 0 else min_relic} | Équipe Min Gear: {min_gear})*",
            color=discord.Color.brand_red()
        )

        for i, sugg in enumerate(suggestions[:10], 1):
            leader_name = get_name(sugg["leader"])
            valid_names = [get_name(u) for u in sugg["valid_members"] if u != sugg["leader"]]
            missing_names = [get_name(u) for u in sugg["missing_units"]]
            
            squad_text = f"**Leader : {leader_name}**\n"
            if valid_names:
                squad_text += f"✅ Présents : {', '.join(valid_names)}\n"
            if missing_names:
                squad_text += f"❌ Manquants/Faibles : {', '.join(missing_names)}\n"
                
            stats_text = f"🚩 Bannières: {sugg['avg_banners']} | 👀 Vu: {sugg['seen']}"
            
            embed.add_field(name=f"Équipe #{i}", value=f"{squad_text}{stats_text}", inline=False)

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(GacPlannerCog(bot))
