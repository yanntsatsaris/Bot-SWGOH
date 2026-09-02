"""
cogs/gac.py — Commandes slash liées à la Grande Arène (GAC)
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db
from utils.helpers import format_ally_code
from config import FORUM_CHANNEL_ID

log = logging.getLogger(__name__)


HELP_MESSAGE = """
🤖 **Bienvenue sur Bot-SWGOH !**

Ce bot est ton assistant personnel pour dominer la Grande Arène (GAC).
Voici les commandes principales que tu peux utiliser :

🔍 **`/gac-scout <code_allié_ennemi> <format>`**
> Scanne l'historique de ton adversaire, prédit sa défense et génère ta carte de contre-défense sur mesure.
> *Boutons interactifs sous la carte : [🔒 Valider ma Défense], [✏️ Ma Défense], [✏️ Défense Ennemie], et [⚔️ Plan d'Attaque Global].*

⚔️ **`/gac-counter <leader_ennemi> <format> [membres...]`**
> Recherche les meilleurs contres contre une équipe spécifique en utilisant **uniquement ton roster disponible** (tes unités posées en défense ou déjà brûlées en attaque sont automatiquement exclues).
> *Utilise les boutons [Victoire] ou [Défaite] pour enregistrer le résultat du combat et brûler l'équipe engagée.*

✏️ **`/gac-edit-slot <cote> <zone> <slot> <leader> [membres...]`**
> Modifie un emplacement d'équipe spécifique (sur ta défense ou la défense adverse) avec l'**autocomplétion textuelle des personnages** pour réajuster la carte exacte vue en jeu.

⚔️ **Planificateur d'Attaque Global (`[⚔️ Plan d'Attaque Global]`)**
> Génère une carte visuelle complète attribuant le meilleur contre 100% prêt de ton roster à chaque secteur ennemi.

⚔️ **`/gac-record-battle <zone> <slot> <resultat> [leader] [membres...]`**
> Enregistre le résultat d'un combat d'attaque avec l'équipe de ton choix (ou l'équipe suggérée), brûle les unités utilisées et réactualise instantanément la carte du plan d'attaque.

🧹 **`/gac-reset-round`**
> Réinitialise manuellement tes unités brûlées pour le round actif. (Le bot effectue également un reset automatique chaque soir de fin de combat à 23h00 Paris).

ℹ️ **`/help`**
> Affiche ce message d'aide à tout moment.
"""


async def unit_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    zone_raw = str(getattr(interaction.namespace, "zone", "") or "")
    is_fleet = ("fleet" in zone_raw.lower() or "flotte" in zone_raw.lower())
    has_zone = bool(zone_raw)

    # Récupérer les unités déjà renseignées dans les autres champs de la même commande
    already_selected = set()
    for field_name in [
        "leader", "membre_2", "membre_3", "membre_4", "membre_5",
        "renfort_1", "renfort_2", "renfort_3", "renfort_4"
    ]:
        val = getattr(interaction.namespace, field_name, None)
        if val and isinstance(val, str) and val.strip():
            already_selected.add(val.strip().upper())

    target_type = "ship" if is_fleet else "character"
    current_lower = current.strip().lower() if current else ""
    
    choices = []
    seen_bids = set()

    async with get_db() as db:
        if current_lower:
            # 1. Recherche prioritaire dans les abréviations (ex: SLKR, CLS, JMK...)
            try:
                if has_zone:
                    cursor_alias = await db.execute(
                        """
                        SELECT a.alias, c.base_id, c.name
                        FROM unit_aliases a
                        JOIN game_characters c ON UPPER(a.base_id) = UPPER(c.base_id)
                        WHERE c.type = ? AND (LOWER(a.alias) = ? OR LOWER(a.alias) LIKE ?)
                        ORDER BY LENGTH(a.alias) ASC, a.alias ASC
                        LIMIT 15
                        """,
                        (target_type, current_lower, f"{current_lower}%")
                    )
                else:
                    cursor_alias = await db.execute(
                        """
                        SELECT a.alias, c.base_id, c.name
                        FROM unit_aliases a
                        JOIN game_characters c ON UPPER(a.base_id) = UPPER(c.base_id)
                        WHERE LOWER(a.alias) = ? OR LOWER(a.alias) LIKE ?
                        ORDER BY LENGTH(a.alias) ASC, a.alias ASC
                        LIMIT 15
                        """,
                        (current_lower, f"{current_lower}%")
                    )
                alias_rows = await cursor_alias.fetchall()
                for r in alias_rows:
                    bid = r["base_id"].upper()
                    if bid not in already_selected and bid not in seen_bids:
                        choices.append(app_commands.Choice(
                            name=f"⚡ [{r['alias'].upper()}] {r['name']} ({r['base_id']})",
                            value=r["base_id"]
                        ))
                        seen_bids.add(bid)
            except Exception as err:
                log.debug("Erreur recherche alias dans autocomplete: %s", err)

            # 2. Recherche standard par nom et base_id
            if has_zone:
                cursor = await db.execute(
                    """
                    SELECT base_id, name 
                    FROM game_characters 
                    WHERE type = ? AND (LOWER(name) LIKE ? OR LOWER(base_id) LIKE ?)
                    ORDER BY name ASC
                    LIMIT 35
                    """,
                    (target_type, f"%{current_lower}%", f"%{current_lower}%")
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT base_id, name 
                    FROM game_characters 
                    WHERE LOWER(name) LIKE ? OR LOWER(base_id) LIKE ?
                    ORDER BY name ASC
                    LIMIT 35
                    """,
                    (f"%{current_lower}%", f"%{current_lower}%")
                )
            rows = await cursor.fetchall()
        else:
            if has_zone:
                cursor = await db.execute(
                    """
                    SELECT base_id, name 
                    FROM game_characters 
                    WHERE type = ?
                    ORDER BY name ASC
                    LIMIT 35
                    """,
                    (target_type,)
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT base_id, name 
                    FROM game_characters 
                    ORDER BY name ASC
                    LIMIT 35
                    """
                )
            rows = await cursor.fetchall()

    for row in rows:
        bid = row["base_id"].upper()
        if bid not in already_selected and bid not in seen_bids:
            choices.append(app_commands.Choice(name=f"{row['name']} ({row['base_id']})", value=row["base_id"]))
            seen_bids.add(bid)
            if len(choices) >= 25:
                break
                
    return choices[:25]


async def slot_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[int]]:
    # Normalisation robuste de la zone
    zone_raw = str(getattr(interaction.namespace, "zone", "") or "")
    zone = "North"
    for z_candidate in ["North", "South", "Back", "Fleet"]:
        if z_candidate.lower() in zone_raw.lower():
            zone = z_candidate
            break

    # Normalisation robuste du côté (Ma Défense vs Défense Adverse)
    cmd_name = str(getattr(interaction.command, "name", "") or "").lower()
    cote_raw = str(getattr(interaction.namespace, "cote", "") or "").lower()
    
    if "record-battle" in cmd_name or "enemy" in cote_raw or "adverse" in cote_raw:
        used_type_target = "enemy_defense_manual"
    else:
        used_type_target = "defense"

    discord_id = str(interaction.user.id)
    
    from database.db import get_db, load_active_gac_session, load_user_defense_zones
    from services.unit_names import get_name
    from utils.gac_config import get_gac_quotas
    from services.comlink import get_player
    
    league = "KYBER"
    format_type = "5v5"
    
    # 1. Récupérer la session active de l'utilisateur
    try:
        session = await load_active_gac_session(discord_id)
        if session:
            if session.get("league"):
                league = session["league"].upper()
            if session.get("format"):
                format_type = session["format"]
    except Exception as e:
        log.debug("Erreur lecture session active pour slot_autocomplete: %s", e)

    # 2. Quotas de la ligue
    quotas = get_gac_quotas(league, format_type)
    quota_slots = quotas.get(zone, 4 if league == "KYBER" else 2)

    # 3. Charger les équipes actuelles enregistrées pour cette zone
    slots_dict = {}
    try:
        user_zones = await load_user_defense_zones(discord_id, used_type_target)
        zone_teams = user_zones.get(zone, [])
        for idx, t in enumerate(zone_teams, 1):
            s_idx = t.get("slot_index") or idx
            ldr = t.get("leader_id")
            if ldr and ldr not in ["USED", "None", "EMPTY", "Vide"]:
                slots_dict[s_idx] = ldr
    except Exception as e:
        log.debug("Erreur lecture user_zones pour slot_autocomplete: %s", e)
        zone_teams = []

    max_slots = max(quota_slots, max(slots_dict.keys(), default=1), len(zone_teams))

    # Récupération des secteurs déjà tombés (CLEARED) si record-battle
    cleared_slots = set()
    if "record-battle" in cmd_name:
        try:
            async with get_db() as db:
                c_cursor = await db.execute(
                    "SELECT slot_index FROM active_sector_status WHERE discord_id = ? AND zone = ? AND status = 'CLEARED'",
                    (discord_id, zone)
                )
                c_rows = await c_cursor.fetchall()
                cleared_slots = {r["slot_index"] for r in c_rows}
        except Exception:
            pass

    choices = []
    for s_idx in range(1, max_slots + 1):
        if s_idx in cleared_slots:
            continue  # Exclure les secteurs déjà tombés
        ldr_id = slots_dict.get(s_idx)
        if ldr_id and ldr_id not in ["USED", "None", "EMPTY", "Vide"]:
            label = f"Slot #{s_idx} : {get_name(ldr_id)}"
        else:
            label = f"Slot #{s_idx} (Vide / À modifier)"
        choices.append(app_commands.Choice(name=label[:100], value=s_idx))
        
    if not choices and "record-battle" in cmd_name:
        choices.append(app_commands.Choice(name=f"🎉 Tous les secteurs de la zone {zone} sont tombés !", value=1))
        
    return choices[:25]


class GacCog(commands.Cog, name="GAC"):
    """Commandes d'analyse et de gestion de la Grande Arène."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /register — Enregistrement du compte SWGOH (PRIMORDIAL)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="register",
        description="Lie ton compte Discord à ton compte SWGOH via ton code allié (ex: 123-456-789)."
    )
    @app_commands.describe(
        ally_code="Ton code allié SWGOH avec ou sans tirets (ex: 123-456-789 ou 123456789)"
    )
    async def register(self, interaction: discord.Interaction, ally_code: str) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            clean = format_ally_code(ally_code)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        discord_id = str(interaction.user.id)
        username = interaction.user.display_name

        async with get_db() as db:
            await db.execute(
                """
                INSERT INTO players (discord_id, ally_code, username)
                VALUES (?, ?, ?)
                ON CONFLICT(discord_id) DO UPDATE SET
                    ally_code  = excluded.ally_code,
                    username   = excluded.username,
                    updated_at = datetime('now')
                """,
                (discord_id, clean, username),
            )
            await db.commit()

        success_msg = f"✅ **Compte enregistré avec succès (Code Allié : `{clean}`) !**\n\n{HELP_MESSAGE}"
        await interaction.followup.send(success_msg, ephemeral=True)

        # Création du fil Forum si configuré
        if FORUM_CHANNEL_ID:
            try:
                from cogs.forum_manager import create_player_forum_thread

                # Récupérer la ligue via Comlink pour choisir le bon tag
                league: str | None = None
                try:
                    from services.comlink import get_player
                    player_data = await get_player(clean)
                    if player_data:
                        league = player_data.get("league", None)
                        if league:
                            league = league.lower()
                except Exception as e:
                    log.warning("[Forum] Impossible de récupérer la ligue depuis Comlink : %s", e)

                thread = await create_player_forum_thread(
                    bot=self.bot,
                    discord_id=discord_id,
                    ally_code=clean,
                    username=username,
                    league=league,
                )
                if thread:
                    mention = thread.mention
                    await interaction.followup.send(
                        f"📌 Ton fil personnel a été créé dans le forum : {mention}",
                        ephemeral=True,
                    )
            except Exception as e:
                log.error("[Forum] Erreur lors de la création du fil forum : %s", e)

    # ------------------------------------------------------------------
    # /help — Manuel d'utilisation du bot
    # ------------------------------------------------------------------
    @app_commands.command(
        name="help",
        description="Affiche le manuel d'utilisation du bot.",
    )
    async def help_command(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(HELP_MESSAGE, ephemeral=True)

    # ------------------------------------------------------------------
    # /gac-edit-slot — Modification ciblée d'un slot (autocomplétion)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="gac-edit-slot",
        description="Modifie un emplacement spécifique (Ta Défense ou Défense Adverse) avec autocomplétion."
    )
    @app_commands.describe(
        cote="Choisir si c'est ta défense ou la défense adverse",
        zone="La zone de la carte à modifier",
        slot="Numéro de l'emplacement (autocomplétion avec le nom de l'équipe actuelle)",
        leader="Leader / Vaisseau Amiral (autocomplétion)",
        membre_2="2ème membre / 1er Vaisseau Principal (optionnel)",
        membre_3="3ème membre / 2ème Vaisseau Principal (optionnel)",
        membre_4="4ème membre / 3ème Vaisseau Principal (optionnel)",
        membre_5="5ème membre / 1er Renfort Flotte (optionnel)",
        renfort_2="2ème Renfort Flotte (Flotte uniquement)",
        renfort_3="3ème Renfort Flotte (Flotte uniquement)",
        renfort_4="4ème Renfort Flotte (Flotte uniquement)",
    )
    @app_commands.choices(
        cote=[
            app_commands.Choice(name="Ma Défense", value="my"),
            app_commands.Choice(name="Défense Adverse", value="enemy"),
        ],
        zone=[
            app_commands.Choice(name="Zone Nord (North)", value="North"),
            app_commands.Choice(name="Zone Sud (South)", value="South"),
            app_commands.Choice(name="Zone Arrière (Back)", value="Back"),
            app_commands.Choice(name="Flotte (Fleet)", value="Fleet"),
        ]
    )
    @app_commands.autocomplete(
        slot=slot_autocomplete,
        leader=unit_autocomplete,
        membre_2=unit_autocomplete,
        membre_3=unit_autocomplete,
        membre_4=unit_autocomplete,
        membre_5=unit_autocomplete,
        renfort_2=unit_autocomplete,
        renfort_3=unit_autocomplete,
        renfort_4=unit_autocomplete,
    )

    async def edit_slot(
        self,
        interaction: discord.Interaction,
        cote: app_commands.Choice[str],
        zone: app_commands.Choice[str],
        slot: int,
        leader: str,
        membre_2: str | None = None,
        membre_3: str | None = None,
        membre_4: str | None = None,
        membre_5: str | None = None,
        renfort_2: str | None = None,
        renfort_3: str | None = None,
        renfort_4: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        
        leader_id = leader.strip().upper()
        raw_members = [m for m in [membre_2, membre_3, membre_4, membre_5, renfort_2, renfort_3, renfort_4] if m]
        members_list = [m.strip().upper() for m in raw_members]
        
        from services.unit_names import get_name
        from database.db import save_user_defense_slot
        
        is_my = (cote.value == "my")
        used_type = "defense" if is_my else "enemy_defense_manual"
        await save_user_defense_slot(str(interaction.user.id), zone.value, slot, leader_id, members_list, used_type=used_type)
        side_str = "Ta Défense" if is_my else "Défense Adverse"
            
        m_str = ", ".join(get_name(m) for m in members_list) if members_list else "aucun"
        await interaction.followup.send(
            f"✅ **{side_str} mise à jour !**\n"
            f"📍 **{zone.name} — Slot #{slot}** : Leader/Amiral **{get_name(leader_id)}** ({len(members_list)} membres/renforts : {m_str}).\n"
            f"Toutes tes propositions de contres et ton plan d'attaque tiendront compte de cette modification.\n"
            f"💡 *Pour voir la carte mise à jour, réutilise `/gac-scout` ou clique sur `[🔄 Actualiser Carte]` dans le plan.*",
            ephemeral=True
        )

    # ------------------------------------------------------------------
    # /gac-reset-round — Réinitialisation manuelle des unités brûlées
    # ------------------------------------------------------------------
    @app_commands.command(
        name="gac-reset-round",
        description="Réinitialise tes unités brûlées (défense et attaques) pour le round en cours.",
    )
    async def reset_round(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        from database.db import clear_used_units
        await clear_used_units(str(interaction.user.id))
        await interaction.followup.send(
            "✅ **Tes unités pour ce round ont été réinitialisées !**\n"
            "Toutes tes unités sont de nouveau disponibles pour `/gac-counter`.",
            ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GacCog(bot))
