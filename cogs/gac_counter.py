"""
cogs/gac_counter.py — Commande /gac-counter
Analyse le roster ennemi et propose les meilleures équipes pour le contrer.
Envoie le résultat sous forme d'image PNG générée dynamiquement.
"""
from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db
from services.gac_counter_engine import analyze_matchup
from services.image_generator import generate_gac_report
from services.unit_names import build_name_cache
from utils.helpers import format_ally_code

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Vue interactive (choix du format)
# ---------------------------------------------------------------------------
class CounterFormatView(discord.ui.View):
    def __init__(self, my_code: str, enemy_code: str, my_name: str, active_fmt: str = "5v5") -> None:
        super().__init__(timeout=180)
        self.my_code    = my_code
        self.enemy_code = enemy_code
        self.my_name    = my_name
        self.active_fmt = active_fmt
        self._refresh_styles()

    def _refresh_styles(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                is_active   = child.custom_id == f"counter_fmt_{self.active_fmt}"
                child.style = discord.ButtonStyle.primary if is_active else discord.ButtonStyle.secondary
                child.emoji = "✅" if is_active else None

    async def _switch(self, interaction: discord.Interaction, fmt: str) -> None:
        self.active_fmt = fmt
        self._refresh_styles()
        await interaction.response.defer()

        try:
            result = await analyze_matchup(self.my_code, self.enemy_code, fmt)
            loop   = asyncio.get_event_loop()
            file   = await loop.run_in_executor(
                None,
                generate_gac_report,
                self.my_name,
                result["enemy_name"],
                result["suggestions"],
                fmt,
            )
            embed = _summary_embed(result, fmt)
            await interaction.edit_original_response(attachments=[file], embed=embed, view=self)
        except Exception:
            log.exception("Erreur changement format /gac-counter")
            await interaction.followup.send("Erreur lors de l'analyse.", ephemeral=True)

    @discord.ui.button(label="Format 5c5", style=discord.ButtonStyle.primary,
                       custom_id="counter_fmt_5v5", emoji="✅", row=0)
    async def btn_5v5(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._switch(interaction, "5v5")

    @discord.ui.button(label="Format 3c3", style=discord.ButtonStyle.secondary,
                       custom_id="counter_fmt_3v3", row=0)
    async def btn_3v3(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._switch(interaction, "3v3")

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]


def _summary_embed(result: dict, fmt: str) -> discord.Embed:
    """Petit embed récapitulatif affiché sous l'image."""
    color = discord.Color.from_rgb(30, 120, 220) if fmt == "5v5" else discord.Color.from_rgb(180, 40, 40)
    nb    = len(result.get("suggestions", []))
    embed = discord.Embed(
        title=f"⚔️ Analyse GAC — {result.get('enemy_name', '?')}",
        description=f"**{nb}** équipe(s) méta détectée(s) en format **{fmt}**",
        color=color,
    )
    embed.set_image(url="attachment://gac_report.png")
    embed.set_footer(text="Source : SWGOH Comlink · Rapport généré dynamiquement")
    return embed


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class GacCounterCog(commands.Cog, name="GacCounter"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gac-counter",
        description="Analyse l'ennemi GAC et propose les meilleures équipes pour le contrer.",
    )
    @app_commands.describe(
        enemy_code="Code allié de l'adversaire (ex : 123-456-789)",
        my_code="Ton code allié (optionnel si déjà enregistré via /register)",
    )
    async def gac_counter(
        self,
        interaction: discord.Interaction,
        enemy_code: str,
        my_code: str | None = None,
    ) -> None:
        await interaction.response.defer()

        # --- Résolution du code allié du demandeur ---
        if my_code:
            try:
                my_clean = format_ally_code(my_code).replace("-", "")
            except ValueError as exc:
                await interaction.followup.send(str(exc), ephemeral=True)
                return
        else:
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT ally_code FROM players WHERE discord_id = ?",
                    (str(interaction.user.id),),
                )
                row = await cursor.fetchone()
            if not row:
                await interaction.followup.send(
                    "Utilise `/register` pour enregistrer ton code allié, "
                    "ou fournis-le avec le paramètre `my_code`.",
                    ephemeral=True,
                )
                return
            my_clean = row["ally_code"].replace("-", "")

        try:
            enemy_clean = format_ally_code(enemy_code).replace("-", "")
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        # --- Analyse + génération image ---
        try:
            await build_name_cache()
            result  = await analyze_matchup(my_clean, enemy_clean, "5v5")
            my_name = interaction.user.display_name

            # Génération image dans un thread (Pillow est synchrone)
            loop = asyncio.get_event_loop()
            file = await loop.run_in_executor(
                None,
                generate_gac_report,
                my_name,
                result["enemy_name"],
                result["suggestions"],
                "5v5",
            )

            embed = _summary_embed(result, "5v5")
            view  = CounterFormatView(my_clean, enemy_clean, my_name, "5v5")
            await interaction.followup.send(file=file, embed=embed, view=view)

        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception:
            log.exception("Erreur /gac-counter")
            await interaction.followup.send(
                "Erreur lors de l'analyse. Vérifie les codes alliés et réessaie.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacCounterCog(bot))
    "3v3": discord.Color.from_rgb(180, 40, 40),
}

_MEDALS   = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
_RELIC_E  = "🔴"   # relic
_GEAR_E   = "⚙️"   # gear
_OWNED_E  = "✅"
_MISSING_E = "❌"
_WARN_E   = "⚠️"


def _unit_status_line(counter: dict) -> str:
    """Formate une ligne de contre avec son statut de possession."""
    name = counter["name"]

    if not counter["owned"]:
        return f"{_MISSING_E} ~~{name}~~ *(non possédé)*"

    relic = counter.get("relic_tier", 0) or 0
    gear  = counter.get("gear_tier", 0) or 0
    ready = counter.get("ready", False)

    if relic >= 1:
        status = f"{_RELIC_E} R{relic}"
    else:
        status = f"{_GEAR_E} G{gear}"

    icon = _OWNED_E if ready else _WARN_E
    return f"{icon} **{name}** — {status}"


def _build_matchup_embeds(result: dict, my_name: str) -> list[discord.Embed]:
    """Construit la liste d'embeds pour afficher le matchup."""
    fmt          = result["fmt"]
    enemy_name   = result["enemy_name"]
    suggestions  = result["suggestions"]
    color        = _COLORS.get(fmt, discord.Color.blurple())
    label        = "5 contre 5" if fmt == "5v5" else "3 contre 3"

    embeds: list[discord.Embed] = []

    # --- Embed header ---
    header = discord.Embed(
        title=f"⚔️  Analyse GAC — {label}",
        description=(
            f"**{my_name}** vs **{enemy_name}**\n"
            f"-# {len(suggestions)} équipe(s) méta détectée(s) chez l'adversaire"
        ),
        color=color,
    )
    embeds.append(header)

    if not suggestions:
        empty = discord.Embed(
            description=(
                f"{_WARN_E} Aucune équipe méta reconnue chez **{enemy_name}** "
                f"en format {fmt}.\n"
                "L'adversaire n'a peut-être pas les unités nécessaires au niveau requis (R5+ / G13+)."
            ),
            color=color,
        )
        embeds.append(empty)
        return embeds

    # --- Un embed par équipe ennemie détectée ---
    for i, suggestion in enumerate(suggestions):
        team     = suggestion["enemy_team"]
        counters = suggestion["counters"]
        medal    = _MEDALS[i] if i < len(_MEDALS) else f"#{i+1}"

        embed = discord.Embed(
            title=f"{medal}  Équipe ennemie : {team['leader_name']}",
            color=color,
        )

        # Membres de l'équipe ennemie
        members_text = "  ·  ".join(
            f"**{m}**" if m == team["leader_name"] else m
            for m in team["members"]
        )
        embed.add_field(
            name="👥 Composition ennemie",
            value=members_text,
            inline=False,
        )

        # Contres suggérés
        if counters:
            ready_counters   = [c for c in counters if c["ready"] and c["owned"]]
            unready_counters = [c for c in counters if not c["ready"] and c["owned"]]
            missing_counters = [c for c in counters if not c["owned"]]

            lines = []
            for c in ready_counters + unready_counters + missing_counters:
                lines.append(_unit_status_line(c))

            embed.add_field(
                name=f"🛡️ Contres suggérés ({len(ready_counters)}/{len(counters)} prêts)",
                value="\n".join(lines) if lines else "_Aucun contre répertorié_",
                inline=False,
            )
        else:
            embed.add_field(
                name="🛡️ Contres suggérés",
                value="_Aucun contre dans la base de données pour cette équipe._",
                inline=False,
            )

        embeds.append(embed)

    # Limite Discord : 10 embeds max par message
    return embeds[:10]


# ---------------------------------------------------------------------------
# Vue interactive (choix du format)
# ---------------------------------------------------------------------------
class CounterFormatView(discord.ui.View):
    def __init__(self, my_code: str, enemy_code: str, my_name: str, active_fmt: str = "5v5") -> None:
        super().__init__(timeout=180)
        self.my_code    = my_code
        self.enemy_code = enemy_code
        self.my_name    = my_name
        self.active_fmt = active_fmt
        self._refresh_styles()

    def _refresh_styles(self) -> None:
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                is_active   = child.custom_id == f"counter_fmt_{self.active_fmt}"
                child.style = discord.ButtonStyle.primary if is_active else discord.ButtonStyle.secondary
                child.emoji = "✅" if is_active else None

    async def _switch(self, interaction: discord.Interaction, fmt: str) -> None:
        self.active_fmt = fmt
        self._refresh_styles()
        await interaction.response.defer()   # Peut prendre quelques secondes

        try:
            result = await analyze_matchup(self.my_code, self.enemy_code, fmt)
            embeds = _build_matchup_embeds(result, self.my_name)
            await interaction.edit_original_response(embeds=embeds, view=self)
        except Exception:
            log.exception("Erreur lors du changement de format")
            await interaction.followup.send("Erreur lors de l'analyse.", ephemeral=True)

    @discord.ui.button(label="Format 5c5", style=discord.ButtonStyle.primary,
                       custom_id="counter_fmt_5v5", emoji="✅", row=0)
    async def btn_5v5(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._switch(interaction, "5v5")

    @discord.ui.button(label="Format 3c3", style=discord.ButtonStyle.secondary,
                       custom_id="counter_fmt_3v3", row=0)
    async def btn_3v3(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self._switch(interaction, "3v3")

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class GacCounterCog(commands.Cog, name="GacCounter"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gac-counter",
        description="Analyse l'ennemi GAC et propose les meilleures équipes pour le contrer.",
    )
    @app_commands.describe(
        enemy_code="Code allié de l'adversaire (ex : 123-456-789)",
        my_code="Ton code allié (optionnel si déjà enregistré via /register)",
    )
    async def gac_counter(
        self,
        interaction: discord.Interaction,
        enemy_code: str,
        my_code: str | None = None,
    ) -> None:
        await interaction.response.defer()

        # --- Résolution du code allié du demandeur ---
        if my_code:
            try:
                my_clean = format_ally_code(my_code).replace("-", "")
            except ValueError as exc:
                await interaction.followup.send(str(exc), ephemeral=True)
                return
        else:
            # Chercher en BDD
            from database.db import get_db
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT ally_code FROM players WHERE discord_id = ?",
                    (str(interaction.user.id),),
                )
                row = await cursor.fetchone()
            if not row:
                await interaction.followup.send(
                    "Utilise `/register` pour enregistrer ton code allié, "
                    "ou fournis-le avec le paramètre `my_code`.",
                    ephemeral=True,
                )
                return
            my_clean = row["ally_code"].replace("-", "")

        try:
            enemy_clean = format_ally_code(enemy_code).replace("-", "")
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        # --- Analyse ---
        try:
            await build_name_cache()
            result  = await analyze_matchup(my_clean, enemy_clean, "5v5")
            my_name = interaction.user.display_name
            embeds  = _build_matchup_embeds(result, my_name)
            view    = CounterFormatView(my_clean, enemy_clean, my_name, "5v5")
            await interaction.followup.send(embeds=embeds, view=view)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
        except Exception:
            log.exception("Erreur /gac-counter")
            await interaction.followup.send(
                "Erreur lors de l'analyse. Vérifie les codes alliés et réessaie.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacCounterCog(bot))
