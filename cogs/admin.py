import logging
import asyncio
import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

log = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Admin"):
    """Commandes d'administration du bot et tâches de fond."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.periodic_sync_gac_omicrons.start()

    def cog_unload(self) -> None:
        self.periodic_sync_gac_omicrons.cancel()

    async def cog_load(self) -> None:
        """Vérifie au démarrage si les Omicrons GAC sont initialisés en BDD."""
        asyncio.create_task(self._check_initial_gac_omicrons())

    async def _check_initial_gac_omicrons(self) -> None:
        try:
            await asyncio.sleep(5)  # Attendre que la BDD soit totalement prête
            from database.db import get_db
            async with get_db() as db:
                cursor = await db.execute("SELECT COUNT(*) as cnt FROM gac_valid_omicrons")
                row = await cursor.fetchone()
                count = row["cnt"] if row else 0

            if count == 0:
                log.info("🛡️ Table gac_valid_omicrons vide au démarrage : lancement de la synchronisation automatique...")
                from services.gac_omicron_scraper import GacOmicronScraper
                await GacOmicronScraper().scrape_and_sync()
        except Exception as e:
            log.warning("Erreur vérification initiale Omicrons GAC : %s", e)

    # ------------------------------------------------------------------
    # Tâche récurrente : Synchronisation quotidienne des Omicrons GAC
    # ------------------------------------------------------------------
    @tasks.loop(time=datetime.time(hour=4, minute=30, tzinfo=datetime.timezone.utc))  # 06h30 Paris
    async def periodic_sync_gac_omicrons(self) -> None:
        """Actualisation automatique quotidienne des Omicrons GAC."""
        log.info("⏰ [CRON] Synchronisation automatique quotidienne des Omicrons GAC...")
        try:
            from services.gac_omicron_scraper import GacOmicronScraper
            count = await GacOmicronScraper().scrape_and_sync()
            log.info("⏰ [CRON] Fin de synchronisation : %d Omicrons GAC à jour.", count)
        except Exception as e:
            log.error("⏰ [CRON] Erreur lors de la synchronisation automatique des Omicrons GAC : %s", e)

    @periodic_sync_gac_omicrons.before_loop
    async def before_periodic_sync(self) -> None:
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------------
    # /ping — Latence du bot
    # ------------------------------------------------------------------
    @app_commands.command(name="ping", description="Vérifie la latence du bot.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(
            f"Pong ! Latence : **{latency} ms**", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /sync — Resynchronisation manuelle des slash commands (admin only)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="sync",
        description="[Admin] Force la resynchronisation des slash commands.",
    )
    @app_commands.default_permissions(administrator=True)
    async def sync_commands(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(
                f"{len(synced)} commande(s) synchronisée(s) globalement.", ephemeral=True
            )
        except Exception:
            log.exception("Erreur lors de la synchronisation des commandes")
            await interaction.followup.send(
                "Erreur lors de la synchronisation.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /reset-player-history — Réinitialisation des données GAC scrapées
    # ------------------------------------------------------------------
    @app_commands.command(
        name="reset-player-history",
        description="[Admin] Supprime tout l'historique GAC extrait d'un joueur (via son ally code).",
    )
    @app_commands.describe(ally_code="L'ally code du joueur à réinitialiser (ex: 123456789)")
    @app_commands.default_permissions(administrator=True)
    async def reset_player_history(self, interaction: discord.Interaction, ally_code: str) -> None:
        await interaction.response.defer(ephemeral=True)
        clean_code = ally_code.replace("-", "").strip()
        try:
            from database.db import get_db
            async with get_db() as db:
                await db.execute("DELETE FROM gac_rounds WHERE player_code = ?", (clean_code,))
                # La suppression en cascade effacera les gac_matches associés
            
            await interaction.followup.send(
                f"✅ Historique supprimé avec succès pour l'ally code **{clean_code}**.", ephemeral=True
            )
        except Exception:
            log.exception(f"Erreur lors de la suppression de l'historique pour {clean_code}")
            await interaction.followup.send(
                "Erreur lors de la suppression.", ephemeral=True
            )


    # ------------------------------------------------------------------
    # /refresh-counters — Forcer le scraping de counters
    # ------------------------------------------------------------------
    @app_commands.command(
        name="refresh-counters",
        description="[Admin] Force la récupération des counters pour un leader spécifique.",
    )
    @app_commands.describe(
        leader_id="L'ID du personnage leader (ex: SUPREMELEADERKYLOREN)",
        membres_ids="Membres optionnels séparés par des virgules (ex: SITHROOPER,GENERALHUX)",
        format_gac="Format 5v5 ou 3v3"
    )
    @app_commands.choices(
        format_gac=[
            app_commands.Choice(name="5 contre 5", value="5v5"),
            app_commands.Choice(name="3 contre 3", value="3v3"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def refresh_counters(self, interaction: discord.Interaction, leader_id: str, format_gac: app_commands.Choice[str], membres_ids: str = None) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from services.gac_counters_scraper import GacCountersScraper
            scraper = GacCountersScraper()
            l_id = leader_id.strip().upper()
            m_ids = membres_ids.strip().upper() if membres_ids else ""
            
            await interaction.edit_original_response(content=f"⏳ Lancement de l'extraction forcée pour {l_id} (membres: {m_ids})...")
            await scraper.refresh_counters_for_leader(l_id, l_id, format_gac.value, d_members=m_ids)
            
            await interaction.edit_original_response(content=f"✅ Extraction terminée pour {l_id} !")
        except Exception as e:
            log.exception("Erreur lors du refresh-counters")
            await interaction.edit_original_response(content=f"❌ Erreur lors de l'extraction : {e}")

    @app_commands.command(name="debug-zetas", description="[Admin] Dump Rey skills from Comlink.")
    @app_commands.default_permissions(administrator=True)
    async def debug_zetas(self, interaction: discord.Interaction, ally_code: str) -> None:
        await interaction.response.defer(ephemeral=False)
        try:
            from services.comlink import get_player
            clean = str(ally_code).replace("-", "").strip()
            data = await get_player(clean)
            if not data:
                await interaction.followup.send("Profil introuvable.")
                return
            raw_roster = data.get("rosterUnit", [])
            for u in raw_roster:
                if "GLREY" in u.get("definitionId", ""):
                    import json
                    skills = u.get("skill", [])
                    out = json.dumps(skills, indent=2)
                    await interaction.followup.send(f"Rey skills:\n```json\n{out}\n```")
                    return
            await interaction.followup.send("Rey not found in roster.")
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

    # ------------------------------------------------------------------
    # /sync-game-units — Synchro manuelle des nouveaux persos et portraits
    # ------------------------------------------------------------------
    @app_commands.command(
        name="sync-game-units",
        description="[Admin] Télécharge les nouveaux personnages, portraits et alignements depuis swgoh.gg."
    )
    @app_commands.default_permissions(administrator=True)
    async def sync_game_units(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            await interaction.followup.send("⏳ **Resynchronisation manuelle en cours...** (Téléchargement des nouveaux personnages et portraits)...", ephemeral=True)
            
            from sync_all_units import sync as sync_comlink_units
            comlink_summary = await sync_comlink_units()
            
            from services.unit_names import build_name_cache
            from services.portrait_cache import build_portrait_cache
            await build_name_cache()
            await build_portrait_cache()
            
            from services.gac_omicron_scraper import GacOmicronScraper
            omi_count = await GacOmicronScraper().scrape_and_sync()

            msg = f"✅ **Resynchronisation terminée avec succès !**\n"
            msg += f"• **Total Unités (Comlink)** : {total_units}\n"
            msg += f"• 🛡️ **Omicrons GAC à jour** : {omi_count}\n"
            if new_cnt > 0:
                names_str = ", ".join(names[:10]) + ("..." if len(names) > 10 else "")
                msg += f"• 🆕 **{new_cnt} nouveau(x) portrait(s) téléchargé(s)** : `{names_str}`"
            else:
                msg += f"• ✨ **Aucun nouveau portrait manquant** (Toutes les {total_units} unités sont déjà dans le cache local !)"
                
            await interaction.followup.send(msg, ephemeral=True)


        except Exception as e:
            log.exception("Erreur lors de la synchronisation manuelle des unités : %s", e)
            await interaction.followup.send(f"❌ Erreur lors de la synchronisation : {e}", ephemeral=True)

    # ------------------------------------------------------------------
    # /sync-gac-omicrons — Synchronisation des Omicrons spécifiques GAC
    # ------------------------------------------------------------------
    @app_commands.command(
        name="sync-gac-omicrons",
        description="[Admin] Récupère et met à jour la liste des Omicrons spécifiques GAC depuis swgoh.gg."
    )
    @app_commands.default_permissions(administrator=True)
    async def sync_gac_omicrons(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from services.gac_omicron_scraper import GacOmicronScraper
            scraper = GacOmicronScraper()
            
            async def progress(msg: str):
                try:
                    await interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    pass

            count = await scraper.scrape_and_sync(progress_callback=progress)
            if count > 0:
                await interaction.followup.send(
                    f"🎉 **{count} Omicrons GAC** synchronisés avec succès depuis swgoh.gg !\n"
                    f"Seuls ces Omicrons seront désormais pris en compte et affichés sur les plans d'attaque GAC.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("⚠️ Aucun nouvel Omicron GAC n'a pu être extrait. Vérifiez les logs.", ephemeral=True)
        except Exception as e:
            log.exception("Erreur lors de la synchronisation des Omicrons GAC : %s", e)
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))

