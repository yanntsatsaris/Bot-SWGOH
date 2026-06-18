import logging
import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db

log = logging.getLogger(__name__)

# --- Autocomplétion ---
async def unit_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    """Autocomplétion des personnages (filtré par format plus tard, pour l'instant tout)"""
    current = current.lower()
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT base_id, name FROM game_characters WHERE name LIKE ? OR base_id LIKE ? LIMIT 25",
            (f"%{current}%", f"%{current}%")
        )
        rows = await cursor.fetchall()
        
    return [
        app_commands.Choice(name=f"{row['name']} ({row['base_id']})", value=row["base_id"])
        for row in rows
    ]


class GACScoutCog(commands.Cog, name="GACScout"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="gac-report-match",
        description="Ajoute manuellement une équipe posée en défense par un ennemi."
    )
    @app_commands.describe(
        code_ennemi="Le code allié de l'ennemi (ex: 123456789)",
        format_gac="Le format de la GAC (3v3, 5v5 ou fleet)",
        zone="La zone où l'équipe a été posée",
        leader_ennemi="Le personnage/vaisseau en Leader",
        membres_ennemi="Les membres (IDs séparés par des virgules)"
    )
    @app_commands.choices(
        format_gac=[
            app_commands.Choice(name="3 contre 3", value="3v3"),
            app_commands.Choice(name="5 contre 5", value="5v5"),
            app_commands.Choice(name="Flottes", value="fleet"),
        ],
        zone=[
            app_commands.Choice(name="Nord (North)", value="North"),
            app_commands.Choice(name="Sud (South)", value="South"),
            app_commands.Choice(name="Arrière (Back)", value="Back"),
            app_commands.Choice(name="Flottes (Fleet)", value="Fleet"),
        ]
    )
    @app_commands.autocomplete(leader_ennemi=unit_autocomplete)
    async def gac_report_match(
        self,
        interaction: discord.Interaction,
        code_ennemi: str,
        format_gac: app_commands.Choice[str],
        zone: app_commands.Choice[str],
        leader_ennemi: str,
        membres_ennemi: str
    ) -> None:
        """Enregistre manuellement une défense ennemie dans la base."""
        # Nettoyage des membres
        membres_list = [m.strip().upper() for m in membres_ennemi.split(",")]
        membres_str = ",".join(membres_list)
        leader_clean = leader_ennemi.strip().upper()
        code_clean = code_ennemi.replace("-", "").strip()

        async with get_db() as db:
            await db.execute("""
                INSERT INTO gac_history (enemy_id, format, zone, leader_id, members_ids)
                VALUES (?, ?, ?, ?, ?)
            """, (code_clean, format_gac.value, zone.value, leader_clean, membres_str))
            await db.commit()

        await interaction.response.send_message(
            f"✅ **Défense enregistrée !**\n"
            f"L'ennemi **{code_clean}** a placé `{leader_clean}` avec `{membres_str}` en zone **{zone.name}** ({format_gac.name})."
        )

    @app_commands.command(
        name="gac-scout",
        description="Scout le profil GAC d'un adversaire."
    )
    @app_commands.describe(
        code_ennemi="Le code allié de l'ennemi (ex: 123-456-789)",
        format_gac="Le format de la GAC (3v3 ou 5v5)"
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
        format_gac: app_commands.Choice[str]
    ) -> None:
        """Commande principale pour scouter un ennemi."""
        await interaction.response.defer(thinking=True)
        try:
            # Récupère l'ally code du joueur s'il est enregistré
            my_ally_code = None
            async with get_db() as db:
                cursor = await db.execute("SELECT ally_code FROM players WHERE discord_id = ?", (str(interaction.user.id),))
                row = await cursor.fetchone()
                if row:
                    my_ally_code = row["ally_code"]
                    
            from services.scouting import get_scout_data
            from services.scout_image import generate_scout_map
            
            scout_data = await get_scout_data(code_ennemi, format_gac.value, my_ally_code)
            
            files = []
            
            # Map de l'ennemi
            enemy_img = generate_scout_map(
                scout_data["zones"], 
                scout_data["quotas"], 
                scout_data["league"], 
                scout_data["format"], 
                scout_data["enemy_name"] + " (Ennemi)", 
                scout_data["source"]
            )
            files.append(discord.File(enemy_img, filename="enemy_defense.png"))
            
            # Map du joueur (suggestion)
            if "my_zones" in scout_data:
                my_img = generate_scout_map(
                    scout_data["my_zones"], 
                    scout_data["quotas"], 
                    scout_data["league"], 
                    scout_data["format"], 
                    scout_data["my_name"] + " (Ta Défense Suggérée)", 
                    "Contre-Défense Optimisée"
                )
                files.append(discord.File(my_img, filename="my_defense.png"))
            
            msg = "Voici la prédiction de la GAC !"
            if not my_ally_code:
                msg += "\n*Astuce : Utilise `/register` pour que le bot te propose aussi une défense sur mesure !*"
                
            await interaction.followup.send(content=msg, files=files)
            
        except Exception as e:
            log.exception("Erreur lors du scouting : %s", e)
            await interaction.followup.send(f"❌ Impossible de scouter cet ennemi : {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GACScoutCog(bot))
