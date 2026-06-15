"""
sync_meta.py — Script de synchronisation des équipes méta GAC depuis SWGOH.GG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Usage :
    python sync_meta.py                   # sync 5v5 + 3v3
    python sync_meta.py --format 5v5      # sync 5v5 uniquement

Cron (tous les jours à 3h) :
    0 3 * * * /opt/bot-swgoh/venv/bin/python /opt/bot-swgoh/sync_meta.py >> /var/log/bot-swgoh/sync.log 2>&1
"""
import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime

import requests
import cloudscraper
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "database/swgoh.db")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

BASE_URL = "https://swgoh.gg"
SQUAD_URLS = {
    "5v5": f"{BASE_URL}/gac/squads/",
    "3v3": f"{BASE_URL}/gac/3v3-squads/",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SwgohBot/1.0; "
        "+https://github.com/yanntsatsaris/Bot-SWGOH)"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}

REQUEST_TIMEOUT = 20       # secondes
RETRY_ATTEMPTS  = 3
RETRY_DELAY     = 5        # secondes entre chaque retry

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers réseau
# ---------------------------------------------------------------------------
def fetch_page(url: str) -> BeautifulSoup | None:
    """
    Récupère une page HTML avec cloudscraper (gère le challenge Cloudflare)
    et retry automatique.

    Returns:
        Objet BeautifulSoup parsé, ou None en cas d'échec définitif.
    """
    # cloudscraper se comporte comme un navigateur réel face à Cloudflare
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "linux", "mobile": False}
    )

    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            log.info("[%d/%d] GET %s", attempt, RETRY_ATTEMPTS, url)
            response = scraper.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return BeautifulSoup(response.text, "lxml")
        except requests.exceptions.HTTPError as exc:
            log.error("Erreur HTTP %s : %s", exc.response.status_code, url)
            if exc.response.status_code in (403, 404, 410):
                break
        except requests.exceptions.ConnectionError:
            log.error("Connexion impossible à %s", url)
        except requests.exceptions.Timeout:
            log.error("Timeout sur %s", url)
        except Exception as exc:
            log.error("Erreur inattendue : %s", exc)

        if attempt < RETRY_ATTEMPTS:
            log.info("Nouvelle tentative dans %ds…", RETRY_DELAY)
            time.sleep(RETRY_DELAY)

    log.error("Abandon après %d tentatives pour %s", RETRY_ATTEMPTS, url)
    return None


# ---------------------------------------------------------------------------
# Parsing HTML
# ---------------------------------------------------------------------------
def parse_squads(soup: BeautifulSoup, fmt: str, source_url: str) -> list[dict]:
    """
    Extrait les équipes méta depuis le HTML de SWGOH.GG.

    SWGOH.GG affiche ses squads dans des blocs avec la classe CSS
    `.squad-listing` (ou similaire). Si la structure du site change,
    mettre à jour les sélecteurs ci-dessous et relancer.

    Args:
        soup:       BeautifulSoup de la page.
        fmt:        '5v5' ou '3v3'.
        source_url: URL d'origine pour traçabilité.

    Returns:
        Liste de dicts prêts à être insérés en base.
    """
    teams: list[dict] = []

    # --- Sélecteur principal : blocs de squads ----------------------------
    # SWGOH.GG utilise des cards avec la classe "squad-row" ou "squad-unit"
    squad_blocks = (
        soup.select("div.squad-row")           # Layout actuel (2024-2025)
        or soup.select("div.squad-listing")    # Layout alternatif
        or soup.select("div[class*='squad']")  # Fallback générique
    )

    if not squad_blocks:
        log.warning(
            "Aucun bloc de squad trouvé sur %s — "
            "la structure HTML a peut-être changé.", source_url
        )
        return teams

    log.info("%d squads trouvés sur %s", len(squad_blocks), source_url)

    for block in squad_blocks:
        try:
            team = _parse_single_squad(block, fmt, source_url)
            if team:
                teams.append(team)
        except Exception:
            log.exception("Erreur lors du parsing d'un bloc squad")
            continue

    return teams


def _parse_single_squad(block, fmt: str, source_url: str) -> dict | None:
    """Parse un seul bloc HTML de squad et retourne un dict normalisé."""

    # --- Leader ---
    # Le leader est généralement le premier personnage ou a une classe dédiée
    leader_el = (
        block.select_one(".squad-leader .char-portrait-full-name")
        or block.select_one(".squad-leader .unit-name")
        or block.select_one(".squad-unit:first-child .unit-name")
        or block.select_one("[class*='leader'] [class*='name']")
    )
    leader_name = leader_el.get_text(strip=True) if leader_el else None

    # --- Membres ---
    member_els = (
        block.select(".squad-unit .char-portrait-full-name")
        or block.select(".squad-unit .unit-name")
        or block.select("[class*='unit'] [class*='name']")
    )
    members = [el.get_text(strip=True) for el in member_els if el.get_text(strip=True)]

    # Si leader non détecté séparément, prendre le premier membre
    if not leader_name and members:
        leader_name = members[0]

    if not leader_name or not members:
        return None

    # --- Win rate / Usage ---
    win_rate_el = (
        block.select_one(".squad-stat-win-rate")
        or block.select_one("[class*='win-rate']")
        or block.select_one("[class*='winrate']")
    )
    win_rate = _parse_percent(win_rate_el.get_text(strip=True) if win_rate_el else None)

    usage_el = (
        block.select_one(".squad-stat-usage")
        or block.select_one("[class*='usage']")
    )
    usage_rate = _parse_percent(usage_el.get_text(strip=True) if usage_el else None)

    # --- Contres ---
    counter_els = (
        block.select(".squad-counter .char-portrait-full-name")
        or block.select(".counter-unit .unit-name")
        or []
    )
    counters = [el.get_text(strip=True) for el in counter_els if el.get_text(strip=True)]

    return {
        "leader_name": leader_name,
        "members":     json.dumps(members, ensure_ascii=False),
        "counters":    json.dumps(counters, ensure_ascii=False),
        "format":      fmt,
        "win_rate":    win_rate,
        "usage_rate":  usage_rate,
        "source_url":  source_url,
        "updated_at":  datetime.utcnow().isoformat(timespec="seconds"),
    }


def _parse_percent(text: str | None) -> float | None:
    """Convertit '72.5%' → 0.725. Retourne None si non parsable."""
    if not text:
        return None
    try:
        return round(float(text.strip().replace("%", "").replace(",", ".")) / 100, 4)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------------
def get_connection() -> sqlite3.Connection:
    """Ouvre une connexion SQLite synchrone (usage hors bot)."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    con = sqlite3.connect(DATABASE_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def upsert_teams(con: sqlite3.Connection, teams: list[dict]) -> int:
    """
    Insère ou met à jour les équipes dans meta_teams.
    Clé d'unicité : (leader_name, format).

    Returns:
        Nombre de lignes insérées/mises à jour.
    """
    if not teams:
        return 0

    sql = """
        INSERT INTO meta_teams
            (leader_name, members, counters, format, win_rate, usage_rate, source_url, updated_at)
        VALUES
            (:leader_name, :members, :counters, :format, :win_rate, :usage_rate, :source_url, :updated_at)
        ON CONFLICT(leader_name, format) DO UPDATE SET
            members    = excluded.members,
            counters   = excluded.counters,
            win_rate   = excluded.win_rate,
            usage_rate = excluded.usage_rate,
            source_url = excluded.source_url,
            updated_at = excluded.updated_at
    """
    # Ajouter la contrainte UNIQUE si elle n'existe pas encore
    _ensure_unique_index(con)

    with con:
        con.executemany(sql, teams)

    return len(teams)


def _ensure_unique_index(con: sqlite3.Connection) -> None:
    """Crée l'index unique (leader_name, format) si absent."""
    con.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_meta_teams_leader_format
        ON meta_teams (leader_name, format)
    """)


# ---------------------------------------------------------------------------
# Orchestration principale
# ---------------------------------------------------------------------------
def sync_format(fmt: str) -> int:
    """Synchronise les équipes méta pour un format donné. Retourne le nb de lignes."""
    url = SQUAD_URLS[fmt]
    log.info("━━ Synchronisation %s depuis %s", fmt, url)

    soup = fetch_page(url)
    if soup is None:
        log.error("Impossible de récupérer les données %s — sync annulée.", fmt)
        return 0

    teams = parse_squads(soup, fmt, url)
    if not teams:
        log.warning("Aucune équipe extraite pour le format %s.", fmt)
        return 0

    con = get_connection()
    try:
        count = upsert_teams(con, teams)
        log.info("✓ %d équipes %s insérées/mises à jour.", count, fmt)
        return count
    finally:
        con.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync équipes méta SWGOH GAC")
    parser.add_argument(
        "--format",
        choices=["5v5", "3v3"],
        default=None,
        help="Synchroniser un seul format (défaut : les deux)",
    )
    args = parser.parse_args()

    formats = [args.format] if args.format else ["5v5", "3v3"]
    total = 0

    for fmt in formats:
        total += sync_format(fmt)

    log.info("━━ Synchronisation terminée. Total : %d équipes.", total)


if __name__ == "__main__":
    main()
