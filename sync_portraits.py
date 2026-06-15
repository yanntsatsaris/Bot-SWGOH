"""
sync_portraits.py — Télécharge tous les portraits SWGOH en cache local
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stratégie (dans l'ordre) :
  1. Comlink /metadata  → URL de base du CDN EA
  2. Comlink /data      → thumbnailName pour chaque unité
  3. Tentative de téléchargement depuis le CDN EA puis swgoh.gg

Usage :
    python sync_portraits.py

Cron (une fois par semaine, dimanche à 2h) :
    0 2 * * 0 /opt/bot-swgoh/venv/bin/python /opt/bot-swgoh/sync_portraits.py >> /var/log/bot-swgoh/sync.log 2>&1
"""
import logging
import sys
import time

import requests
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
_DELAY = 0.15  # secondes entre chaque requête


# ---------------------------------------------------------------------------
# Appels Comlink (sync, pour usage hors-bot)
# ---------------------------------------------------------------------------

def _comlink_post(endpoint: str, payload: dict) -> dict:
    url = f"{COMLINK_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    resp = requests.post(url, json={"payload": payload}, timeout=_HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _get_asset_cdn_base() -> str:
    """
    Récupère l'URL de base du CDN EA depuis le metadata Comlink.
    Retourne une chaîne vide si indisponible.
    """
    try:
        resp = requests.get(f"{COMLINK_URL.rstrip('/')}/metadata", timeout=_HTTP_TIMEOUT)
        meta = resp.json()
        log.info("Metadata Comlink — clés disponibles : %s", list(meta.keys()))
        for key in ("assetBundleUrl", "assetsUrl", "assetUrl", "cdnRoot", "gameUrl"):
            if key in meta and meta[key]:
                log.info("CDN trouvé via metadata[%s] = %s", key, meta[key])
                return str(meta[key]).rstrip("/")
    except Exception as exc:
        log.warning("Metadata Comlink indisponible : %s", exc)
    return ""


def _get_unit_thumbnail_map() -> dict[str, str]:
    """
    Retourne {base_id: thumbnailName} depuis Comlink /data.
    Ex : {"SITH_ETERNAL_EMPEROR": "tex.avatars_sithemperor"}
    """
    try:
        data = _comlink_post("data", {"collection": "unitsList"})
        units = data.get("unitsList", [])
        result = {
            u["baseId"]: u["thumbnailName"]
            for u in units
            if u.get("baseId") and u.get("thumbnailName")
        }
        log.info("%d thumbnailName récupérés depuis Comlink", len(result))
        return result
    except Exception as exc:
        log.warning("Impossible de récupérer unitsList via Comlink : %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Téléchargement d'un portrait
# ---------------------------------------------------------------------------

def _download_url(url: str, dest) -> bool:
    """Tente de télécharger l'image à `url` dans `dest`. Retourne True si succès."""
    try:
        resp = requests.get(url, timeout=_HTTP_TIMEOUT, headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://swgoh.gg/",
        })
        ct = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ct.startswith("image"):
            dest.write_bytes(resp.content)
            return True
        log.debug("✗ HTTP %d (ct=%s) — %s", resp.status_code, ct, url)
    except Exception as exc:
        log.debug("✗ Exception pour %s : %s", url, exc)
    return False


def _download_portrait(base_id: str, thumbnail: str, cdn_base: str) -> bool:
    dest = get_portrait_path(base_id)
    if dest.exists():
        return True

    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)

    # Normalisation du nom de texture (tex.avatars_XXX → tex.avatars_xxx)
    thumb_lower = thumbnail.lower()

    urls: list[str] = []

    # 1. CDN EA via metadata Comlink
    if cdn_base:
        urls += [
            f"{cdn_base}/{thumbnail}.png",
            f"{cdn_base}/{thumb_lower}.png",
            f"{cdn_base}/Android/{thumbnail}.png",
            f"{cdn_base}/iOS/{thumbnail}.png",
        ]

    # 2. swgoh.gg CDN statique (texture name)
    urls += [
        f"https://swgoh.gg/static/img/assets/{thumb_lower}.png",
        f"https://swgoh.gg/static/img/assets/{thumbnail}.png",
    ]

    # 3. swgoh.gg game-asset (base_id direct)
    urls += [
        f"https://swgoh.gg/game-asset/u/{base_id}.png",
        f"https://swgoh.gg/game-asset/u/{base_id.lower()}.png",
    ]

    for url in urls:
        if _download_url(url, dest):
            log.info("✓ %s  ←  %s", base_id, url)
            return True
        time.sleep(_DELAY)

    log.warning("✗ Portrait introuvable : %s  (thumbnail=%s)", base_id, thumbnail)
    return False


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    cdn_base    = _get_asset_cdn_base()
    thumb_map   = _get_unit_thumbnail_map()
    base_ids    = list(STATIC_NAMES.keys())

    log.info("Synchronisation de %d portraits…", len(base_ids))

    ok = 0
    for base_id in base_ids:
        thumb = thumb_map.get(base_id, f"tex.avatars_{base_id.lower().replace('_', '')}")
        if _download_portrait(base_id, thumb, cdn_base):
            ok += 1

    log.info("Terminé : %d/%d portraits disponibles.", ok, len(base_ids))


if __name__ == "__main__":
    main()

