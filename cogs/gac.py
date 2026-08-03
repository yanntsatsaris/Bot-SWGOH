"""
cogs/gac.py — Commandes slash liées à la Grande Arène (GAC)
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db
from utils.helpers import format_ally_code

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

🧹 **`/gac-reset-round`**
> Réinitialise manuellement tes unités brûlées pour le round actif. (Le bot effectue également un reset automatique chaque soir de fin de combat à 23h00 Paris).

ℹ️ **`/help`**
> Affiche ce message d'aide à tout moment.
"""


async def unit_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    if not current:
        return []
    current_lower = current.lower()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT base_id, name FROM game_characters WHERE LOWER(name) LIKE ? OR LOWER(base_id) LIKE ? LIMIT 25",
            (f"%{current_lower}%", f"%{current_lower}%")
        )
        rows = await cursor.fetchall()
    return [
        app_commands.Choice(name=f"{row['name']} ({row['base_id']})", value=row["base_id"])
        for row in rows
    ]


class GacCog(commands.Cog, name="GAC"):
    """Commandes d'analyse et de gestion de la Grande Arène."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # /register — Enregistrement du compte SWGOH (PRIMORDIAL)
    # ------------------------------------------------------------------
    @app_commands.command(
        name="register",
        description="Associe ton compte Discord à ton compte SWGOH.",
    )
    @app_commands.describe(ally_code="Ton code allié SWGOH (ex : 123-456-789)")
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

        success_msg = f"✅ **Compte enregistré avec succès (Code Allié : `{clean}`) !**\n\n{HELP_MESSAGE}"
        await interaction.followup.send(success_msg, ephemeral=True)

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
        slot="Numéro de l'emplacement (1, 2, 3...)",
        leader="Leader de l'équipe (autocomplétion disponible)",
        membre_2="2ème membre de l'équipe (optionnel)",
        membre_3="3ème membre de l'équipe (optionnel)",
        membre_4="4ème membre de l'équipe (5v5 uniquement)",
        membre_5="5ème membre de l'équipe (5v5 uniquement)",
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
        leader=unit_autocomplete,
        membre_2=unit_autocomplete,
        membre_3=unit_autocomplete,
        membre_4=unit_autocomplete,
        membre_5=unit_autocomplete,
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
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        
        leader_id = leader.strip().upper()
        raw_members = [m for m in [membre_2, membre_3, membre_4, membre_5] if m]
        members_list = [m.strip().upper() for m in raw_members]
        
        from services.unit_names import get_name
        from database.db import save_user_defense_slot
        
        is_my = (cote.value == "my")
        if is_my:
            await save_user_defense_slot(str(interaction.user.id), zone.value, slot, leader_id, members_list)
            side_str = "Ta Défense"
        else:
            side_str = "Défense Adverse"
            
        m_str = ", ".join(get_name(m) for m in members_list) if members_list else "aucun"
        await interaction.followup.send(
            f"✅ **{side_str} mise à jour !**\n"
            f"📍 **{zone.name} — Slot #{slot}** : Leader **{get_name(leader_id)}** (Membres : {m_str}).\n"
            f"Toutes tes propositions de contres et ton plan d'attaque tiendront compte de cette modification.",
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
