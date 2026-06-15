"""
cogs/gac.py — Commandes slash liées à la Grande Arène (GAC)
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db
from services.gac_analysis import get_player_gac_stats
from utils.helpers import format_ally_code

log = logging.getLogger(__name__)


class GacCog(commands.Cog, name="GAC"):
    """Commandes d'analyse de la Grande Arène."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /register — Enregistrement du compte SWGOH
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

        await interaction.followup.send(
            f"Compte enregistré avec le code allié `{clean}`.", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /gac-stats — Statistiques GAC d'un joueur
    # ------------------------------------------------------------------
    @app_commands.command(
        name="gac-stats",
        description="Affiche les statistiques GAC d'un joueur SWGOH.",
    )
    @app_commands.describe(ally_code="Code allié du joueur (ex : 123-456-789)")
    async def gac_stats(
        self, interaction: discord.Interaction, ally_code: str
    ) -> None:
        await interaction.response.defer()

        try:
            clean = format_ally_code(ally_code)
            stats = await get_player_gac_stats(clean)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception:
            log.exception("Erreur lors de la récupération des stats GAC pour %s", ally_code)
            await interaction.followup.send(
                "Impossible de récupérer les statistiques. Vérifie le code allié et réessaie.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Statistiques GAC — {stats['username']}",
            color=discord.Color.gold(),
        )

        fmt = stats.get("format", "?").upper()

        embed.add_field(name="🏆 Ligue",        value=stats.get("league", "N/A"),          inline=True)
        embed.add_field(name="📊 Division",      value=stats.get("division", "N/A"),         inline=True)
        embed.add_field(name="🎯 Classement",    value=f"#{stats['rank']}" if stats.get("rank") else "N/A", inline=True)
        embed.add_field(name="✅ Victoires",      value=str(stats.get("wins", 0)),            inline=True)
        embed.add_field(name="❌ Défaites",       value=str(stats.get("losses", 0)),           inline=True)
        embed.add_field(name="⭐ Points saison",  value=str(stats.get("season_points", 0)),   inline=True)
        embed.add_field(name="⚔️ Format",         value=fmt,                                  inline=True)
        embed.add_field(name="🛡️ Arène rank",    value=f"#{stats['arena_rank']}" if stats.get("arena_rank") else "N/A", inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        arena_squad = stats.get("arena_squad", [])
        if arena_squad:
            leader = arena_squad[0]
            members_text = "  ·  ".join(
                f"**{m}**" if m == leader else m for m in arena_squad
            )
            embed.add_field(name="👥 Équipe Arène", value=members_text, inline=False)

        embed.set_footer(text="Source : SWGOH Comlink")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacCog(bot))
