"""
main.py — Point d'entrée du bot SWGOH-GAC
"""
import asyncio
import logging
import sys

import discord
from discord.ext import commands

from config import DISCORD_TOKEN, DISCORD_GUILD_ID
from database.db import init_db

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
import os
import platform
from logging.handlers import WatchedFileHandler

# Chemin du log adapté selon l'OS (Linux vs Windows en dev)
LOG_FILE = "/var/log/bot-swgoh/bot.log" if platform.system() == "Linux" else "bot.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        WatchedFileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extensions (cogs) à charger au démarrage
# ---------------------------------------------------------------------------
INITIAL_EXTENSIONS = [
    "cogs.gac",
    "cogs.admin",
    "cogs.gac_test",
    "cogs.gac_counter",
    "cogs.gac_history",
    "cogs.review_portraits",
    "cogs.gac_scout",
    "cogs.meta_scanner",
    "cogs.meta_manager",
    "cogs.gac_scanner",
    "cogs.gac_global_meta",
]


# ---------------------------------------------------------------------------
# Classe principale du bot
# ---------------------------------------------------------------------------
class SwgohBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(
            command_prefix="!",  # Fallback texte ; les slash commands sont prioritaires
            intents=intents,
            help_command=None,
        )
        self.guild_id: int | None = int(DISCORD_GUILD_ID) if DISCORD_GUILD_ID else None

    async def setup_hook(self) -> None:
        """Appelé automatiquement par discord.py avant la connexion."""
        # 1. Initialisation de la base de données
        await init_db()
        from database.db import get_db
        from services.gac_history_scraper import GACHistoryScraper

        # 1.5 Initialisation du Scraper en arrière-plan
        self.gac_scraper = GACHistoryScraper(get_db)
        await self.gac_scraper.start()

        # 2. Chargement des cogs
        for extension in INITIAL_EXTENSIONS:
            try:
                await self.load_extension(extension)
                log.info("Extension chargée : %s", extension)
            except Exception:
                log.exception("Impossible de charger l'extension : %s", extension)

        # 3. Synchronisation des slash commands
        if self.guild_id:
            # Synchro instantanée sur un seul serveur (pratique en développement)
            guild = discord.Object(id=self.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Slash commands synchronisées sur le serveur %s", self.guild_id)
        else:
            # Synchro globale (~1h de propagation ; recommandé en production)
            await self.tree.sync()
            log.info("Slash commands synchronisées globalement")

    async def on_ready(self) -> None:
        log.info("Connecté en tant que %s (ID : %s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Game(name="Star Wars: Galaxy of Heroes")
        )

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        log.error("Erreur commande texte : %s", error)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------
async def main() -> None:
    bot = SwgohBot()
    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
