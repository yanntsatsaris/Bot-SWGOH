import logging
import discord
from discord import app_commands
from discord.ext import commands

from database.db import get_db

log = logging.getLogger(__name__)



class GACScoutCog(commands.Cog, name="GACScout"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

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
        
        # Vérification obligatoire de l'enregistrement de l'utilisateur
        my_ally_code = None
        async with get_db() as db:
            cursor = await db.execute("SELECT ally_code FROM players WHERE discord_id = ?", (str(interaction.user.id),))
            row = await cursor.fetchone()
            if row:
                my_ally_code = row["ally_code"]
                
        if not my_ally_code:
            await interaction.edit_original_response(content="❌ **Erreur** : Tu dois d'abord lier ton compte avec `/register <ton_ally_code>` pour utiliser le scouting ! Le bot a besoin de connaître ta ligue pour calibrer l'analyse.")
            return

        # Récupération de la taille de la file d'attente
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
            # Fonction callback qui sera appelée quand le scraper aura fini (ou immédiatement si données en cache)
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
                    msg += "⚠️ *Note : Les prédictions sont générées automatiquement. Des erreurs de placement ou d'optimisation sont possibles.*\n"
                    if not my_ally_code:
                        msg += "\n*Astuce : Utilise `/register` pour que le bot te propose aussi une défense sur mesure !*"
                    else:
                        msg += "\n*Astuce : Utilise ensuite `/gac-counter` pour obtenir les meilleurs contres contre sa défense !*"
                        
                    try:
                        await inter.edit_original_response(content=msg, attachments=files)
                    except discord.errors.HTTPException as e:
                        log.warning(f"Impossible de mettre à jour le message original (timeout de 15min ?) : {e}")
                        # Re-générer les fichiers car les BytesIO précédents peuvent être fermés
                        files_retry = _build_files(scout_data)
                        await inter.channel.send(content=msg, files=files_retry)
                except Exception as e:
                    log.exception("Erreur lors de la génération de l'image de scouting : %s", e)
                    try:
                        await inter.edit_original_response(content=f"❌ Impossible de scouter cet ennemi (pas de données ou erreur interne).")
                    except:
                        await inter.channel.send(f"<@{inter.user.id}> ❌ Impossible de scouter cet ennemi (pas de données ou erreur interne).")

            clean_code = code_ennemi.replace("-", "").strip()
            
            # Vérification si on a déjà de l'historique pour ce joueur et ce format
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

                # Vérification si un scraping est déjà en cours pour ce joueur
                scraper = self.bot.gac_scraper
                if scraper.pending_tasks.get(clean_code, 0) > 0:
                    await interaction.edit_original_response(
                        content=f"⏳ **Un scan est déjà en cours** pour ce joueur ! Tu recevras automatiquement le résultat dès qu'il est prêt.\n"
                                f"Tu es abonné(e) à la notification — pas besoin de retaper la commande."
                    )
                    # On s'abonne au callback sans relancer de scraping
                    await scraper.queue_scrape(clean_code, interaction, callback=on_scrape_finished)
                else:
                    await scraper.queue_scrape(clean_code, interaction, callback=on_scrape_finished)
            
        except Exception as e:
            log.exception("Erreur lors du scouting : %s", e)
            await interaction.followup.send(f"❌ Impossible d'initier le scouting : {e}")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GACScoutCog(bot))
