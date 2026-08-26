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
        """Vérifie au démarrage si les Omicrons GAC et les Datacrons sont initialisés en BDD."""
        asyncio.create_task(self._check_initial_gac_data())

    async def _check_initial_gac_data(self) -> None:
        try:
            await asyncio.sleep(5)  # Attendre que la BDD soit totalement prête
            from database.db import get_db
            async with get_db() as db:
                cursor = await db.execute("SELECT COUNT(*) as cnt FROM gac_valid_omicrons")
                row = await cursor.fetchone()
                omi_count = row["cnt"] if row else 0

                cursor_dtc = await db.execute("SELECT COUNT(*) as cnt FROM datacron_sets")
                row_dtc = await cursor_dtc.fetchone()
                dtc_count = row_dtc["cnt"] if row_dtc else 0

            if omi_count == 0:
                log.info("🛡️ Table gac_valid_omicrons vide au démarrage : lancement de la synchronisation Omicrons...")
                from services.gac_omicron_scraper import GacOmicronScraper
                await GacOmicronScraper().scrape_and_sync()

            if dtc_count == 0:
                log.info("🎲 Table datacron_sets vide au démarrage : lancement de la synchronisation Datacrons...")
                from services.datacron_scraper import datacron_scraper_service
                await datacron_scraper_service.scrape_and_sync()

        except Exception as e:
            log.warning("Erreur vérification initiale Omicrons/Datacrons GAC : %s", e)

    # ------------------------------------------------------------------
    # Tâche récurrente : Synchronisation hebdomadaire des Omicrons & Datacrons (Mercredi)
    # ------------------------------------------------------------------
    @tasks.loop(time=datetime.time(hour=4, minute=30, tzinfo=datetime.timezone.utc))  # 06h30 Paris
    async def periodic_sync_gac_omicrons(self) -> None:
        """Actualisation automatique hebdomadaire (Mercredi) des Omicrons GAC et des Datacrons."""
        weekday = datetime.datetime.utcnow().weekday()
        if weekday != 2:  # 2 = Mercredi
            return

        log.info("⏰ [CRON] Synchronisation automatique hebdomadaire des Omicrons et Datacrons GAC (Mercredi)...")
        try:
            from services.gac_omicron_scraper import GacOmicronScraper
            count = await GacOmicronScraper().scrape_and_sync()
            log.info("⏰ [CRON] Fin de synchronisation : %d Omicrons GAC à jour.", count)
        except Exception as e:
            log.error("⏰ [CRON] Erreur lors de la synchronisation automatique des Omicrons GAC : %s", e)

        try:
            from services.datacron_scraper import datacron_scraper_service
            dtc_count = await datacron_scraper_service.scrape_and_sync()
            log.info("⏰ [CRON] Fin de synchronisation : %d Datacrons templates à jour.", dtc_count)
        except Exception as e:
            log.error("⏰ [CRON] Erreur lors de la synchronisation automatique des Datacrons : %s", e)

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
                await db.execute("DELETE FROM gac_matches WHERE round_id IN (SELECT id FROM gac_rounds WHERE player_code = ?)", (clean_code,))
                await db.execute("DELETE FROM gac_round_teams WHERE round_id IN (SELECT id FROM gac_rounds WHERE player_code = ?)", (clean_code,))
                await db.execute("DELETE FROM gac_rounds WHERE player_code = ?", (clean_code,))
            
            await interaction.followup.send(
                f"✅ Tout l'historique (rounds et combats) a été supprimé pour l'ally code **{clean_code}**.", ephemeral=True
            )
        except Exception:
            log.exception(f"Erreur lors de la suppression de l'historique pour {clean_code}")
            await interaction.followup.send(
                "Erreur lors de la suppression.", ephemeral=True
            )

    # ------------------------------------------------------------------
    # /admin-inspect-history — Inspecter les données brutes d'historique en BDD
    # ------------------------------------------------------------------
    @app_commands.command(
        name="admin-inspect-history",
        description="[Admin] Affiche les rounds et combats enregistrés en BDD pour un joueur.",
    )
    @app_commands.describe(
        ally_code="L'ally code du joueur (ex: 646155991)",
        format_gac="Format 5v5 ou 3v3"
    )
    @app_commands.choices(
        format_gac=[
            app_commands.Choice(name="5 contre 5", value="5v5"),
            app_commands.Choice(name="3 contre 3", value="3v3"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def admin_inspect_history(self, interaction: discord.Interaction, ally_code: str, format_gac: app_commands.Choice[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        clean_code = ally_code.replace("-", "").strip()
        fmt = format_gac.value if format_gac else "5v5"
        
        from database.db import get_db
        from services.gac_scout_analyzer import GacScoutAnalyzer
        
        try:
            async with get_db() as db:
                cursor = await db.execute(
                    """
                    SELECT id, season_id, round_number, opponent_name, format, league 
                    FROM gac_rounds 
                    WHERE player_code = ? 
                    ORDER BY id DESC
                    """,
                    (clean_code,)
                )
                rounds = await cursor.fetchall()
                
                cursor_m = await db.execute(
                    """
                    SELECT m.id, m.round_id, m.is_attack, m.attacker_team, m.defender_team, m.zone, m.outcome, m.banners, r.season_id, r.round_number
                    FROM gac_matches m
                    JOIN gac_rounds r ON m.round_id = r.id
                    WHERE r.player_code = ?
                    ORDER BY m.id DESC LIMIT 40
                    """,
                    (clean_code,)
                )
                matches = await cursor_m.fetchall()

            habits = await GacScoutAnalyzer.get_defensive_habits(clean_code, fmt)
            
            lines = [f"📊 **Historique BDD pour `{clean_code}`** (Format : `{fmt}`)\n"]
            lines.append(f"• **Rounds enregistrés en BDD ({len(rounds)})** :")
            if rounds:
                for r in rounds[:12]:
                    lines.append(f"  - Round #{r['round_number']} | Saison: `{r['season_id']}` | Format: `{r['format']}` | Ligue: `{r['league']}` | Vs: {r['opponent_name']}")
            else:
                lines.append("  *(Aucun round trouvé en BDD pour ce code)*")
            
            lines.append(f"\n• **Combats enregistrés (Total : {len(matches)})** :")
            if matches:
                for m in matches[:12]:
                    side = "⚔️ Attaque" if m["is_attack"] else "🛡️ Défense"
                    try:
                        def_t = json.loads(m["defender_team"])
                        def_lead = def_t[0] if def_t else "Vide"
                        def_count = len(def_t)
                    except:
                        def_lead = m["defender_team"]
                        def_count = 0
                    lines.append(f"  - [{side}] S{m['season_id']}R{m['round_number']} | Zone: `{m['zone']}` | Leader Def: **{def_lead}** ({def_count} persos) | {m['banners']} pts | {m['outcome']}")
            else:
                lines.append("  *(Aucun combat enregistré)*")
                
            lines.append(f"\n• **Habitudes défensives synthétisées ({habits.get('total_rounds', 0)} rounds pris en compte)** :")
            for z_name, z_teams in habits.get("zones", {}).items():
                if z_teams:
                    t_names = [f"{t['leader_id']} ({t['percent']}%)" for t in z_teams[:3]]
                    lines.append(f"  - Zone `{z_name.upper()}` : {', '.join(t_names)}")
                else:
                    lines.append(f"  - Zone `{z_name.upper()}` : Aucune équipe récurrente")
                    
            report = "\n".join(lines)
            if len(report) > 1950:
                import io
                file = discord.File(io.BytesIO(report.encode("utf-8")), filename=f"history_{clean_code}.txt")
                await interaction.followup.send(content=f"📄 Rapport complet pour `{clean_code}` :", file=file, ephemeral=True)
            else:
                await interaction.followup.send(content=report, ephemeral=True)
        except Exception as err:
            log.exception("Erreur admin_inspect_history: %s", err)
            await interaction.followup.send(f"❌ Erreur lors de l'inspection : {err}", ephemeral=True)

    # ------------------------------------------------------------------
    # /admin-preview-enemy-map — Prévisualisation directe de la carte ennemie
    # ------------------------------------------------------------------
    @app_commands.command(
        name="admin-preview-enemy-map",
        description="[Admin] Prévisualise la carte de défense d'un joueur sans session utilisateur ni contres.",
    )
    @app_commands.describe(
        ally_code="L'ally code du joueur (ex: 646155991)",
        format_gac="Format 5v5 ou 3v3"
    )
    @app_commands.choices(
        format_gac=[
            app_commands.Choice(name="5 contre 5", value="5v5"),
            app_commands.Choice(name="3 contre 3", value="3v3"),
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def admin_preview_enemy_map(self, interaction: discord.Interaction, ally_code: str, format_gac: app_commands.Choice[str] = None) -> None:
        await interaction.response.defer(ephemeral=True)
        clean_code = ally_code.replace("-", "").strip()
        fmt = format_gac.value if format_gac else "5v5"

        try:
            from services.scouting import get_scout_data
            from services.scout_image import generate_scout_map
            import asyncio

            # On appelle get_scout_data sans my_ally_code pour ne pas scraper de contres ni modifier de session
            scout_data = await get_scout_data(clean_code, fmt, my_ally_code=None)

            fmt_enemy_code = f"{clean_code[:3]}-{clean_code[3:6]}-{clean_code[6:]}" if len(clean_code) == 9 else clean_code

            img_bytes = await asyncio.to_thread(
                generate_scout_map,
                scout_data["zones"],
                scout_data["quotas"],
                scout_data["league"],
                scout_data["format"],
                f"{scout_data['enemy_name']} ({fmt_enemy_code}) [Aperçu Admin]",
                scout_data["source"],
                scout_data.get("roster_index")
            )

            file = discord.File(img_bytes, filename=f"preview_{clean_code}.png")

            # Résumé texte des zones
            lines = [f"🛡️ **Aperçu des défenses pour `{scout_data['enemy_name']}` ({fmt_enemy_code})** — Format `{fmt}`\n"]
            for z_name, teams in scout_data.get("zones", {}).items():
                quota = scout_data.get("quotas", {}).get(z_name, len(teams))
                lines.append(f"**Zone {z_name.upper()} ({len(teams)}/{quota}) :**")
                for i, t in enumerate(teams):
                    ldr = t.get("leader_id") or "Vide"
                    m_count = len(t.get("members_ids", []))
                    src = t.get("source", "Prédiction")
                    lines.append(f"  • Slot #{i+1}: **{ldr}** (+{m_count} membres) — *{src}*")
                lines.append("")

            report = "\n".join(lines)
            await interaction.followup.send(content=report, file=file, ephemeral=True)
        except Exception as err:
            log.exception("Erreur admin_preview_enemy_map: %s", err)
            await interaction.followup.send(f"❌ Erreur lors de la prévisualisation : {err}", ephemeral=True)


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
            comlink_summary = await sync_comlink_units() or {}
            total_units = comlink_summary.get("total_comlink", 0)
            new_cnt = comlink_summary.get("new_portraits_count", 0)
            names = comlink_summary.get("downloaded_names", [])
            
            from services.unit_names import build_name_cache
            from services.portrait_cache import build_portrait_cache
            await build_name_cache()
            await build_portrait_cache()
            
            from services.gac_omicron_scraper import GacOmicronScraper
            omi_count = await GacOmicronScraper().scrape_and_sync()

            from services.datacron_scraper import datacron_scraper_service
            dtc_count = await datacron_scraper_service.scrape_and_sync()

            msg = f"✅ **Resynchronisation terminée avec succès !**\n"
            msg += f"• **Total Unités (Comlink)** : {total_units}\n"
            msg += f"• 🛡️ **Omicrons GAC à jour** : {omi_count}\n"
            msg += f"• 🎲 **Datacrons Templates à jour** : {dtc_count}\n"
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

    # ------------------------------------------------------------------
    # /sync-datacrons — Synchronisation des Datacrons (Sets, Variantes, Tiers)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="sync-datacrons",
        description="[Admin] Récupère et met à jour la liste des Datacrons actifs et de leurs tiers depuis swgoh.gg."
    )
    @app_commands.default_permissions(administrator=True)
    async def sync_datacrons(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            from services.datacron_scraper import datacron_scraper_service
            
            async def progress(msg: str):
                try:
                    await interaction.followup.send(msg, ephemeral=True)
                except Exception:
                    pass

            count = await datacron_scraper_service.scrape_and_sync(progress_callback=progress)
            if count > 0:
                await interaction.followup.send(
                    f"🎉 **Synchronisation des Datacrons réussie !**\n"
                    f"• Templates et variantes mis à jour : **{count}**\n"
                    f"Les Datacrons actifs et leurs bonus de tiers (L1 à L15) sont désormais en mémoire.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send("⚠️ Aucun Datacron n'a pu être synchronisé. Vérifiez les logs.", ephemeral=True)
        except Exception as e:
            log.exception("Erreur lors de la synchronisation des Datacrons : %s", e)
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

    # ------------------------------------------------------------------
    # /admin-add-alias — Ajouter une abréviation personnalisée
    # ------------------------------------------------------------------
    @app_commands.command(
        name="admin-add-alias",
        description="[Admin] Associe une abréviation (ex: SLKR, CLS...) à un personnage ou vaisseau."
    )
    @app_commands.describe(
        abreviation="L'abréviation ou acronyme (ex: SLKR, JMK, CLS, REVA...)",
        personnage="Le personnage ou vaisseau correspondant (autocomplétion disponible)"
    )
    @app_commands.default_permissions(administrator=True)
    async def admin_add_alias(self, interaction: discord.Interaction, abreviation: str, personnage: str) -> None:
        await interaction.response.defer(ephemeral=True)
        from database.db import add_unit_alias, get_character_metadata
        from services.unit_names import get_name

        clean_alias = abreviation.strip().upper()
        clean_bid = personnage.strip().upper()

        if not clean_alias or not clean_bid:
            await interaction.followup.send("❌ Abréviation et personnage obligatoires.", ephemeral=True)
            return

        try:
            await add_unit_alias(clean_alias, clean_bid)
            char_name = get_name(clean_bid) or clean_bid
            await interaction.followup.send(
                f"✅ **Abréviation enregistrée !**\n"
                f"• **Abréviation :** `⚡ [{clean_alias}]`\n"
                f"• **Personnage/Vaisseau :** **{char_name}** (`{clean_bid}`)\n\n"
                f"Cette abréviation sera désormais proposée en priorité dans tous les menus d'autocomplétion.",
                ephemeral=True
            )
        except Exception as e:
            log.exception("Erreur ajout alias : %s", e)
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

    # ------------------------------------------------------------------
    # /admin-remove-alias — Supprimer une abréviation
    # ------------------------------------------------------------------
    @app_commands.command(
        name="admin-remove-alias",
        description="[Admin] Supprime une abréviation existante."
    )
    @app_commands.describe(abreviation="L'abréviation à supprimer (ex: SLKR)")
    @app_commands.default_permissions(administrator=True)
    async def admin_remove_alias(self, interaction: discord.Interaction, abreviation: str) -> None:
        await interaction.response.defer(ephemeral=True)
        from database.db import remove_unit_alias

        clean_alias = abreviation.strip().upper()
        try:
            await remove_unit_alias(clean_alias)
            await interaction.followup.send(
                f"🗑️ Abréviation `[{clean_alias}]` supprimée avec succès.",
                ephemeral=True
            )
        except Exception as e:
            log.exception("Erreur suppression alias : %s", e)
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)

    # ------------------------------------------------------------------
    # /admin-list-aliases — Lister toutes les abréviations
    # ------------------------------------------------------------------
    @app_commands.command(
        name="admin-list-aliases",
        description="[Admin] Affiche la liste des abréviations de personnages et vaisseaux enregistrées."
    )
    @app_commands.default_permissions(administrator=True)
    async def admin_list_aliases(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        from database.db import get_all_unit_aliases
        from services.unit_names import get_name

        try:
            aliases = await get_all_unit_aliases()
            if not aliases:
                await interaction.followup.send("ℹ️ Aucune abréviation enregistrée.", ephemeral=True)
                return

            lines = []
            for a in aliases:
                u_name = a.get("name") or get_name(a["base_id"]) or a["base_id"]
                lines.append(f"• `[{a['alias']}]` ➔ **{u_name}** (`{a['base_id']}`)")

            # Découpage si trop long pour un seul message Discord (max 2000 chars)
            chunks = []
            cur_chunk = ""
            for line in lines:
                if len(cur_chunk) + len(line) + 2 > 1900:
                    chunks.append(cur_chunk)
                    cur_chunk = line + "\n"
                else:
                    cur_chunk += line + "\n"
            if cur_chunk:
                chunks.append(cur_chunk)

            await interaction.followup.send(
                f"📚 **Liste des abréviations actives ({len(aliases)}) :**\n\n{chunks[0]}",
                ephemeral=True
            )
            for ch in chunks[1:]:
                await interaction.followup.send(ch, ephemeral=True)

        except Exception as e:
            log.exception("Erreur liste alias : %s", e)
            await interaction.followup.send(f"❌ Erreur : {e}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    # Autocomplétion sur admin_add_alias
    from cogs.gac import unit_autocomplete
    AdminCog.admin_add_alias = app_commands.autocomplete(personnage=unit_autocomplete)(AdminCog.admin_add_alias)
    await bot.add_cog(AdminCog(bot))


