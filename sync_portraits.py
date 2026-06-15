"""
sync_portraits.py — Télécharge tous les portraits SWGOH en cache local
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
import sys
import time
import cloudscraper
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from config import COMLINK_URL
from services.portrait_cache import PORTRAITS_DIR, get_portrait_path
from services.unit_names import STATIC_NAMES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20
_DELAY = 0.2

# Utilisation de cloudscraper pour contourner les protections
_SCRAPER = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "linux", "mobile": False}
)

def _comlink_metadata() -> dict:
    url = f"{COMLINK_URL.rstrip('/')}/metadata"
    try:
        resp = _SCRAPER.get(url, timeout=_HTTP_TIMEOUT)
        if resp.status_code == 200: return resp.json()
    except Exception: pass
    try:
        resp = _SCRAPER.post(url, json={}, timeout=_HTTP_TIMEOUT)
        if resp.status_code == 200: return resp.json()
    except Exception: pass
    return {}

def _comlink_data(collection: str) -> list:
    url = f"{COMLINK_URL.rstrip('/')}/data"
    for p in [{"payload": {"collection": collection}}, {"collection": collection}]:
        try:
            resp = _SCRAPER.post(url, json=p, timeout=_HTTP_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else data.get(collection, [])
        except Exception: continue
    return []

def _get_cdn_url(meta: dict) -> str:
    for key in ["assetBundleUrl", "assetsUrl", "assetUrl", "cdnRoot"]:
        if meta.get(key): return str(meta[key]).rstrip("/")
    return ""

def _download(url: str, dest: Path) -> bool:
    try:
        resp = _SCRAPER.get(url, timeout=_HTTP_TIMEOUT)
        if resp.status_code == 200 and (
            resp.headers.get("content-type", "").startswith("image") or
            url.endswith(".png") or url.endswith("/")
        ):
            # Certains serveurs ne renvoient pas le bon content-type mais renvoient l'image
            if len(resp.content) > 1000: # Un portrait fait plus de 1ko
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                return True
    except Exception: pass
    return False

def main():
    meta = _comlink_metadata()
    cdn_base = _get_cdn_url(meta)

    units = _comlink_data("unitsList")
    thumb_map = {u.get("baseId", "").upper(): u.get("thumbnailName") for u in units if u.get("baseId")}

    base_ids = list(STATIC_NAMES.keys())
    log.info("Début de la synchronisation pour %d unités...", len(base_ids))

    ok = 0
    for bid in base_ids:
        dest = get_portrait_path(bid)
        if dest.exists():
            ok += 1
            continue

        thumb = thumb_map.get(bid) or f"tex.avatars_{bid.lower()}"
        if thumb.startswith("tex.avatars_") and not thumb.endswith(".png"):
            thumb_file = thumb + ".png"
        else:
            thumb_file = thumb if thumb.endswith(".png") else f"{thumb}.png"

        # Liste étendue d'URLs
        urls = []
        if cdn_base:
            urls.append(f"{cdn_base}/{thumb_file}")
            urls.append(f"{cdn_base}/Android/{thumb_file}")

        # Patterns swgoh.gg officiels et alternatifs
        urls.extend([
            f"https://game-assets.swgoh.gg/{thumb_file}",
            f"https://static-swgoh.gg/game-asset/u/{bid}/",
            f"https://swgoh.gg/game-asset/u/{bid}/",
            f"https://static-swgoh.gg/game-asset/u/{bid.lower()}/",
        ])

        # Test des URLs
        found = False
        for url in urls:
            if _download(url, dest):
                log.info("✓ %s trouvé via %s", bid, url.split('/')[2])
                ok += 1
                found = True
                break
            time.sleep(_DELAY)

        if not found:
            log.warning("✗ Impossible de trouver le portrait pour %s (thumb=%s)", bid, thumb)

    log.info("Terminé : %d/%d portraits disponibles.", ok, len(base_ids))

if __name__ == "__main__":
    main()
