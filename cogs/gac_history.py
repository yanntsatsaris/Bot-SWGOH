import logging
import discord
from discord import app_commands
from discord.ext import commands
from services.comlink import get_player_gac_history
from utils.helpers import format_ally_code

log = logging.getLogger(__name__)

class GacHistoryCog(commands.Cog, name="GacHistory"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gac-history",
        description="Affiche l'historique GAC d'un adversaire.",
    )
    @app_commands.describe(ally_code="Code allié de l'adversaire (ex : 123-456-789)")
    async def gac_history(self, interaction: discord.Interaction, ally_code: str) -> None:
        await interaction.response.defer()

        try:
            clean = format_ally_code(ally_code).replace("-", "")
            data = await get_player_gac_history(clean)

            # Pour le moment, on affiche les infos basiques de la saison
            # en attendant de voir si Comlink renvoie plus de détails
            name = data.get("name", "Inconnu")
            seasons = data.get("seasonStatus", [])

            embed = discord.Embed(
                title=f"Historique GAC - {name}",
                color=discord.Color.blue()
            )

            if not seasons:
                embed.description = "Aucun historique GAC trouvé pour ce joueur."
            else:
                # On affiche les 5 dernières saisons
                for s in seasons[-5:]:
                    s_id = s.get("seasonId", "Inconnu")
                    wins = s.get("wins", 0)
                    losses = s.get("losses", 0)
                    embed.add_field(
                        name=f"Saison: {s_id}",
                        value=f"Victoires: {wins} | Défaites: {losses}",
                        inline=False
                    )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            log.exception("Erreur /gac-history")
            await interaction.followup.send(f"Erreur lors de la récupération de l'historique : {e}", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacHistoryCog(bot))
