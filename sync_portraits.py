"""
sync_portraits.py — Télécharge tous les portraits SWGOH en cache local
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stratégie :
  1. Récupère l'URL du CDN EA via /metadata Comlink
  2. Récupère la liste des unités via /data pour avoir les thumbnailName réels
  3. Télécharge depuis le CDN EA ou swgoh.gg (plusieurs patterns)

Usage :
    python sync_portraits.py
"""
import logging
import sys
import time
import requests
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
_DELAY = 0.1

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
})

def _comlink_metadata() -> dict:
    """Tente de récupérer les métadonnées (GET ou POST)."""
    url = f"{COMLINK_URL.rstrip('/')}/metadata"
    # Essai GET
    try:
        resp = _SESSION.get(url, timeout=_HTTP_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    # Essai POST
    try:
        resp = _SESSION.post(url, json={}, timeout=_HTTP_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass

    log.warning("Impossible de récupérer les metadata Comlink sur %s", url)
    return {}

def _comlink_data(collection: str) -> list:
    """Récupère une collection via /data."""
    url = f"{COMLINK_URL.rstrip('/')}/data"
    payloads = [
        {"payload": {"collection": collection}},
        {"collection": collection}
    ]
    for p in payloads:
        try:
            resp = _SESSION.post(url, json=p, timeout=_HTTP_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list): return data
                return data.get(collection, [])
        except Exception:
            continue
    return []

def _get_cdn_url(meta: dict) -> str:
    """Extrait l'URL du CDN."""
    for key in ["assetBundleUrl", "assetsUrl", "assetUrl", "cdnRoot"]:
        if meta.get(key):
            return str(meta[key]).rstrip("/")
    return ""

def _download(url: str, dest: Path) -> bool:
    try:
        resp = _SESSION.get(url, timeout=_HTTP_TIMEOUT)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("image"):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.content)
            return True
    except Exception:
        pass
    return False

def main():
    meta = _comlink_metadata()
    cdn_base = _get_cdn_url(meta)

    units = _comlink_data("unitsList")
    thumb_map = {}
    for u in units:
        bid = u.get("baseId")
        thumb = u.get("thumbnailName")
        if bid and thumb:
            thumb_map[bid.upper()] = thumb

    base_ids = list(STATIC_NAMES.keys())
    log.info("Début de la synchronisation pour %d unités...", len(base_ids))

    ok = 0
    for bid in base_ids:
        dest = get_portrait_path(bid)
        if dest.exists():
            ok += 1
            continue

        thumb = thumb_map.get(bid, f"tex.avatars_{bid.lower()}")

        # Liste des URLs à tester
        urls = []
        if cdn_base:
            urls.append(f"{cdn_base}/{thumb}.png")
            urls.append(f"{cdn_base}/Android/{thumb}.png")

        urls.extend([
            f"https://game-assets.swgoh.gg/{thumb}.png",
            f"https://swgoh.gg/game-asset/u/{bid}/",
            f"https://static-swgoh.gg/game-asset/u/{bid}/",
        ])

        for url in urls:
            if _download(url, dest):
                log.info("✓ %s téléchargé", bid)
                ok += 1
                break
            time.sleep(_DELAY)
        else:
            log.warning("✗ Impossible de trouver le portrait pour %s", bid)

    log.info("Synchronisation terminée : %d/%d portraits disponibles.", ok, len(base_ids))

if __name__ == "__main__":
    main()
