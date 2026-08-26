"""
cogs/gac_fleet.py -- Commande /gac-fleet & Tâche Hebdomadaire (Mercredi)
Gestion de la tier list de vaisseaux et des ship counters en GAC.

Sous-commandes:
  /gac-fleet tier          -- Affiche la Tier List Fleet (Attaque ou Defense, par Ligue)
  /gac-fleet counter       -- Counters pour un vaisseau mere ennemi (filtre par roster)
  /gac-fleet sync-tier     -- (Admin) Force la mise a jour de la tier list
  /gac-fleet sync-counters -- (Admin) Force le scraping des ship counters pour 1 capital
  /gac-fleet sync-all      -- (Admin) Lance le scraping de TOUS les vaisseaux amiraux
"""
import logging
import asyncio
import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.db import (
    get_db,
    get_fleet_tier_list,
    get_ship_counters,
)
from services.gac_ship_counters_scraper import GacShipCountersScraper, ALL_CAPITAL_IDS
from services.unit_names import get_name
from services.comlink import get_player

log = logging.getLogger(__name__)

_ship_scraper = GacShipCountersScraper()

# ─── Mapping capital_id -> nom affiche ────────────────────────────────────────
CAPITAL_DISPLAY_NAMES = {
    "CAPITALLEVIATHAN":   "Leviathan",
    "CAPITALPROFUNDITY":  "Profundity",
    "CAPITALEXECUTOR":    "Executor",
    "CAPITALNEGOTIATOR":  "Negotiator",
    "CAPITALHOMEONE":     "Home One",
    "CAPITALCHIMAERA":    "Chimaera",
    "CAPITALFINALIZER":   "Finalizer",
    "CAPITALMACE":        "Executrix",
    "CAPITALMALEVOLENCE": "Malevolence",
    "CAPITALRADDUS":      "Raddus",
    "CAPITALVENATOR":     "Venator",
}

# Ordre des tiers pour affichage
TIER_ORDER = {"S": 0, "A": 1, "B": 2, "C": 3, "D": 4}
TIER_EMOJIS = {"S": "🏆", "A": "⭐", "B": "🔵", "C": "🟡", "D": "⬜"}

LEAGUE_CHOICES = [
    app_commands.Choice(name="Kyber", value="kyber"),
    app_commands.Choice(name="Aurodium", value="aurodium"),
    app_commands.Choice(name="Chromium", value="chromium"),
    app_commands.Choice(name="Bronzium", value="bronzium"),
    app_commands.Choice(name="Carbonite", value="carbonite"),
]

SIDE_CHOICES = [
    app_commands.Choice(name="Attaque (Offense)", value="offense"),
    app_commands.Choice(name="Defense", value="defense"),
]


# ─── Autocomplete capital ships ───────────────────────────────────────────────

async def capital_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current_lower = current.lower()
    choices = []
    for cid, name in CAPITAL_DISPLAY_NAMES.items():
        if current_lower in name.lower() or current_lower in cid.lower():
            choices.append(app_commands.Choice(name=name, value=cid))
    return choices[:25]


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_player_ships(discord_id: str) -> dict:
    """Retourne le roster de vaisseaux du joueur {base_id: {rarity, level}} ou {}."""
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT ally_code FROM players WHERE discord_id = ?",
            (str(discord_id),)
        )
        row = await cursor.fetchone()
    if not row:
        return {}

    try:
        profile = await get_player(row["ally_code"].replace("-", ""))
    except Exception as e:
        log.warning(f"[gac-fleet] Impossible de recuperer le roster: {e}")
        return {}

    if not profile:
        return {}

    ships = {}
    for unit in profile.get("rosterUnit", []):
        def_id = unit.get("definitionId", "")
        base_id = def_id.split(":")[0] if ":" in def_id else def_id
        combat_type = unit.get("combatType")
        # combatType=2 = vaisseau
        if combat_type == 2 and base_id:
            ships[base_id] = {
                "base_id": base_id,
                "rarity": unit.get("currentRarity", 0),
                "level": unit.get("currentLevel", 0),
            }
    return ships


def _filter_counters_by_roster(counters: list[dict], player_ships: dict) -> list[dict]:
    """Filtre les counters pour ne garder que ceux que le joueur peut utiliser."""
    if not player_ships:
        return counters

    filtered = []
    for c in counters:
        atk_capital = c.get("atk_capital", "")
        atk_members = c.get("atk_members_ids", [])
        all_ships = [atk_capital] + atk_members
        if all(s in player_ships for s in all_ships if s):
            filtered.append(c)
    return filtered


def _format_ship_name(base_id: str) -> str:
    """Retourne le nom affiche d'un vaisseau."""
    if base_id in CAPITAL_DISPLAY_NAMES:
        return CAPITAL_DISPLAY_NAMES[base_id]
    name = get_name(base_id)
    return name if name else base_id


def _build_tier_embed(entries: list[dict], side: str, league: str) -> discord.Embed:
    """Construit un embed Discord pour la tier list fleet."""
    side_str = "Attaque ⚔️" if side == "offense" else "Défense 🛡️"
    league_str = league.capitalize()

    embed = discord.Embed(
        title=f"🚀 Tier List Fleet — {side_str} ({league_str})",
        description="Source: swgoh.gg/tier-list/fleet/",
        color=0x1a1aff if side == "offense" else 0xff6600,
    )

    if not entries:
        embed.description = "❌ Aucune donnée disponible. Utilisez `/gac-fleet sync-tier` pour mettre à jour."
        return embed

    tiers: dict[str, list[dict]] = {}
    for e in entries:
        t = e.get("tier", "?")
        tiers.setdefault(t, []).append(e)

    for tier_letter in ["S", "A", "B", "C", "D"]:
        if tier_letter not in tiers:
            continue
        tier_entries = tiers[tier_letter]
        emoji = TIER_EMOJIS.get(tier_letter, "•")

        lines = []
        for e in tier_entries[:6]:
            cap = _format_ship_name(e.get("capital_ship", ""))
            members = e.get("members_ids", [])
            members_str = " + ".join(_format_ship_name(m) for m in members[:3]) if members else "?"
            
            stat_parts = []
            if side == "offense" and e.get("win_pct") is not None:
                stat_parts.append(f"{e['win_pct']:.1f}% Win")
            elif side == "defense" and e.get("hold_pct") is not None:
                stat_parts.append(f"{e['hold_pct']:.1f}% Hold")
            if e.get("elo"):
                stat_parts.append(f"Elo {e['elo']}")
            stat_str = f" ·  `{'  '.join(stat_parts)}`" if stat_parts else ""

            lines.append(f"**{cap}** + {members_str}{stat_str}")

        embed.add_field(
            name=f"{emoji} Tier {tier_letter}",
            value="\n".join(lines) if lines else "—",
            inline=False,
        )

    embed.set_footer(text="💡 Utilisez /gac-fleet sync-tier pour mettre à jour les données")
    return embed


def _build_counter_embed(
    def_capital_id: str,
    counters: list[dict],
    player_ships: dict,
    filtered: bool = False,
) -> discord.Embed:
    """Construit un embed Discord pour les ship counters."""
    cap_name = _format_ship_name(def_capital_id)

    embed = discord.Embed(
        title=f"⚔️ Ship Counters — {cap_name}",
        description=f"Meilleurs contres contre **{cap_name}**" + (" (filtré par ton roster)" if filtered else ""),
        color=0x00ccff,
    )

    if not counters:
        embed.description = (
            "❌ Aucun counter disponible pour ce vaisseau.\n"
            "Utilise `/gac-fleet sync-counters` ou `/gac-fleet sync-all` pour lancer le scraping."
        )
        return embed

    for i, c in enumerate(counters[:8], 1):
        atk_cap = _format_ship_name(c.get("atk_capital", ""))
        atk_members = c.get("atk_members_ids", [])
        members_str = " + ".join(_format_ship_name(m) for m in atk_members[:6]) if atk_members else "?"

        all_ships = [c.get("atk_capital", "")] + atk_members
        has_all = all(s in player_ships for s in all_ships if s) if player_ships else None
        has_icon = "✅ " if has_all else ("❌ " if has_all is False else "")

        stat_parts = []
        if c.get("win_pct") is not None:
            stat_parts.append(f"{c['win_pct']:.1f}% Win")
        if c.get("seen"):
            stat_parts.append(f"{c['seen']} battles")
        if c.get("avg_banners"):
            stat_parts.append(f"{c['avg_banners']:.1f}⭐")
        stat_str = f"  ·  `{'  '.join(stat_parts)}`" if stat_parts else ""

        embed.add_field(
            name=f"{has_icon}#{i} — {atk_cap}",
            value=f"+ {members_str}{stat_str}",
            inline=False,
        )

    embed.set_footer(text="✅ = vaisseaux disponibles dans ton roster  |  ❌ = vaisseaux manquants")
    return embed


# ─── COG ──────────────────────────────────────────────────────────────────────

class GacFleet(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.weekly_fleet_update.start()

    def cog_unload(self):
        self.weekly_fleet_update.cancel()

    # ─── Tâche Hebdomadaire (Mercredi soir ~23h30 Paris) ──────────────────────
    @tasks.loop(time=datetime.time(hour=21, minute=30, tzinfo=datetime.timezone.utc))
    async def weekly_fleet_update(self):
        """
        Scrape automatiquement tous les counters de vaisseaux et la tier list
        tous les Mercredis soir (jour d'inscription GAC / début de round).
        """
        weekday = datetime.datetime.utcnow().weekday()
        if weekday != 2:  # 2 = Mercredi
            return

        log.info("[FleetTask] 🚀 Démarrage du scraping hebdomadaire des flottes (Mercredi)...")
        try:
            # 1. Tier list Kyber Attaque + Défense
            await _ship_scraper.refresh_fleet_tier_list(side="offense", league="kyber")
            await _ship_scraper.refresh_fleet_tier_list(side="defense", league="kyber")

            # 2. Counters pour tous les 11 vaisseaux amiraux
            results = await _ship_scraper.refresh_all_ship_counters()
            log.info(f"[FleetTask] ✅ Scraping hebdomadaire terminé avec succès : {results}")
        except Exception as e:
            log.exception(f"[FleetTask] ❌ Erreur lors du scraping hebdomadaire des flottes: {e}")

    @weekly_fleet_update.before_loop
    async def before_weekly_fleet_update(self):
        await self.bot.wait_until_ready()

    fleet = app_commands.Group(
        name="gac-fleet",
        description="Tier List Fleet et Ship Counters pour le GAC"
    )

    @fleet.command(name="tier", description="Affiche la Tier List Fleet (attaque ou defense)")
    @app_commands.describe(
        side="Cote de la tier list",
        league="Ligue GAC",
    )
    @app_commands.choices(side=SIDE_CHOICES, league=LEAGUE_CHOICES)
    async def fleet_tier(
        self,
        interaction: discord.Interaction,
        side: str = "offense",
        league: str = "kyber",
    ):
        await interaction.response.defer(thinking=True)

        entries = await get_fleet_tier_list(side=side, league=league, format_type="5v5")

        if not entries:
            embed = discord.Embed(
                title="🚀 Tier List Fleet — Pas de données",
                description=(
                    f"Aucune donnée disponible pour **{side}/{league}**.\n\n"
                    "Lance une mise a jour avec :\n"
                    f"`/gac-fleet sync-tier side:{side} league:{league}`"
                ),
                color=0xff4444,
            )
            await interaction.followup.send(embed=embed)
            return

        embed = _build_tier_embed(entries, side, league)
        await interaction.followup.send(embed=embed)

    @fleet.command(name="counter", description="Affiche les meilleurs contres pour un vaisseau mere ennemi")
    @app_commands.describe(capital="Vaisseau mere ennemi")
    @app_commands.autocomplete(capital=capital_autocomplete)
    async def fleet_counter(
        self,
        interaction: discord.Interaction,
        capital: str,
    ):
        await interaction.response.defer(thinking=True)

        player_ships = await _get_player_ships(str(interaction.user.id))
        has_roster = bool(player_ships)

        counters = await get_ship_counters(capital.upper())

        if not counters:
            cap_name = _format_ship_name(capital.upper())
            embed = discord.Embed(
                title=f"⚔️ Ship Counters — {cap_name}",
                description=(
                    f"Aucun counter disponible pour **{cap_name}**.\n\n"
                    f"Lance le scraping avec :\n"
                    f"`/gac-fleet sync-counters capital:{capital}` ou `/gac-fleet sync-all`"
                ),
                color=0xff4444,
            )
            await interaction.followup.send(embed=embed)
            return

        filtered_counters = _filter_counters_by_roster(counters, player_ships) if has_roster else counters
        if not filtered_counters and has_roster:
            filtered_counters = counters
            filtered = False
        else:
            filtered = has_roster

        embed = _build_counter_embed(capital.upper(), filtered_counters, player_ships, filtered=filtered)

        if not has_roster:
            embed.set_footer(text="💡 Enregistre ton compte avec /register pour filtrer par ton roster")

        await interaction.followup.send(embed=embed)

    @fleet.command(name="sync-tier", description="(Admin) Met a jour la tier list fleet depuis swgoh.gg")
    @app_commands.describe(
        side="Cote a scraper",
        league="Ligue a scraper",
    )
    @app_commands.choices(side=SIDE_CHOICES, league=LEAGUE_CHOICES)
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_tier(
        self,
        interaction: discord.Interaction,
        side: str = "offense",
        league: str = "kyber",
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)

        msg = await interaction.followup.send(
            f"⏳ Scraping de la tier list fleet **{side}/{league}** en cours...",
            ephemeral=True,
            wait=True,
        )

        count = await _ship_scraper.refresh_fleet_tier_list(side=side, league=league)

        if count < 0:
            await msg.edit(content=f"❌ Erreur lors du scraping de la tier list {side}/{league}. Voir les logs.")
        elif count == 0:
            await msg.edit(content=f"⚠️ Scraping termine mais aucune equipe trouvee pour {side}/{league}.")
        else:
            await msg.edit(content=f"✅ **{count}** equipes fleet sauvegardees pour {side}/{league} !")

    @fleet.command(name="sync-counters", description="(Admin) Scrape les ship counters pour un capital")
    @app_commands.describe(capital="Capital ship defensif a scraper")
    @app_commands.autocomplete(capital=capital_autocomplete)
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_counters(
        self,
        interaction: discord.Interaction,
        capital: str,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)

        cap_name = _format_ship_name(capital.upper())
        msg = await interaction.followup.send(
            f"⏳ Scraping des counters pour **{cap_name}** en cours...",
            ephemeral=True,
            wait=True,
        )

        count = await _ship_scraper.refresh_ship_counters(capital.upper())

        if count < 0:
            await msg.edit(content=f"❌ Erreur lors du scraping des counters pour {cap_name}. Voir les logs.")
        elif count == 0:
            await msg.edit(content=f"⚠️ Scraping termine mais aucun counter trouve pour {cap_name}.")
        else:
            await msg.edit(content=f"✅ **{count}** counters sauvegardes pour **{cap_name}** !")

    @fleet.command(name="sync-all", description="(Admin) Scrape TOUS les 11 vaisseaux amiraux en arrière-plan")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_all(
        self,
        interaction: discord.Interaction,
    ):
        await interaction.response.defer(thinking=True, ephemeral=True)

        msg = await interaction.followup.send(
            "⏳ Lancement du scraping de **tous les 11 vaisseaux amiraux** en arrière-plan (~2-3 minutes)...\nTu peux continuer à utiliser le bot.",
            ephemeral=True,
            wait=True,
        )

        # Lancer en arrière-plan
        async def _run_all():
            try:
                # Tier list
                await _ship_scraper.refresh_fleet_tier_list(side="offense", league="kyber")
                await _ship_scraper.refresh_fleet_tier_list(side="defense", league="kyber")
                # Tous les ship counters
                res = await _ship_scraper.refresh_all_ship_counters()
                total = sum(v for v in res.values() if v > 0)
                await interaction.followup.send(
                    f"✅ **Scraping Flotte terminé !**\nTotal de **{total}** counters sauvegardés pour les 11 vaisseaux amiraux.",
                    ephemeral=True,
                )
            except Exception as e:
                log.exception(f"[sync-all] Erreur: {e}")
                await interaction.followup.send(
                    f"❌ Une erreur est survenue pendant le scraping complet des flottes: {e}",
                    ephemeral=True,
                )

        asyncio.create_task(_run_all())

    @sync_tier.error
    @sync_counters.error
    @sync_all.error
    async def admin_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ Commande reservee aux administrateurs.", ephemeral=True)
        else:
            log.exception(f"[gac-fleet] Erreur: {error}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Une erreur est survenue.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(GacFleet(bot))
