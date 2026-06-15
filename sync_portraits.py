"""
sync_portraits.py — Télécharge tous les portraits SWGOH en cache local
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
import logging
import sys
import time
from pathlib import Path

# On charge le .env AVANT d'importer config
from dotenv import load_dotenv
load_dotenv()

import requests
import cloudscraper

from config import COMLINK_URL
from services.portrait_cache import PORTRAITS_DIR, get_portrait_path
from services.unit_names import STATIC_NAMES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15
_DELAY = 0.2

_SCRAPER = cloudscraper.create_scraper(
    browser={"browser": "chrome", "platform": "linux", "mobile": False}
)

def _comlink_metadata() -> dict:
    url = f"{COMLINK_URL.rstrip('/')}/metadata"
    try:
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200: return resp.json()
    except Exception: pass
    try:
        resp = requests.post(url, json={}, timeout=5)
        if resp.status_code == 200: return resp.json()
    except Exception: pass
    return {}

def _comlink_data(collection: str) -> list:
    url = f"{COMLINK_URL.rstrip('/')}/data"
    payloads = [
        {"payload": {"collection": collection}},
        {"collection": collection}
    ]
    for p in payloads:
        try:
            resp = requests.post(url, json=p, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list): return data
                return data.get(collection, [])
        except Exception: continue
    return []

def _get_fallback_thumb_map() -> dict:
    url = "https://raw.githubusercontent.com/swgoh-utils/swgoh-data/master/units.json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {u.get("base_id", "").upper(): u.get("thumbnail_name") for u in data if u.get("base_id")}
    except Exception: pass
    return {}

def _download(url: str, dest: Path) -> bool:
    try:
        client = _SCRAPER if "swgoh.gg" in url else requests
        resp = client.get(url, timeout=_HTTP_TIMEOUT, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 2000:
            if b"PNG" in resp.content[:10] or b"JFIF" in resp.content[:10]:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                return True
    except Exception: pass
    return False

def main():
    meta = _comlink_metadata()
    cdn_base = str(meta.get("assetBundleUrl") or meta.get("assetsUrl") or "").rstrip("/")

    log.info("Récupération des métadonnées des unités...")
    thumb_map = {u.get("baseId", "").upper(): u.get("thumbnailName") for u in _comlink_data("unitsList") if u.get("baseId")}
    if not thumb_map:
        log.info("Tentative via source externe...")
        thumb_map = _get_fallback_thumb_map()

    base_ids = list(STATIC_NAMES.keys())
    log.info("Synchronisation de %d portraits...", len(base_ids))

    ok = 0
    for bid in base_ids:
        dest = get_portrait_path(bid)
        if dest.exists() and dest.stat().st_size > 2000:
            ok += 1
            continue

        thumb = thumb_map.get(bid) or f"tex.avatars_{bid.lower()}"
        thumb = thumb.replace(".png", "")

        urls = [
            f"https://swgoh.gg/game-asset/u/{bid}/",
            f"https://game-assets.swgoh.gg/{thumb}.png",
            f"https://swgoh.gg/static/img/assets/{thumb}.png",
        ]
        if cdn_base:
            urls.insert(0, f"{cdn_base}/{thumb}.png")
            urls.insert(1, f"{cdn_base}/Android/{thumb}.png")

        found = False
        for url in urls:
            if _download(url, dest):
                log.info("✓ %s trouvé via %s", bid, url.split('/')[2])
                ok += 1
                found = True
                break
            time.sleep(_DELAY)

        if not found:
            log.warning("✗ Échec pour %s (thumb=%s)", bid, thumb)

    log.info("Terminé : %d/%d portraits synchronisés.", ok, len(base_ids))

if __name__ == "__main__":
    main()
