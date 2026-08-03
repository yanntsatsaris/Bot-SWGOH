import datetime
import logging
import discord
from discord import app_commands
from discord.ext import commands, tasks

from database.db import get_db, save_user_defense_slot, clear_used_units
from services.unit_names import get_name

log = logging.getLogger(__name__)

# ─── MODAL D'ÉDITION D'UN SLOT DE DÉFENSE ────────────────────────────────────

class SlotEditModal(discord.ui.Modal):
    def __init__(self, parent_view, zone: str, slot_index: int, current_leader: str = "", current_members: str = ""):
        super().__init__(title=f"Éditer {zone} — Équipe #{slot_index}")
        self.parent_view = parent_view
        self.zone = zone
        self.slot_index = slot_index

        self.leader_input = discord.ui.TextInput(
            label="ID / Nom du Leader",
            placeholder="Ex: GLREY, JEDIMASTERKENOBI...",
            default=current_leader,
            required=True,
            max_length=50
        )
        self.members_input = discord.ui.TextInput(
            label="Membres (séparés par des virgules)",
            placeholder="Ex: BAZEMALBUS, CAPTAINDROGAN...",
            default=current_members,
            required=False,
            max_length=200
        )
        self.add_item(self.leader_input)
        self.add_item(self.members_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        leader_raw = self.leader_input.value.strip().upper()
        members_raw = [m.strip().upper() for m in self.members_input.value.split(",") if m.strip()]
        
        zone_teams = self.parent_view.my_zones.get(self.zone, [])
        while len(zone_teams) < self.slot_index:
            zone_teams.append({"leader_id": "EMPTY", "members_ids": [], "source": "custom"})
            
        zone_teams[self.slot_index - 1] = {
            "leader_id": leader_raw,
            "members_ids": members_raw,
            "source": "custom"
        }
        self.parent_view.my_zones[self.zone] = zone_teams
        
        await save_user_defense_slot(str(interaction.user.id), self.zone, self.slot_index, leader_raw, members_raw)
        
        from services.scout_image import generate_scout_map
        m_img = generate_scout_map(
            self.parent_view.my_zones, self.parent_view.quotas, self.parent_view.league, self.parent_view.fmt,
            self.parent_view.my_name + " (Défense Personnalisée)",
            "Défense Modifiée",
            self.parent_view.my_roster_index
        )
        file_updated = discord.File(m_img, filename="my_defense.png")
        
        await interaction.followup.send(
            f"✅ **Emplacement mis à jour !** ({self.zone} — Équipe #{self.slot_index} : **{get_name(leader_raw)}**).\n"
            f"La carte de défense et les exclusions de contres ont été réactualisées.",
            file=file_updated,
            ephemeral=True
        )


# ─── VUES SELECT POUR L'ÉDITEUR DE SLOT ──────────────────────────────────────

class SlotSelectView(discord.ui.View):
    def __init__(self, parent_view, zone: str):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.zone = zone

        teams = parent_view.my_zones.get(zone, [])
        max_slots = max(len(teams), parent_view.quotas.get(zone, 1))
        
        options = []
        for idx in range(1, max_slots + 1):
            curr_leader = teams[idx-1].get("leader_id", "Aucun") if idx <= len(teams) else "Aucun"
            options.append(discord.SelectOption(
                label=f"Équipe #{idx} : {get_name(curr_leader)}",
                value=str(idx)
            ))
            
        select = discord.ui.Select(placeholder=f"Choisis l'équipe de la zone {zone} à modifier...", options=options)
        select.callback = self.on_select_slot
        self.add_item(select)

    async def on_select_slot(self, interaction: discord.Interaction):
        slot_idx = int(interaction.data["values"][0])
        teams = self.parent_view.my_zones.get(self.zone, [])
        curr_leader = teams[slot_idx-1].get("leader_id", "") if slot_idx <= len(teams) else ""
        curr_members = ",".join(teams[slot_idx-1].get("members_ids", [])) if slot_idx <= len(teams) else ""
        
        modal = SlotEditModal(self.parent_view, self.zone, slot_idx, curr_leader, curr_members)
        await interaction.response.send_modal(modal)


class ZoneSelectView(discord.ui.View):
    def __init__(self, parent_view):
        super().__init__(timeout=60)
        self.parent_view = parent_view

        options = [
            discord.SelectOption(label="Zone Nord (North)", value="North", emoji="⬆️"),
            discord.SelectOption(label="Zone Sud (South)", value="South", emoji="⬇️"),
            discord.SelectOption(label="Zone Arrière (Back)", value="Back", emoji="⬅️"),
            discord.SelectOption(label="Flotte (Fleet)", value="Fleet", emoji="🚀"),
        ]
        select = discord.ui.Select(placeholder="Choisis la zone à modifier...", options=options)
        select.callback = self.on_select_zone
        self.add_item(select)

    async def on_select_zone(self, interaction: discord.Interaction):
        zone = interaction.data["values"][0]
        slot_view = SlotSelectView(self.parent_view, zone)
        await interaction.response.send_message(f"📍 **Zone {zone} sélectionnée.** Choisis l'emplacement à modifier :", view=slot_view, ephemeral=True)


# ─── VUE PRINCIPALE DÉFENSE / RESET ──────────────────────────────────────────

class DefenseValidationView(discord.ui.View):
    def __init__(self, original_user_id: int, my_zones: dict, quotas: dict, league: str, fmt: str, my_name: str, my_roster_index: dict):
        super().__init__(timeout=None)
        self.original_user_id = original_user_id
        self.my_zones = my_zones
        self.quotas = quotas
        self.league = league
        self.fmt = fmt
        self.my_name = my_name
        self.my_roster_index = my_roster_index

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.original_user_id:
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
            child.disabled = True
            
        await interaction.followup.send(
            f"✅ **Défense validée !** ({count} personnages verrouillés en défense pour ce round et exclus de `/gac-counter`).",
            ephemeral=True
        )

    @discord.ui.button(label="✏️ Modifier une Équipe", style=discord.ButtonStyle.primary, custom_id="btn_edit_def")
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ZoneSelectView(self)
        await interaction.response.send_message("📌 **Modification de défense** — Sélectionne la Zone à ajuster :", view=view, ephemeral=True)

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
        # 4 = Vendredi, 6 = Dimanche, 1 = Mardi
        if weekday in [4, 6, 1]:
            log.info("⏰ 23h00 (Paris) — Fin de phase de combat GAC détectée. Réinitialisation des unités brûlées...")
            await clear_used_units()
            log.info("✅ Réinitialisation automatique terminée.")

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
        await interaction.response.defer(ephemeral=False)
        
        my_ally_code = None
        async with get_db() as db:
            cursor = await db.execute("SELECT ally_code FROM players WHERE discord_id = ?", (str(interaction.user.id),))
            row = await cursor.fetchone()
            if row:
                my_ally_code = row["ally_code"]
                
        if not my_ally_code:
            await interaction.edit_original_response(content="❌ **Erreur** : Tu dois d'abord lier ton compte avec `/register <ton_ally_code>` pour utiliser le scouting ! Le bot a besoin de connaître ta ligue pour calibrer l'analyse.")
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
            
        await interaction.edit_original_response(content=msg_attente)
        
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
                        await inter.edit_original_response(content=msg)

                    scout_data = await get_scout_data(ally_code, format_gac.value, my_ally_code, progress_callback=cb)
                    
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
                                sd.get("my_roster_index")
                            )
                            result_files.append(discord.File(m_img, filename="my_defense.png"))
                        return result_files

                    files = _build_files(scout_data)

                    msg = f"<@{inter.user.id}> Voici la prédiction de la GAC pour {scout_data['enemy_name']} !\n"
                    msg += "⚠️ *Note : Les prédictions sont générées automatiquement. Utilise les boutons ci-dessous pour valider ou ajuster ta défense.*\n"
                    
                    def_view = None
                    if "my_zones" in scout_data:
                        def_view = DefenseValidationView(
                            inter.user.id,
                            scout_data["my_zones"],
                            scout_data["quotas"],
                            scout_data["league"],
                            scout_data["format"],
                            scout_data["my_name"],
                            scout_data.get("my_roster_index", {})
                        )
                        
                    try:
                        if def_view:
                            await inter.edit_original_response(content=msg, attachments=files, view=def_view)
                        else:
                            await inter.edit_original_response(content=msg, attachments=files)
                    except discord.errors.HTTPException as e:
                        log.warning(f"Impossible de mettre à jour le message original (timeout de 15min ?) : {e}")
                        files_retry = _build_files(scout_data)
                        if def_view:
                            await inter.channel.send(content=msg, files=files_retry, view=def_view)
                        else:
                            await inter.channel.send(content=msg, files=files_retry)
                except Exception as e:
                    log.exception("Erreur lors de la génération de l'image de scouting : %s", e)
                    try:
                        await inter.edit_original_response(content=f"❌ Impossible de scouter cet ennemi (pas de données ou erreur interne).")
                    except:
                        await inter.channel.send(f"<@{inter.user.id}> ❌ Impossible de scouter cet ennemi (pas de données ou erreur interne).")

            clean_code = code_ennemi.replace("-", "").strip()
            
            has_history = False
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT 1 FROM gac_rounds WHERE player_code = ? AND format = ? LIMIT 1", 
                    (clean_code, format_gac.value)
                )
                has_history = await cursor.fetchone() is not None

            if has_history and not force_sync:
                await interaction.edit_original_response(content="⏳ Historique trouvé en base de données. Génération de la prédiction sans refaire de scan...")
                await on_scrape_finished(clean_code, interaction)
            else:
                if not hasattr(self.bot, "gac_scraper"):
                    await interaction.followup.send("❌ Le service d'extraction GAC (Scan) n'est pas actif sur ce serveur.")
                    return
                    
                await interaction.edit_original_response(content="⏳ **[■□□□□□□□□□] 10%** : Analyse approfondie du profil GAC de l'adversaire...")

                scraper = self.bot.gac_scraper
                if scraper.pending_tasks.get(clean_code, 0) > 0:
                    await interaction.edit_original_response(
                        content=f"⏳ **Un scan est déjà en cours** pour ce joueur ! Tu recevras automatiquement le résultat dès qu'il est prêt.\n"
                                f"Tu es abonné(e) à la notification — pas besoin de retaper la commande."
                    )
                    await scraper.queue_scrape(clean_code, interaction, callback=on_scrape_finished, format_filter=format_gac.value)
                else:
                    await scraper.queue_scrape(clean_code, interaction, callback=on_scrape_finished, format_filter=format_gac.value)
            
        except Exception as e:
            log.exception("Erreur lors du scouting : %s", e)
            await interaction.followup.send(f"❌ Impossible d'initier le scouting : {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GACScoutCog(bot))
