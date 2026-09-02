"""
config.py — Chargement centralisé de la configuration depuis .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Discord ---
DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
DISCORD_GUILD_ID: str | None = os.getenv("DISCORD_GUILD_ID") or None

# --- Forum Discord ---
FORUM_CHANNEL_ID: int | None = int(os.getenv("FORUM_CHANNEL_ID", 0)) or None
ADMIN_ROLE_ID: int | None = int(os.getenv("ADMIN_ROLE_ID", 0)) or None

# --- API SWGOH ---
SWGOH_API_URL: str = os.getenv("SWGOH_API_URL", "https://swgoh.gg/api").rstrip("/")

# --- Comlink (auto-hébergé) ---
COMLINK_URL: str = os.getenv("COMLINK_URL", "http://localhost:3200").rstrip("/")

# --- Base de données ---
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "database/swgoh.db")
DATABASE_URL: str | None = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or None
