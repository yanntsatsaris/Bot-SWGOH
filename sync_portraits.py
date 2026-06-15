"""
sync_portraits.py — Télécharge tous les portraits SWGOH en cache local
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stratégie :
  1. GET /metadata  → récupère la version du jeu + URL du CDN EA
  2. POST /data avec {"payload": {"collection": "unitsList"}} → thumbnailName
  3. Télécharge depuis le CDN EA, puis fallback swgoh.gg

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
_DELAY = 0.2

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
})


# ---------------------------------------------------------------------------
# Appels Comlink
# ---------------------------------------------------------------------------

def _comlink_metadata() -> dict:
    """GET /metadata — retourne les infos de version du jeu."""
    url = f"{COMLINK_URL.rstrip('/')}/metadata"
    try:
        resp = _SESSION.get(url, timeout=_HTTP_TIMEOUT)
        data = resp.json()
        # Log complet pour debug
        log.info("Metadata Comlink (status=%d) : %s", resp.status_code, data)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        log.warning("Metadata Comlink indisponible : %s", exc)
        return {}


def _comlink_data(collection: str) -> list:
    """
    POST /data avec {"payload": {"collection": ...}} — format correct swgoh-comlink.
    """
    url = f"{COMLINK_URL.rstrip('/')}/data"
    for payload in [
        {"payload": {"collection": collection, "enums": False}},
        {"payload": {"collection": collection}},
        {"collection": collection},
    ]:
        try:
            resp = _SESSION.post(url, json=payload, timeout=_HTTP_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    log.info("Comlink /data OK (%d items) avec payload=%s", len(data), payload)
                    return data
                items = data.get(collection, [])
                if items:
                    log.info("Comlink /data OK (%d items) avec payload=%s", len(items), payload)
                    return items
            log.debug("Comlink /data HTTP %d avec payload=%s", resp.status_code, payload)
        except Exception as exc:
            log.debug("Comlink /data exception : %s", exc)
    log.warning("Comlink /data indisponible pour collection '%s'", collection)
    return []


# ---------------------------------------------------------------------------
# Récupération de l'URL du CDN EA
# ---------------------------------------------------------------------------

def _get_cdn_base(meta: dict) -> str:
    """Extrait l'URL du CDN EA depuis les métadonnées Comlink."""
    cdn_keys = ("assetBundleUrl", "assetsUrl", "assetUrl", "cdnRoot", "gameUrl", "cdnUrl",
                "assetBase", "bundleUrl")
    for key in cdn_keys:
        val = meta.get(key, "")
        if val and str(val).startswith("http"):
            log.info("CDN trouvé via metadata[%s] = %s", key, val)
            return str(val).rstrip("/")

    # Chercher dans les sous-dicts
    for key, sub in meta.items():
        if isinstance(sub, dict):
            for k, v in sub.items():
                if isinstance(v, str) and v.startswith("http") and (
                    "cdn" in k.lower() or "asset" in k.lower() or "bundle" in k.lower()
                ):
                    log.info("CDN trouvé via metadata[%s][%s] = %s", key, k, v)
                    return v.rstrip("/")

    return ""


# ---------------------------------------------------------------------------
# Téléchargement
# ---------------------------------------------------------------------------

def _try_url(url: str, dest) -> bool:
    try:
        resp = _SESSION.get(url, timeout=_HTTP_TIMEOUT, allow_redirects=True)
        ct = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ct.startswith("image"):
            dest.write_bytes(resp.content)
            return True
        log.debug("✗ HTTP %d (ct=%s) — %s", resp.status_code, ct, url)
    except Exception as exc:
        log.debug("✗ %s — %s", type(exc).__name__, url)
    return False


def _download_portrait(base_id: str, thumb: str, cdn_base: str) -> bool:
    dest = get_portrait_path(base_id)
    if dest.exists():
        return True

    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    tl = thumb.lower()

    urls: list[str] = []

    # 1. CDN EA si disponible
    if cdn_base:
        for sub in ("", "Android", "iOS"):
            prefix = f"{cdn_base}/{sub}" if sub else cdn_base
            urls += [f"{prefix}/{thumb}.png", f"{prefix}/{tl}.png"]

    # 2. swgoh.gg variantes (peut fonctionner selon l'IP)
    urls += [
        f"https://swgoh.gg/static/img/assets/{tl}.png",
        f"https://swgoh.gg/static/img/assets/{thumb}.png",
        f"https://swgoh.gg/game-asset/u/{base_id}/",
        f"https://swgoh.gg/game-asset/u/{base_id.lower()}/",
    ]

    for url in urls:
        if _try_url(url, dest):
            log.info("✓ %s  ←  %s", base_id, url)
            return True
        time.sleep(_DELAY)

    log.warning("✗ Portrait introuvable : %s  (thumb=%s)", base_id, thumb)
    return False


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    meta     = _comlink_metadata()
    cdn_base = _get_cdn_base(meta)
    if not cdn_base:
        log.warning("Aucune URL CDN trouvée dans les metadata Comlink")

    # thumbnailName réels depuis Comlink /data
    units_list = _comlink_data("unitsList")
    thumb_map: dict[str, str] = {}
    for u in units_list:
        bid   = (u.get("baseId") or u.get("base_id", "")).upper()
        thumb = u.get("thumbnailName", "")
        if bid and thumb:
            thumb_map[bid] = thumb
    if thumb_map:
        log.info("%d thumbnailName récupérés depuis Comlink", len(thumb_map))
    else:
        log.warning("thumbnailName indisponibles — dérivation automatique depuis le base_id")

    base_ids = list(STATIC_NAMES.keys())
    log.info("Synchronisation de %d portraits…", len(base_ids))

    ok = 0
    for base_id in base_ids:
        thumb = thumb_map.get(base_id.upper(), f"tex.avatars_{base_id.lower()}")
        if _download_portrait(base_id, thumb, cdn_base):
            ok += 1

    log.info("Terminé : %d/%d portraits disponibles.", ok, len(base_ids))


if __name__ == "__main__":
    main()

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
_DELAY = 0.3  # secondes entre chaque requête (éviter le rate-limit)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
})


# ---------------------------------------------------------------------------
# Appels Comlink (sync)
# ---------------------------------------------------------------------------

def _comlink_metadata() -> dict:
    """
    POST /metadata — retourne les infos de version du jeu.
    Note : pas de wrapper {"payload": ...} pour cet endpoint.
    """
    url = f"{COMLINK_URL.rstrip('/')}/metadata"
    try:
        resp = _SESSION.post(url, json={}, timeout=_HTTP_TIMEOUT)
        data = resp.json()
        log.info("Metadata Comlink — clés : %s", list(data.keys()))
        return data
    except Exception as exc:
        log.warning("Metadata Comlink indisponible : %s", exc)
        return {}


def _comlink_data(collection: str) -> list:
    """
    POST /data — endpoint sans wrapper {"payload": ...}.
    Retourne la liste brute de la collection demandée.
    """
    url = f"{COMLINK_URL.rstrip('/')}/data"
    try:
        resp = _SESSION.post(
            url,
            json={"collection": collection, "enums": False},
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            log.warning("Comlink /data HTTP %d pour %s", resp.status_code, collection)
            return []
        data = resp.json()
        # La réponse peut être une liste directe ou un dict {collectionName: [...]}
        if isinstance(data, list):
            return data
        return data.get(collection, [])
    except Exception as exc:
        log.warning("Comlink /data/%s indisponible : %s", collection, exc)
        return []


# ---------------------------------------------------------------------------
# Récupération de l'URL du CDN EA
# ---------------------------------------------------------------------------

def _get_cdn_base(meta: dict) -> str:
    """Extrait l'URL du CDN EA depuis les métadonnées Comlink."""
    for key in ("assetBundleUrl", "assetsUrl", "assetUrl", "cdnRoot", "gameUrl", "cdnUrl"):
        val = meta.get(key, "")
        if val and val.startswith("http"):
            log.info("CDN trouvé via metadata[%s] = %s", key, val)
            return val.rstrip("/")

    # Essayer de deviner depuis la version
    version = meta.get("latestGamedataVersion", "")
    if version:
        log.info("Version du jeu : %s (pas de CDN URL directe)", version)

    return ""


# ---------------------------------------------------------------------------
# Découverte du CDN via swgoh.gg redirect
# ---------------------------------------------------------------------------

def _discover_cdn_via_redirect(base_id: str) -> str:
    """
    swgoh.gg/game-asset/ redirige vers le vrai CDN EA.
    On suit la redirection pour récupérer l'URL de base du CDN.
    Retourne le préfixe CDN (ex: https://cdn.ea.com/swgoh/...) ou "".
    """
    url = f"https://swgoh.gg/game-asset/u/{base_id}/"
    try:
        resp = _SESSION.get(url, timeout=_HTTP_TIMEOUT, allow_redirects=True)
        final_url = resp.url
        ct = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ct.startswith("image"):
            log.info("swgoh.gg redirect vers CDN : %s", final_url)
            # Extrait la base (tout sauf le nom de fichier)
            cdn_base = final_url.rsplit("/", 1)[0]
            return cdn_base
        log.debug("swgoh.gg redirect : HTTP %d (ct=%s) → %s", resp.status_code, ct, final_url)
    except Exception as exc:
        log.debug("swgoh.gg redirect échoué : %s", exc)
    return ""


# ---------------------------------------------------------------------------
# Téléchargement d'un portrait
# ---------------------------------------------------------------------------

def _download_url(url: str, dest) -> bool:
    """Télécharge l'image à `url` dans `dest`. Retourne True si succès."""
    try:
        resp = _SESSION.get(url, timeout=_HTTP_TIMEOUT)
        ct = resp.headers.get("content-type", "")
        if resp.status_code == 200 and ct.startswith("image"):
            dest.write_bytes(resp.content)
            return True
        log.debug("✗ HTTP %d (ct=%s) — %s", resp.status_code, ct, url)
    except Exception as exc:
        log.debug("✗ Exception : %s — %s", exc, url)
    return False


def _download_portrait(base_id: str, thumb: str, cdn_base: str, cdn_discovered: str) -> bool:
    dest = get_portrait_path(base_id)
    if dest.exists():
        return True

    PORTRAITS_DIR.mkdir(parents=True, exist_ok=True)
    thumb_lower = thumb.lower()

    urls: list[str] = []

    # 1. CDN EA découvert via swgoh.gg redirect (le plus fiable)
    if cdn_discovered:
        urls += [
            f"{cdn_discovered}/{thumb}.png",
            f"{cdn_discovered}/{thumb_lower}.png",
        ]

    # 2. CDN EA depuis metadata Comlink
    if cdn_base:
        for sub in ("Android", "iOS", ""):
            prefix = f"{cdn_base}/{sub}" if sub else cdn_base
            urls += [
                f"{prefix}/{thumb}.png",
                f"{prefix}/{thumb_lower}.png",
            ]

    # 3. swgoh.gg (peut fonctionner selon l'IP du serveur)
    urls += [
        f"https://swgoh.gg/game-asset/u/{base_id}/",
        f"https://swgoh.gg/game-asset/u/{base_id}.png",
        f"https://swgoh.gg/static/img/assets/{thumb_lower}.png",
    ]

    for url in urls:
        if _download_url(url, dest):
            log.info("✓ %s  ←  %s", base_id, url)
            return True
        time.sleep(_DELAY)

    log.warning("✗ Portrait introuvable : %s  (thumb=%s)", base_id, thumb)
    return False


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------

def main() -> None:
    meta      = _comlink_metadata()
    cdn_base  = _get_cdn_base(meta)

    # Récupère les thumbnailName réels depuis Comlink /data
    units_list = _comlink_data("unitsList")
    thumb_map: dict[str, str] = {}
    if units_list:
        for u in units_list:
            bid   = u.get("baseId") or u.get("base_id", "")
            thumb = u.get("thumbnailName", "")
            if bid and thumb:
                thumb_map[bid.upper()] = thumb
        log.info("%d thumbnailName récupérés depuis Comlink /data", len(thumb_map))
    else:
        log.warning("Comlink /data indisponible — dérivation du thumbnailName depuis le base_id")

    base_ids = list(STATIC_NAMES.keys())
    log.info("Synchronisation de %d portraits…", len(base_ids))

    # Découverte du CDN via swgoh.gg redirect sur un premier personnage connu
    cdn_discovered = ""
    if not cdn_base:
        log.info("Tentative de découverte du CDN via swgoh.gg redirect…")
        cdn_discovered = _discover_cdn_via_redirect("JEDIMASTERKENOBI")
        if not cdn_discovered:
            cdn_discovered = _discover_cdn_via_redirect("DARTHVADER")

    ok = 0
    for base_id in base_ids:
        # Utilise le vrai thumbnailName si disponible, sinon dérive du base_id
        thumb = thumb_map.get(base_id.upper(), f"tex.avatars_{base_id.lower()}")
        if _download_portrait(base_id, thumb, cdn_base, cdn_discovered):
            ok += 1

    log.info("Terminé : %d/%d portraits disponibles.", ok, len(base_ids))


if __name__ == "__main__":
    main()

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

