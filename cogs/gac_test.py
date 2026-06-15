"""
cogs/gac_test.py — Commande /gac_test avec interface interactive (boutons)
"""
from __future__ import annotations

import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Données de démo (utilisées si la base est vide)
# Elles simulent ce que sync_meta.py injecterait en production.
# ---------------------------------------------------------------------------
_DEMO_TEAMS: dict[str, list[dict]] = {
    "5v5": [
        {
            "leader":   "Sith Eternal Emperor",
            "members":  ["Sith Eternal Emperor", "Darth Vader", "Mara Jade", "Darth Nihilus", "Royal Guard"],
            "counters": ["Jedi Master Kenobi", "Padmé Amidala", "General Skywalker"],
            "win_rate": 0.74,
        },
        {
            "leader":   "Jabba the Hutt",
            "members":  ["Jabba the Hutt", "Boba Fett (Scion)", "Krrsantan", "Gamorrean Guard", "Skiff Guard"],
            "counters": ["Lord Vader", "Sith Eternal Emperor"],
            "win_rate": 0.71,
        },
        {
            "leader":   "Lord Vader",
            "members":  ["Lord Vader", "Mara Jade", "Darth Vader", "Royal Guard", "Darth Nihilus"],
            "counters": ["Jabba the Hutt", "Executor fleet"],
            "win_rate": 0.68,
        },
    ],
    "3v3": [
        {
            "leader":   "Sith Eternal Emperor",
            "members":  ["Sith Eternal Emperor", "Darth Vader", "Mara Jade"],
            "counters": ["Jedi Master Kenobi", "Supreme Leader Kylo Ren"],
            "win_rate": 0.77,
        },
        {
            "leader":   "Supreme Leader Kylo Ren",
            "members":  ["Supreme Leader Kylo Ren", "Hux", "First Order SF TIE Pilot"],
            "counters": ["Sith Eternal Emperor", "Jabba the Hutt"],
            "win_rate": 0.70,
        },
        {
            "leader":   "Jedi Master Kenobi",
            "members":  ["Jedi Master Kenobi", "Padmé Amidala", "General Skywalker"],
            "counters": ["Lord Vader", "Sith Eternal Emperor"],
            "win_rate": 0.66,
        },
    ],
}

# Couleurs de l'embed selon le format sélectionné
_COLORS = {
    "5v5": discord.Color.from_rgb(30, 120, 220),   # bleu
    "3v3": discord.Color.from_rgb(180, 40, 40),    # rouge
}

# Emojis décoratifs
_E = {
    "sword":    "⚔️",
    "shield":   "🛡️",
    "star":     "⭐",
    "chart":    "📊",
    "players":  "👥",
    "warning":  "⚠️",
    "check":    "✅",
    "arrow":    "➤",
}


# ---------------------------------------------------------------------------
# Helpers de formatage
# ---------------------------------------------------------------------------
def _format_team_block(team: dict) -> str:
    """Formate une équipe en bloc texte compact pour un embed Field."""
    members = " · ".join(team["members"])
    win_pct = f"{team['win_rate'] * 100:.0f}%" if team.get("win_rate") else "N/A"
    return f"{_E['star']} **{team['leader']}**\n`{members}`\n{_E['chart']} Win rate : **{win_pct}**"


def _format_counters(counters: list[str]) -> str:
    if not counters:
        return "_Aucun contre répertorié_"
    return "\n".join(f"{_E['arrow']} {c}" for c in counters[:3])


async def _load_teams_from_db(fmt: str) -> list[dict]:
    """Charge les équipes méta depuis la BDD pour le format donné."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT leader_name, members, counters, win_rate
            FROM   meta_teams
            WHERE  format = ?
            ORDER  BY win_rate DESC NULLS LAST
            LIMIT  3
            """,
            (fmt,),
        )
        rows = await cursor.fetchall()

    if not rows:
        return []

    result = []
    for row in rows:
        result.append({
            "leader":   row["leader_name"],
            "members":  json.loads(row["members"]),
            "counters": json.loads(row["counters"]) if row["counters"] else [],
            "win_rate": row["win_rate"],
        })
    return result


async def _get_teams(fmt: str) -> tuple[list[dict], bool]:
    """
    Retourne (teams, is_live_data).
    Tente la BDD d'abord, replie sur les données de démo si vide.
    """
    try:
        teams = await _load_teams_from_db(fmt)
        if teams:
            return teams, True
    except Exception:
        log.exception("Erreur lecture BDD pour le format %s", fmt)

    return _DEMO_TEAMS[fmt], False


# ---------------------------------------------------------------------------
# Construction de l'embed
# ---------------------------------------------------------------------------
def _build_embed(fmt: str, teams: list[dict], is_live: bool) -> discord.Embed:
    """Construit l'embed principal pour un format donné."""
    label = "5 contre 5" if fmt == "5v5" else "3 contre 3"
    color = _COLORS[fmt]

    embed = discord.Embed(
        title=f"{_E['sword']} Méta GAC — Format {label}",
        description=(
            f"Top **{len(teams)}** compositions méta en Grande Arène "
            f"{'*(données en direct)*' if is_live else '*(données de démonstration)*'}"
        ),
        color=color,
    )
    embed.set_thumbnail(
        url="https://swgoh.gg/static/img/assets/tex.avatars_guild_icon_heroic.png"
    )

    if not teams:
        embed.add_field(
            name=f"{_E['warning']} Aucune donnée",
            value="Lance `sync_meta.py` pour synchroniser les équipes méta.",
            inline=False,
        )
        return embed

    # --- Top équipes ---
    for i, team in enumerate(teams, start=1):
        embed.add_field(
            name=f"{_E['players']} #{i} — Composition",
            value=_format_team_block(team),
            inline=True,
        )
        embed.add_field(
            name=f"{_E['shield']} Contres",
            value=_format_counters(team["counters"]),
            inline=True,
        )
        embed.add_field(name="\u200b", value="\u200b", inline=False)  # séparateur

    data_src = "SWGOH.GG (live)" if is_live else "Données de démonstration"
    embed.set_footer(text=f"Source : {data_src} · /sync pour rafraîchir")

    return embed


# ---------------------------------------------------------------------------
# Vue interactive (boutons)
# ---------------------------------------------------------------------------
class GacFormatView(discord.ui.View):
    """
    Affiche deux boutons : Format 5c5 / Format 3c3.
    Le clic met à jour l'embed sans envoyer un nouveau message.
    """

    def __init__(self, active_fmt: str = "5v5") -> None:
        super().__init__(timeout=180)   # expire après 3 minutes d'inactivité
        self.active_fmt = active_fmt
        self._refresh_button_styles()

    def _refresh_button_styles(self) -> None:
        """Met à jour l'apparence des boutons selon le format actif."""
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == f"fmt_{self.active_fmt}":
                    child.style  = discord.ButtonStyle.primary
                    child.emoji  = "✅"
                else:
                    child.style  = discord.ButtonStyle.secondary
                    child.emoji  = None

    async def _switch_format(
        self, interaction: discord.Interaction, fmt: str
    ) -> None:
        """Logique commune aux deux boutons."""
        self.active_fmt = fmt
        self._refresh_button_styles()

        teams, is_live = await _get_teams(fmt)
        embed = _build_embed(fmt, teams, is_live)

        # Mise à jour de l'embed existant (sans nouveau message)
        await interaction.response.edit_message(embed=embed, view=self)

    # --- Bouton 5c5 ---
    @discord.ui.button(
        label="Format 5c5",
        style=discord.ButtonStyle.primary,
        custom_id="fmt_5v5",
        emoji="✅",
        row=0,
    )
    async def btn_5v5(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._switch_format(interaction, "5v5")

    # --- Bouton 3c3 ---
    @discord.ui.button(
        label="Format 3c3",
        style=discord.ButtonStyle.secondary,
        custom_id="fmt_3v3",
        row=0,
    )
    async def btn_3v3(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await self._switch_format(interaction, "3v3")

    async def on_timeout(self) -> None:
        """Désactive les boutons quand la vue expire."""
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------
class GacTestCog(commands.Cog, name="GacTest"):
    """Commande de test de l'interface GAC."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gac-test",
        description="Affiche un aperçu des équipes méta GAC avec sélection du format.",
    )
    async def gac_test(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        fmt = "5v5"
        teams, is_live = await _get_teams(fmt)
        embed = _build_embed(fmt, teams, is_live)
        view  = GacFormatView(active_fmt=fmt)

        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacTestCog(bot))
