"""
cogs/meta_manager.py — Gestion manuelle de la base de données méta GAC
"""
import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db

log = logging.getLogger(__name__)

class MetaManagerCog(commands.Cog, name="MetaManager"):
    """Commandes pour ajouter, modifier ou supprimer des équipes méta manuellement."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    gac_team = app_commands.Group(
        name="gac-team",
        description="Gestion manuelle des équipes méta GAC",
        default_permissions=discord.Permissions(administrator=True)
    )

    @gac_team.command(name="add", description="Ajouter une équipe méta manuellement")
    @app_commands.describe(
        leader="Nom du leader",
        members="Noms des membres séparés par une virgule (incluant le leader)",
        fmt="Format (5v5 ou 3v3)",
        league="Ligue (défaut: KYBER)",
        counters="Liste des contres (optionnel, séparés par une virgule)",
        win_rate="Taux de victoire estimé (0.0 à 1.0, optionnel)"
    )
    @app_commands.choices(fmt=[
        app_commands.Choice(name="5v5", value="5v5"),
        app_commands.Choice(name="3v3", value="3v3")
    ])
    @app_commands.choices(league=[
        app_commands.Choice(name="Kyber", value="KYBER"),
        app_commands.Choice(name="Aurodium", value="AURODIUM"),
        app_commands.Choice(name="Chromium", value="CHROMIUM"),
        app_commands.Choice(name="Bronzium", value="BRONZIUM"),
        app_commands.Choice(name="Carbonite", value="CARBONITE"),
    ])
    async def team_add(
        self,
        interaction: discord.Interaction,
        leader: str,
        members: str,
        fmt: str,
        league: str = "KYBER",
        counters: str | None = None,
        win_rate: float | None = None
    ) -> None:
        members_list = [m.strip() for m in members.split(",")]
        counters_list = [c.strip() for c in counters.split(",")] if counters else []
        
        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO meta_teams (
                    leader_name, members, counters, format, league, win_rate, usage_rate, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    leader.strip(),
                    json.dumps(members_list),
                    json.dumps(counters_list),
                    fmt,
                    league,
                    win_rate,
                    1.0,  # Valeur par défaut pour les ajouts manuels
                    "manual_override"
                )
            )
        
        embed = discord.Embed(
            title="✅ Équipe ajoutée manuellement",
            description=f"Leader: **{leader}**\nMembres: {', '.join(members_list)}\nFormat: {fmt}\nLigue: {league}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @gac_team.command(name="list", description="Lister les équipes méta ajoutées manuellement")
    async def team_list(self, interaction: discord.Interaction) -> None:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT id, leader_name, format, league FROM meta_teams WHERE source_url = 'manual_override' ORDER BY id"
            )
            rows = await cursor.fetchall()
            
        if not rows:
            await interaction.response.send_message("Aucune équipe manuelle trouvée.")
            return
            
        desc = "\n".join(f"`ID: {r['id']}` - **{r['leader_name']}** ({r['format']} - {r['league']})" for r in rows)
        embed = discord.Embed(title="Équipes Méta (Manuelles)", description=desc, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

    @gac_team.command(name="delete", description="Supprimer une équipe méta manuelle par son ID")
    @app_commands.describe(team_id="L'ID de l'équipe à supprimer (voir /gac-team list)")
    async def team_delete(self, interaction: discord.Interaction, team_id: int) -> None:
        async with get_db() as db:
            cursor = await db.execute("DELETE FROM meta_teams WHERE id = ? AND source_url = 'manual_override'", (team_id,))
            if cursor.rowcount > 0:
                await interaction.response.send_message(f"✅ L'équipe avec l'ID {team_id} a été supprimée.")
            else:
                await interaction.response.send_message(f"❌ Aucune équipe manuelle trouvée avec l'ID {team_id}.", ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MetaManagerCog(bot))
