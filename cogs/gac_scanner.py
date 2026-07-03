"""
cogs/gac_scanner.py
Commandes Discord pour lancer le scan GAC et l'auto-report des combats.
"""
import discord
from discord.ext import commands, tasks
from discord import app_commands
import logging
import json

from services.gac_scanner import run_full_gac_scan, run_top50_scan
from database.db import get_db

log = logging.getLogger(__name__)

class GacScannerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_top50.start()   # Cron quotidien Top 50

    def cog_unload(self):
        self.daily_top50.cancel()

    # ─── CRON QUOTIDIEN ────────────────────────────────────────────────────

    import datetime
    @tasks.loop(time=datetime.time(hour=12, minute=0, tzinfo=datetime.timezone.utc))
    async def daily_top50(self):
        """Scan automatique du Top 50 chaque jour à midi UTC."""
        log.info("[CRON] Démarrage du scan Top 50 quotidien...")
        result = await run_top50_scan()
        log.info(f"[CRON] Top 50 terminé : {result}")

    @daily_top50.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    # ─── COMMANDE ADMIN : Lancer le scan complet ───────────────────────────

    @app_commands.command(
        name="gac-scan-start",
        description="[ADMIN] Lance le scan complet de tous les brackets GAC."
    )
    @app_commands.default_permissions(administrator=True)
    async def gac_scan_start(
        self,
        interaction: discord.Interaction,
        leagues: str = "ALL",  # "ALL" ou "KYBER,AURODIUM"
    ):
        await interaction.response.defer(ephemeral=True)

        target_leagues = None
        if leagues.upper() != "ALL":
            target_leagues = [l.strip().upper() for l in leagues.split(",")]

        embed = discord.Embed(
            title="🚀 Scan GAC démarré",
            description=(
                f"Ligues : `{leagues}`\n"
                "Durée estimée : **3-4 heures** pour un scan complet.\n"
                "Le bot continue à fonctionner normalement pendant le scan."
            ),
            color=0x00D4FF
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        # Lancer en background (ne bloque pas Discord)
        self.bot.loop.create_task(run_full_gac_scan(
            concurrency=30,
            leagues=target_leagues,
        ))

    # ─── COMMANDE ADMIN : Scan Top 50 manuel ───────────────────────────────

    @app_commands.command(
        name="gac-scan-top50",
        description="[ADMIN] Scan manuel du Top 50 toutes ligues/divisions."
    )
    @app_commands.default_permissions(administrator=True)
    async def gac_scan_top50(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await run_top50_scan()
        embed = discord.Embed(
            title="✅ Scan Top 50 terminé",
            description=(
                f"**{result['success']}** / **{result['total_players']}** rosters stockés\n"
                f"Durée : {result['duration_sec']}s"
            ),
            color=0x00FF99
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /gac-log-round : Auto-report d'un round ───────────────────────────

    @app_commands.command(
        name="gac-log-round",
        description="Enregistre le résultat d'un round de GAC."
    )
    @app_commands.describe(
        season   = "Numéro de la saison (ex: 42)",
        round_nb = "Numéro du round (1, 2 ou 3)",
        result   = "Résultat du round",
        my_banners  = "Tes banners",
        opp_banners = "Banners de l'adversaire",
        opp_code    = "Ally code de l'adversaire (optionnel)",
        format      = "Format du GAC",
    )
    @app_commands.choices(result=[
        app_commands.Choice(name="✅ Victoire", value="win"),
        app_commands.Choice(name="❌ Défaite",  value="loss"),
        app_commands.Choice(name="🤝 Égalité",  value="draw"),
    ])
    @app_commands.choices(format=[
        app_commands.Choice(name="5v5", value="5v5"),
        app_commands.Choice(name="3v3", value="3v3"),
    ])
    async def gac_log_round(
        self,
        interaction: discord.Interaction,
        season:      int,
        round_nb:    app_commands.Range[int, 1, 3],
        result:      str,
        my_banners:  int,
        opp_banners: int,
        format:      str = "5v5",
        opp_code:    str = "",
    ):
        await interaction.response.defer(ephemeral=True)

        season_id = f"CHAMPIONSHIPS_GRAND_ARENA_GA2_EVENT_SEASON_{season}"

        async with get_db() as db:
            cursor = await db.execute("""
                INSERT INTO gac_rounds
                    (season_id, round_number, player_code, opponent_code,
                     result, player_banners, opponent_banners, format)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                season_id,
                round_nb,
                str(interaction.user.id),
                opp_code or None,
                result,
                my_banners,
                opp_banners,
                format,
            ))
            round_id = cursor.lastrowid
            await db.commit()

        emoji = {"win": "✅", "loss": "❌", "draw": "🤝"}[result]
        embed = discord.Embed(
            title=f"{emoji} Round {round_nb} enregistré — Saison {season}",
            description=(
                f"**Résultat :** {result.upper()}\n"
                f"**Banners :** {my_banners} vs {opp_banners}\n"
                f"**Round ID :** `{round_id}`\n\n"
                "Utilise `/gac-log-team` pour ajouter les équipes de ce round."
            ),
            color=0x00FF99 if result == "win" else 0xFF4444
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ─── /gac-log-team : Ajouter une équipe à un round ─────────────────────

    @app_commands.command(
        name="gac-log-team",
        description="Ajoute une équipe à un round GAC déjà enregistré."
    )
    @app_commands.describe(
        round_id  = "ID du round (fourni par /gac-log-round)",
        side      = "Attaque ou Défense",
        owner     = "Ton équipe ou celle de l'adversaire",
        leader    = "ID du leader (ex: LORDVADER)",
        members   = "Membres séparés par virgule (ex: MOFF_GIDEON,RANGE_TROOPER)",
        zone      = "Zone (North/South/Back/Fleet)",
        banners   = "Banners obtenus avec cette équipe",
        success   = "L'équipe a-t-elle tenu/gagné ?",
    )
    @app_commands.choices(side=[
        app_commands.Choice(name="⚔️ Attaque",  value="offense"),
        app_commands.Choice(name="🛡️ Défense", value="defense"),
    ])
    @app_commands.choices(owner=[
        app_commands.Choice(name="Moi",          value="player"),
        app_commands.Choice(name="Adversaire",   value="opponent"),
    ])
    async def gac_log_team(
        self,
        interaction: discord.Interaction,
        round_id:   int,
        side:       str,
        owner:      str,
        leader:     str,
        members:    str,
        zone:       str = "",
        banners:    int = 0,
        success:    bool = True,
    ):
        await interaction.response.defer(ephemeral=True)

        members_list = [m.strip().upper() for m in members.split(",") if m.strip()]
        members_json = json.dumps(members_list)

        async with get_db() as db:
            await db.execute("""
                INSERT INTO gac_round_teams
                    (round_id, side, owner, zone, leader_id, members_ids, banners, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                round_id,
                side,
                owner,
                zone or None,
                leader.upper(),
                members_json,
                banners,
                1 if success else 0,
            ))
            await db.commit()

        embed = discord.Embed(
            title="✅ Équipe enregistrée",
            description=(
                f"**Round :** `{round_id}` | **Zone :** {zone or 'N/A'}\n"
                f"**Leader :** `{leader.upper()}`\n"
                f"**Membres :** {', '.join(f'`{m}`' for m in members_list)}\n"
                f"**Banners :** {banners} | **Succès :** {'✅' if success else '❌'}"
            ),
            color=0x00FF99
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(GacScannerCog(bot))
