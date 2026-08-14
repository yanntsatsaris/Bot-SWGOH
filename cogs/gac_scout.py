import asyncio
import datetime
import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.db import get_db, save_user_defense_slot, clear_used_units
from services.unit_names import get_name
from cogs.gac import unit_autocomplete, slot_autocomplete

log = logging.getLogger(__name__)


# ─── VUE DU PLAN D'ATTAQUE INTERACTIF ──────────────────────────────────────────

class SectorOutcomeSelectView(discord.ui.View):
    def __init__(self, parent_view, zone: str, slot_index: int):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.zone = zone
        self.slot_index = slot_index

    @discord.ui.button(label="✅ Victoire (Secteur Tombé)", style=discord.ButtonStyle.success)
    async def btn_win(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        from database.db import set_sector_status, add_used_units
        await set_sector_status(str(interaction.user.id), self.zone, self.slot_index, "CLEARED")
        
        plan = await self.parent_view.get_plan(interaction.user.id)
        slot_info = None
        for s in plan.get(self.zone, []):
            if s["slot_index"] == self.slot_index:
                slot_info = s
                break
        if slot_info and slot_info.get("counter"):
            c = slot_info["counter"]
            all_atk = [c["atk_leader_id"]] + c.get("atk_members_ids", [])
            await add_used_units(str(interaction.user.id), all_atk, used_type="attack", zone=self.zone, slot_index=self.slot_index)
            
        await interaction.followup.send(f"✅ **Secteur {self.zone} #{self.slot_index} marqué comme VICTOIRE (TOMBÉ) !**\nL'équipe d'attaque a été verrouillée.", ephemeral=True)
        await self.parent_view.refresh_plan_message(interaction)

    @discord.ui.button(label="❌ Échec (Défaite)", style=discord.ButtonStyle.danger)
    async def btn_loss(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        from database.db import set_sector_status, add_used_units
        await set_sector_status(str(interaction.user.id), self.zone, self.slot_index, "FAILED")
        
        plan = await self.parent_view.get_plan(interaction.user.id)
        slot_info = None
        for s in plan.get(self.zone, []):
            if s["slot_index"] == self.slot_index:
                slot_info = s
                break
        if slot_info and slot_info.get("counter"):
            c = slot_info["counter"]
            all_atk = [c["atk_leader_id"]] + c.get("atk_members_ids", [])
            await add_used_units(str(interaction.user.id), all_atk, used_type="attack", zone=self.zone, slot_index=self.slot_index)
            
        await interaction.followup.send(f"⚠ **Secteur {self.zone} #{self.slot_index} marqué comme ÉCHEC !**\nUn contre de rattrapage a été réattribué avec tes unités disponibles restantes.", ephemeral=True)
        await self.parent_view.refresh_plan_message(interaction)


class SectorSlotSelectView(discord.ui.View):
    def __init__(self, parent_view, zone: str, action: str):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.zone = zone
        self.action = action

        teams = parent_view.enemy_zones.get(zone, [])
        options = []
        for idx in range(1, len(teams) + 1):
            curr_leader = teams[idx-1].get("leader_id", "Inconnu")
            options.append(discord.SelectOption(
                label=f"Équipe #{idx} : {get_name(curr_leader)}",
                value=str(idx)
            ))
            
        select = discord.ui.Select(placeholder=f"Choisis l'emplacement de la zone {zone}...", options=options)
        select.callback = self.on_select_slot
        self.add_item(select)

    async def on_select_slot(self, interaction: discord.Interaction):
        slot_idx = int(interaction.data["values"][0])
        if self.action == "record":
            outcome_view = SectorOutcomeSelectView(self.parent_view, self.zone, slot_idx)
            await interaction.response.send_message(f"📌 **Secteur {self.zone} #{slot_idx}** — Sélectionne le résultat de ton combat :", view=outcome_view, ephemeral=True)
        else:
            from database.db import cycle_sector_counter_offset
            new_off = await cycle_sector_counter_offset(str(interaction.user.id), self.zone, slot_idx)
            await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(f"🔄 **Secteur {self.zone} #{slot_idx}** — Passage à l'Alternative #{new_off + 1} ! Le plan global a été rééquilibré.", ephemeral=True)
            await self.parent_view.refresh_plan_message(interaction)


class SectorZoneSelectView(discord.ui.View):
    def __init__(self, parent_view, action: str):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.action = action

        options = [
            discord.SelectOption(label="Zone Nord (North)", value="North", emoji="⬆️"),
            discord.SelectOption(label="Zone Sud (South)", value="South", emoji="⬇️"),
            discord.SelectOption(label="Zone Arrière (Back)", value="Back", emoji="⬅️"),
            discord.SelectOption(label="Flotte (Fleet)", value="Fleet", emoji="🚀"),
        ]
        select = discord.ui.Select(placeholder="Choisis la zone du secteur...", options=options)
        select.callback = self.on_select_zone
        self.add_item(select)

    async def on_select_zone(self, interaction: discord.Interaction):
        zone = interaction.data["values"][0]
        slot_view = SectorSlotSelectView(self.parent_view, zone, self.action)
        await interaction.response.send_message(f"📍 **Zone {zone} sélectionnée.** Choisis l'emplacement :", view=slot_view, ephemeral=True)


class AttackPlanView(discord.ui.View):
    def __init__(
        self, 
        original_user_id: int = 0, 
        my_zones: dict = None, 
        enemy_zones: dict = None, 
        quotas: dict = None, 
        league: str = "KYBER", 
        fmt: str = "5v5", 
        my_name: str = "", 
        enemy_name: str = "", 
        my_roster_index: dict = None, 
        enemy_roster_index: dict = None
    ):
        super().__init__(timeout=None)
        self.original_user_id = original_user_id
        self.my_zones = my_zones or {}
        self.enemy_zones = enemy_zones or {}
        self.quotas = quotas or {}
        self.league = league
        self.fmt = fmt
        self.my_name = my_name
        self.enemy_name = enemy_name
        self.my_roster_index = my_roster_index or {}
        self.enemy_roster_index = enemy_roster_index or {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.original_user_id and interaction.user.id != self.original_user_id:
            await interaction.response.send_message("❌ Ces boutons ne te sont pas destinés.", ephemeral=True)
            return False
        return True

    async def get_plan(self, discord_id: int):
        from services.scouting import generate_attack_plan
        return await generate_attack_plan(str(discord_id), self.my_roster_index, self.enemy_zones, self.fmt, self.league, self.enemy_roster_index)

    async def refresh_plan_message(self, interaction: discord.Interaction):
        from services.scouting import generate_attack_plan
        from services.scout_image import generate_attack_plan_image
        
        plan = await generate_attack_plan(str(interaction.user.id), self.my_roster_index, self.enemy_zones, self.fmt, self.league, self.enemy_roster_index)
        img_buf = generate_attack_plan_image(plan, self.league, self.fmt, self.enemy_name, self.my_name, self.my_roster_index, self.enemy_roster_index)
        file_plan = discord.File(img_buf, filename="attack_plan.png")
        
        msg = (
            f"⚔️ **PLAN D'ATTAQUE GLOBAL GAC — {self.my_name} vs {self.enemy_name}**\n"
            f"Carte d'attribution mise à jour en temps réel !\n"
            f"⚠️ *Les secteurs tombés apparaissent en grisé (✔ TOMBÉ) et les contres restants sont automatiquement rééquilibrés.*"
        )
        await interaction.channel.send(content=msg, file=file_plan, view=self)

    @discord.ui.button(label="⚔️ Enregistrer Combat", style=discord.ButtonStyle.success, custom_id="btn_record_combat")
    async def btn_record_combat(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SectorZoneSelectView(self, action="record")
        await interaction.response.send_message("📌 **Enregistrement de Combat** — Sélectionne la Zone du secteur :", view=view, ephemeral=True)

    @discord.ui.button(label="🔄 Autre Option", style=discord.ButtonStyle.primary, custom_id="btn_cycle_counter")
    async def btn_cycle_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = SectorZoneSelectView(self, action="cycle")
        await interaction.response.send_message("📌 **Changement de Contre** — Sélectionne le secteur dont tu souhaites voir l'Alternative suivante :", view=view, ephemeral=True)

    @discord.ui.button(label="🔄 Actualiser Carte", style=discord.ButtonStyle.secondary, custom_id="btn_refresh_plan")
    async def btn_refresh_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await self.refresh_plan_message(interaction)
        await interaction.followup.send("✅ Carte d'attaque actualisée !", ephemeral=True)


# ─── VUE PRINCIPALE DÉFENSE & PLAN D'ATTAQUE ──────────────────────────────────

class DefenseValidationView(discord.ui.View):
    def __init__(
        self, 
        original_user_id: int = 0, 
        my_zones: dict = None, 
        enemy_zones: dict = None, 
        quotas: dict = None, 
        league: str = "KYBER", 
        fmt: str = "5v5", 
        my_name: str = "", 
        enemy_name: str = "", 
        my_roster_index: dict = None, 
        enemy_roster_index: dict = None
    ):
        super().__init__(timeout=None)
        self.original_user_id = original_user_id
        self.my_zones = my_zones or {}
        self.enemy_zones = enemy_zones or {}
        self.quotas = quotas or {}
        self.league = league
        self.fmt = fmt
        self.my_name = my_name
        self.enemy_name = enemy_name
        self.my_roster_index = my_roster_index or {}
        self.enemy_roster_index = enemy_roster_index or {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.original_user_id and interaction.user.id != self.original_user_id:
            await interaction.response.send_message("❌ Ces boutons ne te sont pas destinés.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔒 Valider ma Défense", style=discord.ButtonStyle.success, custom_id="btn_valider_def")
    async def btn_valider(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        count = 0
        for zone, teams in self.my_zones.items():
            for idx, team in enumerate(teams, 1):
                leader = team.get("leader_id")
                members = team.get("members_ids", [])
                if leader and leader not in ["USED", "None", "EMPTY"]:
                    await save_user_defense_slot(str(interaction.user.id), zone, idx, leader, members)
                    count += len([leader] + members)
                    
        for child in self.children:
            if child.custom_id == "btn_valider_def":
                child.disabled = True
            
        await interaction.followup.send(
            f"✅ **Défense validée !** ({count} personnages verrouillés en défense pour ce round et exclus de `/gac-counter`).",
            ephemeral=True
        )

    @discord.ui.button(label="⚔️ Plan d'Attaque Global", style=discord.ButtonStyle.danger, custom_id="btn_attack_plan")
    async def btn_attack_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        try:
            from services.scouting import generate_attack_plan
            from services.scout_image import generate_attack_plan_image
            
            await interaction.followup.send("⏳ **Génération du Plan d'Attaque Global en cours...** (Assignation optimale des contres secteur par secteur)...")
            
            plan = await generate_attack_plan(str(interaction.user.id), self.my_roster_index, self.enemy_zones, self.fmt, self.league, self.enemy_roster_index)
            img_buf = generate_attack_plan_image(plan, self.league, self.fmt, self.enemy_name, self.my_name, self.my_roster_index, self.enemy_roster_index)
            
            file_plan = discord.File(img_buf, filename="attack_plan.png")
            msg = (
                f"⚔️ **PLAN D'ATTAQUE GLOBAL GAC — {self.my_name} vs {self.enemy_name}**\n"
                f"Voici la carte d'attribution optimale de tes contres d'attaque pour détruire la défense de {self.enemy_name} !\n"
                f"⚠️ *Utilise les boutons ci-dessous pour enregistrer tes victoires/défaites ou changer de contre (`[🔄 Autre Option]`).*"
            )
            atk_view = AttackPlanView(
                interaction.user.id, self.my_zones, self.enemy_zones, self.quotas, self.league, self.fmt, self.my_name, self.enemy_name, self.my_roster_index, self.enemy_roster_index
            )
            await interaction.channel.send(content=msg, file=file_plan, view=atk_view)
        except Exception as e:
            log.exception("Erreur lors de la génération du plan d'attaque : %s", e)
            await interaction.followup.send(f"❌ Erreur lors de la génération du plan d'attaque : {e}")

    @discord.ui.button(label="🧹 Reset Round", style=discord.ButtonStyle.secondary, custom_id="btn_reset_round")
    async def btn_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await clear_used_units(str(interaction.user.id))
        await interaction.followup.send("✅ **Round réinitialisé !** Tous tes personnages sont de nouveau disponibles.", ephemeral=True)


# ─── COG ─────────────────────────────────────────────────────────────────────

class GACScoutCog(commands.Cog, name="GACScout"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.daily_gac_round_reset.start()

    def cog_unload(self) -> None:
        if self.daily_gac_round_reset.is_running():
            self.daily_gac_round_reset.cancel()

    @tasks.loop(time=datetime.time(hour=21, minute=0, tzinfo=datetime.timezone.utc))  # 23h00 Heure de Paris
    async def daily_gac_round_reset(self) -> None:
        """
        Réinitialise automatiquement les unités brûlées des joueurs à la fin de chaque journée de combat :
        - Vendredi 23h (Fin Combat R1)
        - Dimanche 23h (Fin Combat R2)
        - Mardi 23h (Fin Combat R3 / Fin Event)
        """
        weekday = datetime.datetime.utcnow().weekday()
        if weekday in [4, 6, 1]:
            log.info("⏰ 23h00 (Paris) — Fin de phase de combat GAC détectée. Réinitialisation des unités brûlées...")
            await clear_used_units()
            log.info("✅ Réinitialisation automatique terminée.")

    async def _send_response(
        self,
        inter: discord.Interaction,
        content: str = None,
        attachments: list[discord.File] = None,
        view: discord.ui.View = None
    ) -> None:
        """Envoie ou édite la réponse de l'interaction en toute sécurité avec fallback sur le salon textuel."""
        try:
            if inter.response.is_done():
                kwargs = {}
                if content is not None:
                    kwargs["content"] = content
                if attachments is not None:
                    kwargs["attachments"] = attachments
                if view is not None:
                    kwargs["view"] = view
                await inter.edit_original_response(**kwargs)
            else:
                kwargs = {}
                if content is not None:
                    kwargs["content"] = content
                if attachments is not None:
                    kwargs["files"] = attachments
                if view is not None:
                    kwargs["view"] = view
                await inter.response.send_message(**kwargs)
        except (discord.errors.NotFound, discord.errors.HTTPException) as e:
            log.warning("Échec réponse interaction (%s) — fallback sur le salon textuel", e)
            try:
                user_tag = f"<@{inter.user.id}> "
                full_content = f"{user_tag}{content}" if content else user_tag
                kwargs = {"content": full_content}
                if attachments:
                    kwargs["files"] = attachments
                if view:
                    kwargs["view"] = view
                await inter.channel.send(**kwargs)
            except Exception as send_err:
                log.error("Échec de l'envoi fallback sur le salon : %s", send_err)

    @app_commands.command(
        name="gac-scout",
        description="Scout le profil GAC d'un adversaire."
    )
    @app_commands.describe(
        code_ennemi="Code allié de l'ennemi (ex: 123-456-789)",
        format_gac="Le format de la GAC en cours",
        force_sync="Forcer la synchro depuis swgoh.gg (ignore le cache de la semaine)"
    )
    @app_commands.choices(
        format_gac=[
            app_commands.Choice(name="3 contre 3", value="3v3"),
            app_commands.Choice(name="5 contre 5", value="5v5"),
        ]
    )
    async def gac_scout(
        self, 
        interaction: discord.Interaction,
        code_ennemi: str,
        format_gac: app_commands.Choice[str],
        force_sync: bool = False
    ) -> None:
        """Commande principale pour scouter un ennemi."""
        try:
            await interaction.response.defer(ephemeral=False)
        except (discord.errors.NotFound, discord.errors.HTTPException) as e:
            log.warning("Impossible de defer l'interaction /gac-scout (délai 3s dépassé ou interaction inconnue) : %s", e)
        
        my_ally_code = None
        async with get_db() as db:
            cursor = await db.execute("SELECT ally_code FROM players WHERE discord_id = ?", (str(interaction.user.id),))
            row = await cursor.fetchone()
            if row:
                my_ally_code = row["ally_code"]
                
        if not my_ally_code:
            await self._send_response(interaction, content="❌ **Erreur** : Tu dois d'abord lier ton compte avec `/register <ton_ally_code>` pour utiliser le scouting ! Le bot a besoin de connaître ta ligue pour calibrer l'analyse.")
            return

        if hasattr(self.bot, "gac_scraper"):
            qsize = self.bot.gac_scraper.queue.qsize()
        else:
            qsize = 0
        if qsize > 0:
            attente_estimee = qsize * 2
            msg_attente = f"⏳ **[■□□□□□□□□□] 10%** : File d'attente : tu es en position **{qsize + 1}** (~{attente_estimee} min d'attente)..."
        else:
            msg_attente = "⏳ **[■□□□□□□□□□] 10%** : Vérification de l'historique GAC..."
            
        await self._send_response(interaction, content=msg_attente)
        
        try:
            async def on_scrape_finished(ally_code: str, inter: discord.Interaction):
                try:
                    my_ally_code = None
                    async with get_db() as db:
                        cursor = await db.execute("SELECT ally_code FROM players WHERE discord_id = ?", (str(inter.user.id),))
                        row = await cursor.fetchone()
                        if row:
                            my_ally_code = row["ally_code"]
                            
                    from services.scouting import get_scout_data
                    from services.scout_image import generate_scout_map
                    
                    async def cb(msg):
                        await self._send_response(inter, content=msg)

                    scout_data = await get_scout_data(ally_code, format_gac.value, my_ally_code, progress_callback=cb, discord_id=str(inter.user.id))
                    
                    from database.db import save_user_defense_zones
                    if "my_zones" in scout_data:
                        await save_user_defense_zones(str(inter.user.id), scout_data["my_zones"], "defense")
                    if "zones" in scout_data:
                        await save_user_defense_zones(str(inter.user.id), scout_data["zones"], "enemy_defense")

                    
                    def _build_files(sd):
                        result_files = []
                        e_img = generate_scout_map(
                            sd["zones"], sd["quotas"], sd["league"], sd["format"],
                            sd["enemy_name"] + " (Ennemi)", sd["source"],
                            sd.get("roster_index")
                        )
                        result_files.append(discord.File(e_img, filename="enemy_defense.png"))
                        if "my_zones" in sd:
                            m_img = generate_scout_map(
                                sd["my_zones"], sd["quotas"], sd["league"], sd["format"],
                                sd["my_name"] + " (Ta Défense Suggérée)",
                                "Contre-Défense Optimisée",
                                sd.get("my_roster_index"),
                                is_player=True
                            )
                            result_files.append(discord.File(m_img, filename="my_defense.png"))
                        return result_files

                    files = await asyncio.to_thread(_build_files, scout_data)

                    msg = f"<@{inter.user.id}> Voici la prédiction de la GAC pour {scout_data['enemy_name']} !\n"
                    msg += "⚠️ *Note : Les prédictions sont générées automatiquement. Utilise le bouton [🔒 Valider ma Défense] pour verrouiller tes persos posés, ou [⚔️ Plan d'Attaque Global] pour obtenir la stratégie complète d'attaque.*\n"
                    msg += "*Pour réajuster un slot spécifique sur la carte, utilise `/gac-edit-slot` avec autocomplétion des persos.*\n"
                    
                    def_view = None
                    if "my_zones" in scout_data:
                        def_view = DefenseValidationView(
                            inter.user.id,
                            scout_data["my_zones"],
                            scout_data["zones"],
                            scout_data["quotas"],
                            scout_data["league"],
                            scout_data["format"],
                            scout_data["my_name"],
                            scout_data["enemy_name"],
                            scout_data.get("my_roster_index", {}),
                            scout_data.get("roster_index", {})
                        )
                        
                    await self._send_response(inter, content=msg, attachments=files, view=def_view)
                except Exception as e:
                    log.exception("Erreur lors de la génération de l'image de scouting : %s", e)
                    await self._send_response(inter, content=f"❌ Impossible de scouter cet ennemi (pas de données ou erreur interne).")

            clean_code = code_ennemi.replace("-", "").strip()
            
            has_history = False
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT 1 FROM gac_rounds WHERE player_code = ? AND format = ? LIMIT 1", 
                    (clean_code, format_gac.value)
                )
                has_history = await cursor.fetchone() is not None

            if has_history and not force_sync:
                await self._send_response(interaction, content="⏳ Historique trouvé en base de données. Génération de la prédiction sans refaire de scan...")
                await on_scrape_finished(clean_code, interaction)
            else:
                if not hasattr(self.bot, "gac_scraper"):
                    await self._send_response(interaction, content="❌ Le service d'extraction GAC (Scan) n'est pas actif sur ce serveur.")
                    return
                    
                await self._send_response(interaction, content="⏳ **[■□□□□□□□□□] 10%** : Analyse approfondie du profil GAC de l'adversaire...")

                scraper = self.bot.gac_scraper
                if scraper.pending_tasks.get(clean_code, 0) > 0:
                    await self._send_response(
                        interaction,
                        content=f"⏳ **Un scan est déjà en cours** pour ce joueur ! Tu recevras automatiquement le résultat dès qu'il est prêt.\n"
                                f"Tu es abonné(e) à la notification — pas besoin de retaper la commande."
                    )
                    await scraper.queue_scrape(clean_code, interaction, callback=on_scrape_finished, format_filter=format_gac.value)
                else:
                    await scraper.queue_scrape(clean_code, interaction, callback=on_scrape_finished, format_filter=format_gac.value)
            
        except Exception as e:
            log.exception("Erreur lors du scouting : %s", e)
            await self._send_response(interaction, content=f"❌ Impossible d'initier le scouting : {e}")

    # ------------------------------------------------------------------
    # /gac-record-battle — Enregistrement du résultat d'un combat d'attaque
    # ------------------------------------------------------------------
    @app_commands.command(
        name="gac-record-battle",
        description="Enregistre un combat d'attaque (avec ton équipe ou celle proposée) et actualise la carte."
    )
    @app_commands.describe(
        zone="La zone du secteur attaqué",
        slot="Numéro de l'emplacement (Slot #1, Slot #2...)",
        resultat="Résultat du combat (Victoire ou Échec)",
        leader="Leader que tu as réellement utilisé (optionnel si tu as pris le contre proposé)",
        membre_2="2ème membre utilisé (optionnel)",
        membre_3="3ème membre utilisé (optionnel)",
        membre_4="4ème membre utilisé (optionnel)",
        membre_5="5ème membre utilisé (optionnel)",
    )
    @app_commands.choices(
        zone=[
            app_commands.Choice(name="Zone Nord (North)", value="North"),
            app_commands.Choice(name="Zone Sud (South)", value="South"),
            app_commands.Choice(name="Zone Arrière (Back)", value="Back"),
            app_commands.Choice(name="Flotte (Fleet)", value="Fleet"),
        ],
        resultat=[
            app_commands.Choice(name="✅ Victoire (Secteur Tombé)", value="CLEARED"),
            app_commands.Choice(name="❌ Échec (Défaite / Fail)", value="FAILED"),
        ]
    )
    @app_commands.autocomplete(
        slot=slot_autocomplete,
        leader=unit_autocomplete,
        membre_2=unit_autocomplete,
        membre_3=unit_autocomplete,
        membre_4=unit_autocomplete,
        membre_5=unit_autocomplete,
    )
    async def gac_record_battle(
        self,
        interaction: discord.Interaction,
        zone: app_commands.Choice[str],
        slot: int,
        resultat: app_commands.Choice[str],
        leader: str | None = None,
        membre_2: str | None = None,
        membre_3: str | None = None,
        membre_4: str | None = None,
        membre_5: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=False)
        discord_id = str(interaction.user.id)
        
        from database.db import set_sector_status, add_used_units, load_user_defense_zones, get_db
        from services.scouting import generate_attack_plan, _build_roster_index, get_omicron_dict, get_zeta_dict, get_ship_base_ids
        from services.scout_image import generate_attack_plan_image
        from services.unit_names import get_name
        from services.comlink import get_player
        
        # 1. Déterminer les personnages utilisés
        all_atk = []
        if leader:
            raw_members = [m for m in [membre_2, membre_3, membre_4, membre_5] if m]
            all_atk = [leader.strip().upper()] + [m.strip().upper() for m in raw_members]
            
        # 2. Récupérer les infos du round actif pour le joueur
        ally_code = None
        enemy_code = None
        league = "BRONZIUM"
        fmt = "5v5"
        enemy_name = "Ennemi"
        my_name = interaction.user.display_name
        
        async with get_db() as db:
            c = await db.execute("SELECT ally_code FROM players WHERE discord_id = ?", (discord_id,))
            r = await c.fetchone()
            if r: ally_code = r["ally_code"]
            
            c = await db.execute(
                "SELECT player_code, opponent_code, league, format, opponent_name FROM gac_rounds WHERE (player_code = ? OR player_code = ?) AND league IS NOT NULL ORDER BY id DESC LIMIT 1",
                (ally_code, discord_id) if ally_code else (discord_id, discord_id)
            )
            gr = await c.fetchone()
            if gr:
                if gr["opponent_code"]: enemy_code = gr["opponent_code"]
                if gr["league"]: league = gr["league"].upper()
                if gr["format"]: fmt = gr["format"]
                if gr["opponent_name"]: enemy_name = gr["opponent_name"]
                
        # 3. Charger le roster du joueur et de l'ennemi
        my_roster_index = {}
        enemy_roster_index = {}
        omicron_dict = await get_omicron_dict()
        zeta_dict = await get_zeta_dict()
        ship_base_ids = await get_ship_base_ids()
        
        if ally_code:
            p_profile = await get_player(ally_code)
            if p_profile:
                my_roster_index = _build_roster_index(p_profile.get("rosterUnit", []), omicron_dict, zeta_dict, ship_base_ids)
                my_name = p_profile.get("name", my_name)
                
        if enemy_code:
            e_profile = await get_player(enemy_code)
            if e_profile:
                enemy_roster_index = _build_roster_index(e_profile.get("rosterUnit", []), omicron_dict, zeta_dict, ship_base_ids)
                enemy_name = e_profile.get("name", enemy_name)

        enemy_zones = await load_user_defense_zones(discord_id, "enemy_defense")
        my_zones = await load_user_defense_zones(discord_id, "defense")
        
        # Si aucun leader personnalisé n'a été spécifié, récupérer le contre actuellement proposé pour ce slot
        if not all_atk:
            current_plan = await generate_attack_plan(discord_id, my_roster_index, enemy_zones, fmt, league, enemy_roster_index)
            for s in current_plan.get(zone.value, []):
                if s["slot_index"] == slot and s.get("counter"):
                    c_info = s["counter"]
                    all_atk = [c_info["atk_leader_id"]] + c_info.get("atk_members_ids", [])
                    break

        # 4. Enregistrer le résultat et brûler les persos
        await set_sector_status(discord_id, zone.value, slot, resultat.value)
        if all_atk:
            await add_used_units(discord_id, all_atk, used_type="attack", zone=zone.value, slot_index=slot)

        # 5. Régénérer le plan complet rééquilibré
        new_plan = await generate_attack_plan(discord_id, my_roster_index, enemy_zones, fmt, league, enemy_roster_index)
        img_buf = generate_attack_plan_image(new_plan, league, fmt, enemy_name, my_name, my_roster_index, enemy_roster_index)
        file_plan = discord.File(img_buf, filename="attack_plan.png")
        
        units_str = ", ".join(get_name(u) for u in all_atk) if all_atk else "Équipe inconnue"
        if resultat.value == "CLEARED":
            header_msg = (
                f"✅ **Secteur {zone.name} #{slot} enregistré comme VICTOIRE (TOMBÉ) !**\n"
                f"🔥 **Unités utilisées & verrouillées** : {units_str}.\n"
                f"Le secteur est désormais grisé (`✔ TOMBÉ`) et tous les autres contres ont été rééquilibrés avec tes troupes restantes."
            )
        else:
            header_msg = (
                f"⚠ **Secteur {zone.name} #{slot} enregistré comme ÉCHEC (DÉFAITE) !**\n"
                f"🔥 **Unités brûlées** : {units_str}.\n"
                f"Un nouveau contre de rattrapage (2-shot) a été calculé avec tes unités restantes disponibles."
            )
            
        atk_view = AttackPlanView(
            interaction.user.id, my_zones, enemy_zones, {}, league, fmt, my_name, enemy_name, my_roster_index, enemy_roster_index
        )
        await self._send_response(interaction, content=header_msg, attachments=[file_plan], view=atk_view)


async def setup(bot: commands.Bot) -> None:
    bot.add_view(DefenseValidationView())
    bot.add_view(AttackPlanView())
    await bot.add_cog(GACScoutCog(bot))
