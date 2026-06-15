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

# ---------------------------------------------------------------------------
# Portraits — URL directes vers les assets SWGOH.GG
# Format : https://swgoh.gg/static/img/assets/tex.avatars_<base_id>.png
# ---------------------------------------------------------------------------
_PORTRAIT_BASE = "https://swgoh.gg/static/img/assets/tex.avatars_{}.png"

CHARACTER_IDS: dict[str, str] = {
    # Sith / Empire
    "Sith Eternal Emperor":         "sithpalpatine",
    "Darth Vader":                  "darthvader",
    "Lord Vader":                   "lordvader",
    "Mara Jade":                    "marajade",
    "Darth Nihilus":                "darthnihilus",
    "Royal Guard":                  "royalguard",
    "Emperor Palpatine":            "palpatine",
    "Grand Admiral Thrawn":         "thrawn",
    # Jabba
    "Jabba the Hutt":               "jabbathehutt",
    "Boba Fett (Scion)":            "bobafettscion",
    "Krrsantan":                    "krrsantan",
    "Gamorrean Guard":              "gamorreanguard",
    "Skiff Guard":                  "skiffguard",
    # Jedi / République
    "Jedi Master Kenobi":           "jedimasterkenobi",
    "Padmé Amidala":                "padmeamidala",
    "General Skywalker":            "generalskywalker",
    "Jedi Master Luke Skywalker":   "jedimasterluke",
    "Ahsoka Tano":                  "ahsokatano",
    "Shaak Ti":                     "shaakti",
    # First Order
    "Supreme Leader Kylo Ren":      "supremeleaderkylo",
    "Hux":                          "generalhux",
    "First Order SF TIE Pilot":     "firstordersftfighter",
    # Rebels
    "Commander Luke Skywalker":     "commanderlukeskywalker",
    "Han Solo":                     "hansolo",
    "Chewbacca":                    "chewbacca",
    # Autres
    "Darth Revan":                  "darthrevan",
    "Jedi Knight Revan":            "jediknightrevan",
    "Mother Talzin":                "mothertalzin",
    "The Mandalorian (Beskar)":     "themandalorian_beskar",
    "Moff Gideon":                  "moffgideon",
}


def get_portrait_url(name: str) -> str:
    """
    Retourne l'URL du portrait d'un personnage.
    Si le nom n'est pas dans le mapping, tente une dérivation automatique.
    """
    base_id = CHARACTER_IDS.get(name)
    if not base_id:
        # Dérivation : minuscules, sans espaces ni caractères spéciaux
        base_id = (
            name.lower()
            .replace(" ", "")
            .replace("(", "").replace(")", "")
            .replace("'", "").replace("-", "")
            .replace("é", "e").replace("è", "e").replace("ê", "e")
        )
    return _PORTRAIT_BASE.format(base_id)


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
# Construction des embeds (header + 1 par équipe)
# ---------------------------------------------------------------------------
def _build_header_embed(fmt: str, nb_teams: int, is_live: bool) -> discord.Embed:
    """Embed d'en-tête affiché au-dessus des équipes."""
    label = "5 contre 5" if fmt == "5v5" else "3 contre 3"
    src   = "SWGOH.GG (live)" if is_live else "Démonstration"
    embed = discord.Embed(
        title=f"{_E['sword']}  Méta GAC — Format **{label}**",
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
    leader  = team["leader"]

    embed = discord.Embed(
        title=f"{medal}  {leader}",
        color=_COLORS[fmt],
    )

    # Portrait du leader en thumbnail
    embed.set_thumbnail(url=get_portrait_url(leader))

    # Membres (leader en gras)
    members_text = "  ·  ".join(
        f"**{m}**" if m == leader else m
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


def _build_all_embeds(fmt: str, teams: list[dict], is_live: bool) -> list[discord.Embed]:
    """Retourne : 1 embed header + 1 embed par équipe."""
    embeds = [_build_header_embed(fmt, len(teams), is_live)]

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
        embeds = _build_all_embeds(fmt, teams, is_live)

        # Mise à jour du message existant (sans nouveau message)
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

        fmt            = "5v5"
        teams, is_live = await _get_teams(fmt)
        embeds         = _build_all_embeds(fmt, teams, is_live)
        view           = GacFormatView(active_fmt=fmt)

        await interaction.followup.send(embeds=embeds, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacTestCog(bot))
