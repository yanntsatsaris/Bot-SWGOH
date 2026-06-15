"""
config.py — Chargement centralisé de la configuration depuis .env
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Discord ---
DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]          # Obligatoire : lève KeyError si absent
DISCORD_GUILD_ID: str | None = os.getenv("DISCORD_GUILD_ID") or None

# --- API SWGOH ---
SWGOH_API_URL: str = os.getenv("SWGOH_API_URL", "https://swgoh.gg/api").rstrip("/")

# --- Comlink (auto-hébergé) ---
COMLINK_URL: str = os.getenv("COMLINK_URL", "http://localhost:3000").rstrip("/")

# --- Base de données ---
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "database/swgoh.db")
