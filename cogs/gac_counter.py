import discord
from discord import app_commands
from discord.ext import commands
import logging
from database.db import get_db, record_counter_feedback
from services.gac_attack_planner import get_best_counter_with_memory
from services.unit_names import get_name
from services.comlink import get_player

log = logging.getLogger(__name__)

async def get_my_roster_index(user_id: int):
    async with get_db() as db:
        cursor = await db.execute("SELECT ally_code FROM players WHERE discord_id = ?", (str(user_id),))
        row = await cursor.fetchone()
        if not row:
            return None
        
        my_clean = row["ally_code"]
        my_profile = await get_player(my_clean)
        if not my_profile:
            return None
            
        roster = {}
        for unit in my_profile.get("rosterUnit", []):
            def_id = unit.get("definitionId", "")
            base_id = def_id.split(":")[0] if ":" in def_id else def_id
            raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
            relic_tier = max(0, raw_relic - 2) if raw_relic >= 2 else 0
            roster[base_id] = {
                "base_id": base_id,
                "gear_tier": unit.get("currentTier", 0),
                "relic_tier": relic_tier,
                "rarity": unit.get("currentRarity", 0),
            }
        return roster

class CounterSuggestionView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction, suggestions: list, def_leader: str, format_type: str, current_index: int = 0, excluded_chars: set = None):
        super().__init__(timeout=600) # 10 minutes timeout
        self.original_interaction = interaction
        self.suggestions = suggestions
        self.def_leader = def_leader
        self.format_type = format_type
        self.current_index = current_index
        self.excluded_chars = excluded_chars or set()
        
    async def get_current_suggestion_embed(self) -> discord.Embed:
        if self.current_index >= len(self.suggestions):
            return discord.Embed(title="❌ Plus de contres disponibles", description="Aucun autre contre n'a été trouvé pour cette équipe avec votre roster actuel.", color=discord.Color.red())
            
        sugg = self.suggestions[self.current_index]
        atk_leader = sugg["atk_leader_id"]
        atk_members = sugg.get("atk_members_ids", [])
        all_chars = [atk_leader] + atk_members
        names = [get_name(cid) for cid in all_chars]
        team_str = "\n".join([f"• **{name}**" for name in names])
        
        embed = discord.Embed(
            title=f"🎯 Contre Suggéré #{self.current_index + 1}",
            description=f"Voici le contre optimal proposé pour battre **{get_name(self.def_leader)}** :",
            color=discord.Color.blue()
        )
        embed.add_field(name="Équipe Proposée", value=team_str, inline=False)
        embed.add_field(name="Score Composite", value=f"{sugg.get('composite_score', 0):.2f}", inline=True)
        embed.add_field(name="Taux de Victoire (Global)", value=f"{sugg.get('win_pct', 0)}%", inline=True)
        
        if "missing" in sugg and sugg["missing"]:
            missing_names = [get_name(m) for m in sugg["missing"]]
            embed.add_field(name="⚠️ Personnages Manquants / Faibles", value=", ".join(missing_names), inline=False)
            
        embed.set_footer(text="Que s'est-il passé lors de l'attaque ?")
        return embed
        
    @discord.ui.button(label="Victoire", style=discord.ButtonStyle.success, emoji="✅")
    async def btn_victoire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_feedback(interaction, True)
        
    @discord.ui.button(label="Défaite", style=discord.ButtonStyle.danger, emoji="❌")
    async def btn_defaite(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_feedback(interaction, False)

    @discord.ui.button(label="Autre Option", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def btn_autre(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index += 1
        await self.update_message(interaction)
        
    async def _handle_feedback(self, interaction: discord.Interaction, won: bool):
        sugg = self.suggestions[self.current_index]
        atk_leader = sugg["atk_leader_id"]
        atk_members = sugg.get("atk_members_ids", [])
        
        await record_counter_feedback(self.def_leader, [], atk_leader, atk_members, self.format_type, "win" if won else "loss", str(interaction.user.id))
        
        # Désactiver les boutons
        for child in self.children:
            child.disabled = True
            
        status = "✅ Victoire enregistrée" if won else "❌ Défaite enregistrée"
        embed = await self.get_current_suggestion_embed()
        embed.color = discord.Color.green() if won else discord.Color.red()
        embed.set_footer(text=f"Résultat : {status}")
        
        await interaction.response.edit_message(embed=embed, view=self)

    async def update_message(self, interaction: discord.Interaction):
        embed = await self.get_current_suggestion_embed()
        if self.current_index >= len(self.suggestions):
            for child in self.children:
                child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

async def unit_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current = current.lower()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT base_id, name FROM game_characters WHERE name LIKE ? OR base_id LIKE ? LIMIT 25",
            (f"%{current}%", f"%{current}%")
        )
        rows = await cursor.fetchall()
        
    return [
        app_commands.Choice(name=f"{row['name']} ({row['base_id']})", value=row["base_id"])
        for row in rows
    ]

class GACCounterCog(commands.Cog, name="GACCounter"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gac-counter",
        description="Trouve le meilleur contre pour une équipe ennemie."
    )
    @app_commands.describe(
        leader_ennemi="Le leader de l'équipe ennemie",
        membres_ennemi="Les membres (optionnel, IDs séparés par des virgules)",
        format_gac="Le format (3v3 ou 5v5)"
    )
    @app_commands.choices(
        format_gac=[
            app_commands.Choice(name="3 contre 3", value="3v3"),
            app_commands.Choice(name="5 contre 5", value="5v5"),
        ]
    )
    @app_commands.autocomplete(leader_ennemi=unit_autocomplete)
    async def gac_counter(
        self,
        interaction: discord.Interaction,
        leader_ennemi: str,
        format_gac: app_commands.Choice[str],
        membres_ennemi: str = None
    ) -> None:
        await interaction.response.defer()
        
        leader_clean = leader_ennemi.strip().upper()
        members_list = [m.strip().upper() for m in membres_ennemi.split(",")] if membres_ennemi else []
        
        my_roster_index = await get_my_roster_index(interaction.user.id)
        if not my_roster_index:
            await interaction.followup.send("❌ Impossible de trouver ton profil. As-tu utilisé `/register` ?")
            return
            
        counters = await get_best_counter_with_memory(leader_clean, members_list, format_gac.value, my_roster_index)
        
        if not counters:
            await interaction.followup.send(f"❌ Aucun contre n'a été trouvé pour **{get_name(leader_clean)}** dans ce format.")
            return
            
        view = CounterSuggestionView(interaction, counters, leader_clean, format_gac.value)
        embed = await view.get_current_suggestion_embed()
        
        await interaction.followup.send(embed=embed, view=view)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GACCounterCog(bot))
