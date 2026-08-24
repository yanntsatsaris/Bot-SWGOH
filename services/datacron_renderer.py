"""
services/datacron_renderer.py — Générateur graphique officiel de badges Datacrons (DTC)
Utilise les textures et anneaux officiels de swgoh.gg avec composition multicalque :
1. Anneau d'arrière-plan officiel (standard / focused / L9)
2. Lueur d'alignement/tiers
3. Cube Datacron 3D haute résolution
4. Médaillon supérieur pour le personnage ciblé (Focused / L9)
5. Points de tiers inférieurs (gradient #feffff -> #ffe59c avec lueur)
"""
import os
import io
import math
import logging
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageOps

log = logging.getLogger(__name__)

ASSETS_DIR = Path("assets/datacrons")
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

OFFICIAL_ASSETS_URLS = {
    "datacron-icon-bg--focused-level9.png": "https://assets.swgoh.gg/frontend/assets/datacron-icon-bg--focused-level9-B3neGwEp.png",
    "datacron-icon-bg--level9.webp": "https://assets.swgoh.gg/frontend/assets/datacron-icon-bg--level9-C5rkueIv.webp",
    "datacron-ring-bg.png": "https://assets.swgoh.gg/frontend/assets/datacron-ring-bg-BAY-loxK.png",
    "datacron-ring-thin-bg--focused.png": "https://assets.swgoh.gg/frontend/assets/datacron-ring-thin-bg--focused-DTTg5A80.png",
    "datacron_inactive_dot.webp": "https://assets.swgoh.gg/frontend/assets/datacron-ring-bg-BAY-loxK.png",
    "tex.datacron_a_focused_max.png": "https://game-assets.swgoh.gg/textures/tex.datacron_a_focused_max.png",
    "tex.datacron_b_max.png": "https://game-assets.swgoh.gg/textures/tex.datacron_b_max.png",
    "tex.datacron_c_max.png": "https://game-assets.swgoh.gg/textures/tex.datacron_c_max.png",
    "tex.datacron_d_max.png": "https://game-assets.swgoh.gg/textures/tex.datacron_d_max.png",
}

def _download_asset_if_missing(filename: str, url: str) -> Path:
    """Assure le téléchargement et la mise en cache locale d'une texture Datacron."""
    local_path = ASSETS_DIR / filename
    if not local_path.exists() or local_path.stat().st_size < 500:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                local_path.write_bytes(resp.read())
        except Exception as e:
            log.warning(f"Impossible de télécharger la texture DTC {filename}: {e}")
    return local_path

def render_datacron_badge(
    level: int = 3,
    max_tiers: int = None,
    is_focused: bool = False,
    character_base_id: str = None,
    character_icon_url: str = None,
    cube_texture_url: str = None,
    glow_tier: int = 5,
    size: tuple[int, int] = (120, 120)
) -> Image.Image:
    """
    Génère un badge Datacron haute fidélité (RGBA) identique à l'affichage officiel de swgoh.gg.
    - level : niveau débloqué (ex: 1, 2, 3 pour standard ; 1..5 pour variante focus)
    - is_focused : True si variante ciblée (5 tiers)
    - character_base_id : Base ID du personnage pour portrait local (affiché dès L3)
    - character_icon_url : URL de secours si portrait non présent
    - cube_texture_url : URL de la texture de cube
    - size : Taille finale du badge (largeur, hauteur)
    """
    CANVAS_SIZE = 512
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))

    # Affichage du médaillon personnage au sommet : si variante focus OU standard L3 avec perso
    has_char_portrait = bool((is_focused or level >= 3) and (character_base_id or character_icon_url))

    # Nombre de tiers : 5 si variante focus, sinon 3 pour standard
    if max_tiers is not None:
        total_tiers = max_tiers
    else:
        total_tiers = 5 if is_focused else 3

    active_level = min(level, total_tiers)

    # 1. Choix du Cadre Principal :
    # - Variante Focus : datacron-icon-bg--focused-level9.png
    # - Standard (Tier 1, 2 ou Tier 3 avec/sans perso) : datacron-icon-bg--level9.webp
    if is_focused:
        bg_name = "datacron-icon-bg--focused-level9.png"
        ring_dim = int(CANVAS_SIZE * 0.86)
        ring_x = (CANVAS_SIZE - ring_dim) // 2
        ring_y = int(CANVAS_SIZE * 0.10)
        center_x = CANVAS_SIZE // 2
        center_y = ring_y + int(ring_dim * (65.5 / 118))
        main_radius = int(ring_dim * (43.5 / 118))
    else:
        bg_name = "datacron-icon-bg--level9.webp"
        if has_char_portrait:
            ring_dim = int(CANVAS_SIZE * 0.86)
            ring_x = (CANVAS_SIZE - ring_dim) // 2
            ring_y = int(CANVAS_SIZE * 0.10)
            center_x = CANVAS_SIZE // 2
            center_y = ring_y + ring_dim // 2
            main_radius = int(ring_dim * 0.44)
        else:
            ring_dim = int(CANVAS_SIZE * 0.96)
            ring_x = (CANVAS_SIZE - ring_dim) // 2
            ring_y = int(CANVAS_SIZE * 0.02)
            center_x = CANVAS_SIZE // 2
            center_y = ring_y + ring_dim // 2
            main_radius = int(ring_dim * 0.44)

    bg_url = OFFICIAL_ASSETS_URLS.get(bg_name, f"https://assets.swgoh.gg/frontend/assets/{bg_name}")
    bg_path = _download_asset_if_missing(bg_name, bg_url)

    if bg_path.exists():
        raw_frame = Image.open(bg_path).convert("RGBA")
        resized_frame = raw_frame.resize((ring_dim, ring_dim), Image.Resampling.LANCZOS)
        canvas.paste(resized_frame, (ring_x, ring_y), resized_frame)

    # 2. Cube Datacron 3D (2.45 pour standard, 2.85 pour variante focus)
    cube_url = cube_texture_url or (
        OFFICIAL_ASSETS_URLS["tex.datacron_a_focused_max.png"] if is_focused
        else OFFICIAL_ASSETS_URLS["tex.datacron_b_max.png"]
    )
    cube_fn = cube_url.split("/")[-1]
    cube_path = _download_asset_if_missing(cube_fn, cube_url)

    if cube_path.exists():
        cube_raw = Image.open(cube_path).convert("RGBA")
        cube_scale = 2.85 if is_focused else 2.45
        cube_dim = int(main_radius * cube_scale)
        cube_resized = cube_raw.resize((cube_dim, cube_dim), Image.Resampling.LANCZOS)
        cube_x = center_x - cube_dim // 2
        cube_y = center_y - cube_dim // 2 if not is_focused else center_y - cube_dim // 2 - int(CANVAS_SIZE * 0.03)
        canvas.paste(cube_resized, (cube_x, cube_y), cube_resized)

    # 3. Médaillon supérieur du personnage :
    # - Pour standard Tier 3 : anneau bleu officiel (datacron-ring-bg.png)
    # - Pour variante Focus : anneau doré fin (datacron-ring-thin-bg--focused.png)
    if has_char_portrait:
        if is_focused:
            portrait_ring_name = "datacron-ring-thin-bg--focused.png"
        else:
            portrait_ring_name = "datacron-ring-bg.png"

        portrait_ring_url = OFFICIAL_ASSETS_URLS.get(portrait_ring_name, f"https://assets.swgoh.gg/frontend/assets/{portrait_ring_name}")
        portrait_ring_path = _download_asset_if_missing(portrait_ring_name, portrait_ring_url)

        callout_dim = int(CANVAS_SIZE * 0.35)
        callout_x = (CANVAS_SIZE - callout_dim) // 2
        callout_y = ring_y - int(callout_dim * (0.28 if is_focused else 0.22))

        if portrait_ring_path.exists():
            raw_p_ring = Image.open(portrait_ring_path).convert("RGBA")
            resized_p_ring = raw_p_ring.resize((callout_dim, callout_dim), Image.Resampling.LANCZOS)
            canvas.paste(resized_p_ring, (callout_x, callout_y), resized_p_ring)

        char_p = None
        if character_base_id:
            from services.portrait_cache import get_portrait_path
            char_p = get_portrait_path(character_base_id)
            if not char_p or not char_p.exists():
                for test_dir in ["assets/portraits", "assets/datacrons"]:
                    for pat in [f"tex.charui_{character_base_id.lower()}.png", f"charui_{character_base_id.lower()}.png", f"{character_base_id.lower()}.png"]:
                        p_check = Path(test_dir) / pat
                        if p_check.exists():
                            char_p = p_check
                            break
                    if char_p:
                        break

        if not char_p and character_icon_url:
            char_fn = character_icon_url.split("/")[-1]
            char_p = _download_asset_if_missing(char_fn, character_icon_url)

        if char_p and Path(char_p).exists():
            char_img = Image.open(char_p).convert("RGBA")
            inner_char_dim = int(callout_dim * (0.78 if is_focused else 0.76))
            inner_x = callout_x + (callout_dim - inner_char_dim) // 2
            inner_y = callout_y + (callout_dim - inner_char_dim) // 2

            mask = Image.new("L", (inner_char_dim, inner_char_dim), 0)
            m_draw = ImageDraw.Draw(mask)
            m_draw.ellipse((0, 0, inner_char_dim, inner_char_dim), fill=255)

            char_fitted = ImageOps.fit(char_img, (inner_char_dim, inner_char_dim), centering=(0.5, 0.35))
            canvas.paste(char_fitted, (inner_x, inner_y), mask)

    # 4. Points de tiers inférieurs
    dot_ring_name = "datacron-ring-bg.png"
    dot_ring_url = OFFICIAL_ASSETS_URLS.get(dot_ring_name, f"https://assets.swgoh.gg/frontend/assets/{dot_ring_name}")
    dot_ring_path = _download_asset_if_missing(dot_ring_name, dot_ring_url)
    dot_ring_raw = Image.open(dot_ring_path).convert("RGBA") if dot_ring_path.exists() else None

    num_dots = total_tiers
    dot_dim = int(CANVAS_SIZE * 0.150)
    dot_radius = dot_dim // 2

    if num_dots == 3:
        dots_orbit_radius = int(main_radius * 1.01)
        angles = [90 + 19.5, 90, 90 - 19.5]
    else:
        dots_orbit_radius = int(main_radius * 1.05)
        angles = [90 + 54 - (i * 27) for i in range(num_dots)]

    for idx, angle_deg in enumerate(angles):
        rad = math.radians(angle_deg)
        dx = int(center_x + dots_orbit_radius * math.cos(rad))
        dy = int(center_y + dots_orbit_radius * math.sin(rad))

        is_active = (idx < active_level)

        # 4a. Anneau bleu officiel
        if dot_ring_raw:
            resized_dot_ring = dot_ring_raw.resize((dot_dim, dot_dim), Image.Resampling.LANCZOS)
            canvas.paste(resized_dot_ring, (dx - dot_radius, dy - dot_radius), resized_dot_ring)

        if is_active:
            # 4b. Remplissage lumineux radial-gradient(#feffff, #ffe59c)
            inner_dot_r = int(dot_radius * 0.72)
            dot_canvas = Image.new("RGBA", (inner_dot_r * 2, inner_dot_r * 2), (0, 0, 0, 0))
            for r_step in range(inner_dot_r, 0, -1):
                t = r_step / inner_dot_r
                cr = int(254 + (255 - 254) * t)
                cg = int(255 + (229 - 255) * t)
                cb = int(255 + (156 - 255) * t)
                d_draw = ImageDraw.Draw(dot_canvas)
                d_draw.ellipse(
                    (inner_dot_r - r_step, inner_dot_r - r_step, inner_dot_r + r_step, inner_dot_r + r_step),
                    fill=(cr, cg, cb, 255)
                )

            canvas.paste(dot_canvas, (dx - inner_dot_r, dy - inner_dot_r), dot_canvas)

    # 5. Redimensionnement final
    final_output = canvas.resize(size, Image.Resampling.LANCZOS)
    return final_output

def render_datacron_badge_bytes(
    level: int = 3,
    max_tiers: int = 3,
    is_focused: bool = False,
    character_base_id: str = None,
    character_icon_url: str = None,
    cube_texture_url: str = None,
    glow_tier: int = 5,
    size: tuple[int, int] = (120, 120)
) -> bytes:
    """Génère le badge Datacron et retourne les octets PNG."""
    img = render_datacron_badge(
        level=level,
        max_tiers=max_tiers,
        is_focused=is_focused,
        character_base_id=character_base_id,
        character_icon_url=character_icon_url,
        cube_texture_url=cube_texture_url,
        glow_tier=glow_tier,
        size=size
    )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()
