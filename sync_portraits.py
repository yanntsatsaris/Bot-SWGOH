"""
sync_portraits.py — Télécharge tous les portraits SWGOH en cache local
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Usage :
    python sync_portraits.py

Cron (une fois par semaine, dimanche à 2h) :
    0 2 * * 0 /opt/bot-swgoh/venv/bin/python /opt/bot-swgoh/sync_portraits.py >> /var/log/bot-swgoh/sync.log 2>&1
"""
import logging
import sys

from dotenv import load_dotenv

from services.unit_names import STATIC_NAMES
from services.portrait_cache import download_all_portraits

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def main() -> None:
    base_ids = list(STATIC_NAMES.keys())
    log.info("Synchronisation de %d portraits…", len(base_ids))
    results = download_all_portraits(base_ids)
    ok = sum(1 for v in results.values() if v)
    log.info("Terminé : %d/%d portraits disponibles.", ok, len(base_ids))


if __name__ == "__main__":
    main()
