"""
cogs/gac_test.py — Commande /gac_test avec interface interactive (boutons + portraits)
"""
from __future__ import annotations

import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db

log = logging.getLogger(__name__)

from services.portrait_cache import get_portrait_path, get_unit_name

def get_portrait_url(base_id: str) -> str:
    """
    Retourne l'URL du portrait d'un personnage via la résolution de portrait_cache.
    """
    path = get_portrait_path(base_id)
    filename = path.name
    # swgoh.gg utilise tex.avatars_ pour les images au lieu de charui_
    if filename.startswith("charui_"):
        filename = filename.replace("charui_", "tex.avatars_")
    return f"https://swgoh.gg/static/img/assets/{filename}"


# ---------------------------------------------------------------------------
# Médailles et emojis
# ---------------------------------------------------------------------------
_MEDALS = ["🥇", "🥈", "🥉"]

_E = {
    "sword":   "⚔️",
    "shield":  "🛡️",
    "chart":   "📊",
    "warning": "⚠️",
    "arrow":   "➤",
    "members": "👥",
    "counter": "🔄",
}

# ---------------------------------------------------------------------------
# Données de démo (utilisées si la base est vide)
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

# Couleurs selon le format
_COLORS = {
    "5v5": discord.Color.from_rgb(30, 120, 220),   # bleu
    "3v3": discord.Color.from_rgb(180, 40, 40),    # rouge
}


async def _load_teams_from_db(fmt: str, league: str) -> list[dict]:
    """Charge les équipes méta depuis la BDD pour le format et la ligue donnés."""
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT leader_name, members, counters, win_rate
            FROM   meta_teams
            WHERE  format = ? AND league = ?
            ORDER  BY usage_rate DESC NULLS LAST, win_rate DESC NULLS LAST
            LIMIT  3
            """,
            (fmt, league),
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


async def _get_teams(fmt: str, league: str) -> tuple[list[dict], bool]:
    """
    Retourne (teams, is_live_data).
    Tente la BDD d'abord, replie sur les données de démo si vide.
    """
    try:
        teams = await _load_teams_from_db(fmt, league)
        if teams:
            return teams, True
    except Exception:
        log.exception("Erreur lecture BDD pour le format %s", fmt)

    return _DEMO_TEAMS[fmt], False


# ---------------------------------------------------------------------------
# Construction des embeds (header + 1 par équipe)
# ---------------------------------------------------------------------------
def _build_header_embed(fmt: str, league: str, nb_teams: int, is_live: bool) -> discord.Embed:
    """Embed d'en-tête affiché au-dessus des équipes."""
    label = "5 contre 5" if fmt == "5v5" else "3 contre 3"
    src   = "SWGOH.GG (live)" if is_live else "Démonstration"
    embed = discord.Embed(
        title=f"{_E['sword']}  Méta GAC — Format **{label}** ({league.capitalize()})",
        description=(
            f"Top **{nb_teams}** compositions les plus efficaces en Grande Arène.\n"
            f"-# Source : {src}"
        ),
        color=_COLORS[fmt],
    )
    return embed


def _build_team_embed(rank: int, team: dict, fmt: str) -> discord.Embed:
    """
    Construit un embed pour une équipe.
    Le portrait du leader apparaît en thumbnail (haut droite).
    """
    medal   = _MEDALS[rank - 1] if rank <= len(_MEDALS) else f"#{rank}"
    win_pct = f"{team['win_rate'] * 100:.0f}%" if team.get("win_rate") else "N/A"
    leader_base = team["leader"]
    leader_name = get_unit_name(leader_base)

    embed = discord.Embed(
        title=f"{medal}  {leader_name}",
        color=_COLORS[fmt],
    )

    # Portrait du leader en thumbnail
    embed.set_thumbnail(url=get_portrait_url(leader_base))

    # Membres (leader en gras)
    members_text = "  ·  ".join(
        f"**{get_unit_name(m)}**" if m == leader_base else get_unit_name(m)
        for m in team["members"]
    )
    embed.add_field(
        name=f"{_E['members']}  Composition",
        value=members_text or "_Inconnue_",
        inline=False,
    )

    # Contres
    if team["counters"]:
        embed.add_field(
            name=f"{_E['counter']}  Contres",
            value="\n".join(f"{_E['arrow']}  {c}" for c in team["counters"][:4]),
            inline=True,
        )

    # Win rate
    embed.add_field(
        name=f"{_E['chart']}  Win rate",
        value=f"**{win_pct}**",
        inline=True,
    )

    return embed


def _build_all_embeds(fmt: str, league: str, teams: list[dict], is_live: bool) -> list[discord.Embed]:
    """Retourne : 1 embed header + 1 embed par équipe."""
    embeds = [_build_header_embed(fmt, league, len(teams), is_live)]

    if not teams:
        embeds.append(discord.Embed(
            description=f"{_E['warning']} Aucune donnée — lance `sync_meta.py`.",
            color=_COLORS[fmt],
        ))
        return embeds

    for i, team in enumerate(teams, start=1):
        embeds.append(_build_team_embed(i, team, fmt))

    return embeds


# ---------------------------------------------------------------------------
# Vue interactive (boutons)
# ---------------------------------------------------------------------------
class LeagueSelect(discord.ui.Select):
    """Sélecteur déroulant pour choisir la ligue GAC."""
    def __init__(self, active_league: str):
        options = [
            discord.SelectOption(label="Kyber", value="KYBER", description="Division 1", default=(active_league=="KYBER")),
            discord.SelectOption(label="Aurodium", value="AURODIUM", description="Division 2", default=(active_league=="AURODIUM")),
            discord.SelectOption(label="Chromium", value="CHROMIUM", description="Division 3", default=(active_league=="CHROMIUM")),
            discord.SelectOption(label="Bronzium", value="BRONZIUM", description="Division 4", default=(active_league=="BRONZIUM")),
            discord.SelectOption(label="Carbonite", value="CARBONITE", description="Division 5", default=(active_league=="CARBONITE")),
        ]
        super().__init__(placeholder="Choisissez une ligue...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: GacFormatView = self.view
        view.active_league = self.values[0]
        # Mettre à jour l'option par défaut
        for opt in self.options:
            opt.default = (opt.value == view.active_league)
        
        await view._refresh_content(interaction)


class GacFormatView(discord.ui.View):
    """
    Affiche deux boutons : Format 5c5 / Format 3c3 et un sélecteur de ligue.
    """

    def __init__(self, active_fmt: str = "5v5", active_league: str = "KYBER") -> None:
        super().__init__(timeout=180)   # expire après 3 minutes d'inactivité
        self.active_fmt = active_fmt
        self.active_league = active_league
        self.add_item(LeagueSelect(active_league))
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

    async def _refresh_content(self, interaction: discord.Interaction) -> None:
        """Met à jour le message existant."""
        self._refresh_button_styles()
        teams, is_live = await _get_teams(self.active_fmt, self.active_league)
        embeds = _build_all_embeds(self.active_fmt, self.active_league, teams, is_live)
        await interaction.response.edit_message(embeds=embeds, view=self)

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
        self.active_fmt = "5v5"
        await self._refresh_content(interaction)

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
        self.active_fmt = "3v3"
        await self._refresh_content(interaction)

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

        fmt            = "5v5"
        league         = "KYBER"
        teams, is_live = await _get_teams(fmt, league)
        embeds         = _build_all_embeds(fmt, league, teams, is_live)
        view           = GacFormatView(active_fmt=fmt, active_league=league)

        await interaction.followup.send(embeds=embeds, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacTestCog(bot))
