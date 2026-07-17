"""
services/image_generator.py — Génère une image PNG du rapport GAC
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Layout (860px de large, hauteur dynamique) :

  ┌──────────────────────────────────────────────────────────┐
  │  RAPPORT GAC — FORMAT 5v5                                │
  │  Yann  ⚔  Adversaire                                    │
  ├──────────────────────────────────────────────────────────┤
  │  #1  Équipe ennemie  ·  Sith Eternal Emperor             │
  │  [SEE][Vader][Mara][Nihilus][RoyalGuard]                 │
  │                                                          │
  │  ▶ Contres recommandés                                   │
  │  [JMK R7✓][Padmé R5✓][GS R5⚠]                         │
  ├──────────────────────────────────────────────────────────┤
  │  #2  ...                                                 │
  └──────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path

import discord
from PIL import Image, ImageDraw, ImageFont

from services.portrait_cache import get_portrait_path, download_portrait

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de layout
# ---------------------------------------------------------------------------
IMG_WIDTH      = 860
PADDING        = 24
PORTRAIT_SIZE  = 72          # taille de l'image portrait
PORTRAIT_CELL  = 88          # cellule totale (portrait + bordure)
PORTRAIT_GAP   = 8           # espace entre portraits
SECTION_RADIUS = 10          # arrondi des sections

# Hauteurs des blocs
H_HEADER       = 80          # titre + noms joueurs
H_TEAM_LABEL   = 44          # "Équipe ennemie : ..."
H_PORTRAIT_ROW = PORTRAIT_CELL + 30  # portraits + badge
H_COUNTER_LABEL= 34          # "▶ Contres recommandés"
H_SEPARATOR    = 18

# Couleurs (dark theme GitHub-inspired)
C_BG          = (13, 17, 23)        # fond global
C_SECTION     = (22, 27, 34)        # fond des sections
C_BORDER      = (48, 54, 61)        # séparateurs
C_GOLD        = (255, 193, 7)       # titres / accent
C_TEXT        = (230, 237, 243)     # texte principal
C_MUTED       = (139, 148, 158)     # texte secondaire
C_ENEMY       = (248, 81, 73)       # rouge ennemi
C_READY       = (63, 185, 80)       # vert prêt
C_WARN        = (255, 196, 0)       # jaune avertissement
C_MISSING     = (100, 100, 100)     # gris non possédé

# Polices candidates (Windows en priorité, puis Linux/Debian)
_FONT_CANDIDATES = {
    "bold": [
        # Windows
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/verdanab.ttf",
        # Linux/Debian
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ],
    "regular": [
        # Windows
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/verdana.ttf",
        # Linux/Debian
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ],
}


# ---------------------------------------------------------------------------
# Helpers polices
# ---------------------------------------------------------------------------
def _find_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    """Charge la première police TrueType disponible sur le système."""
    for path in _FONT_CANDIDATES.get(style, []):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    log.warning("Aucune police TrueType trouvée pour '%s' size %d — fallback.", style, size)
    return ImageFont.load_default()


# Pré-chargement des polices (évite de recharger à chaque image)
_FONTS: dict[str, ImageFont.FreeTypeFont] = {}


def _get_font(style: str, size: int) -> ImageFont.FreeTypeFont:
    key = f"{style}_{size}"
    if key not in _FONTS:
        _FONTS[key] = _find_font(style, size)
    return _FONTS[key]

# ---------------------------------------------------------------------------
# Helpers Alignements
# ---------------------------------------------------------------------------
_ALIGNMENTS: dict[str, str] = {}
def _get_alignment(base_id: str) -> str:
    global _ALIGNMENTS
    if not _ALIGNMENTS:
        try:
            import json
            with open("data/unit_alignments.json", "r", encoding="utf-8") as f:
                _ALIGNMENTS = json.load(f)
        except Exception as e:
            log.warning("Impossible de charger les alignements: %s", e)
    return _ALIGNMENTS.get(base_id, "Light Side")


# ---------------------------------------------------------------------------
# Helpers portraits
# ---------------------------------------------------------------------------
def _load_portrait(base_id: str | None) -> Image.Image:
    """
    Charge le portrait depuis le cache local.
    Tente un téléchargement à la volée si absent.
    Retourne un placeholder gris si introuvable.
    """
    if base_id:
        path = get_portrait_path(base_id)
        if not path.exists():
            download_portrait(base_id)   # tentative de téléchargement
            path = get_portrait_path(base_id)  # re-calcule après DL
        if path.exists():
            try:
                return Image.open(path).convert("RGBA").resize(
                    (PORTRAIT_SIZE, PORTRAIT_SIZE), Image.LANCZOS
                )
            except Exception:
                pass

    # Placeholder
    img  = Image.new("RGBA", (PORTRAIT_SIZE, PORTRAIT_SIZE), C_SECTION)
    draw = ImageDraw.Draw(img)
    draw.ellipse([8, 8, PORTRAIT_SIZE - 8, PORTRAIT_SIZE - 8], fill=C_BORDER)
    return img


def _circle_mask(size: int) -> Image.Image:
    """Crée un masque circulaire."""
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    return mask


def _draw_portrait_cell(
    canvas: Image.Image,
    x: int,
    y: int,
    base_id: str | None,
    relic_tier: int | None,
    gear_tier: int | None,
    ready: bool,
    owned: bool,
    is_enemy: bool = False,
    missing_omicron: bool = False,
    is_ship: bool = False,
    level: int = 85,
    zetas: int = 0,
    omicrons: int = 0,
) -> None:
    draw = ImageDraw.Draw(canvas)
    
    # --- 1. Dessin du fond d'alignement optionnel ---
    if is_enemy:
        border_color = C_ENEMY
    elif not owned:
        border_color = C_MISSING
    elif missing_omicron:
        border_color = "#9b59b6"
    elif ready:
        border_color = C_READY
    else:
        border_color = C_WARN

    # --- 2. Collage du portrait (au centre) ---
    portrait = _load_portrait(base_id)
    portrait.putalpha(_circle_mask(PORTRAIT_SIZE))
    offset = (PORTRAIT_CELL - PORTRAIT_SIZE) // 2
    canvas.paste(portrait, (x + offset, y + offset), portrait)

    # --- 3. Overlay assombri si non possédé ---
    if not owned and not is_enemy:
        overlay = Image.new("RGBA", (PORTRAIT_CELL, PORTRAIT_CELL), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).ellipse([0, 0, PORTRAIT_CELL - 1, PORTRAIT_CELL - 1], fill=(0, 0, 0, 150))
        canvas.paste(overlay, (x, y), overlay)

    # --- 4. Cadre (Gear) ---
    gear_to_draw = 13 if (relic_tier and relic_tier >= 1) else (gear_tier or 1)
    if not is_ship and gear_to_draw >= 1 and gear_to_draw <= 12:
        gear_name = f"gear{gear_to_draw}.webp"
        gear_path = Path(f"assets/overlays/{gear_name}")
            
        if gear_path.exists():
            gear_img_orig = Image.open(gear_path).convert("RGBA")
            # Redimensionner en conservant les proportions
            scale = 0.85
            new_w = int(gear_img_orig.width * scale)
            new_h = int(gear_img_orig.height * scale)
            gear_img = gear_img_orig.resize((new_w, new_h), Image.LANCZOS)
            
            gx = x + (PORTRAIT_CELL - new_w) // 2
            gy = y + (PORTRAIT_CELL - new_h) // 2
            canvas.paste(gear_img, (gx, gy), gear_img)
        else:
            # Fallback border
            draw.ellipse([x, y, x + PORTRAIT_CELL - 1, y + PORTRAIT_CELL - 1], fill=None, outline=border_color, width=4)

    # --- 5. Relique ou Niveau ---
    badge_font = _get_font("bold", 12)
    level_font = _get_font("bold", 10)
    
    gl_list = ["JEDIMASTERKENOBI", "LORDVADER", "JABBATHEHUTT", "SUPREMELEADERKYLOREN", "SITHPALPATINE", "GLREY", "GRANDMASTERLUKESKYWALKER", "LEIAORGANA"]
    is_gl = base_id in gl_list if base_id else False
    
    # Détermination de la couleur (Light/Dark/Neutral)
    alignment = _get_alignment(base_id) if base_id else "Light Side"
    if alignment == "Dark Side":
        relic_color = "red"
    elif alignment == "Neutral":
        relic_color = "neutral"
    else:
        relic_color = "blue"

    has_relic_borders = not is_ship and (gear_to_draw >= 13)
    
    if has_relic_borders:
        r_right_path = Path(f"assets/overlays/relic_{relic_color}_right.webp")
        if r_right_path.exists():
            orig_r_right = Image.open(r_right_path).convert("RGBA")
            scale = 0.85
            new_w = int(orig_r_right.width * scale)
            new_h = int(orig_r_right.height * scale)
            r_right = orig_r_right.resize((new_w, new_h), Image.LANCZOS)
            
            cx = x + PORTRAIT_CELL // 2
            cy = y + PORTRAIT_CELL // 2
            
            # Côté droit
            canvas.paste(r_right, (cx, cy - new_h // 2), r_right)
            
            # Côté gauche (flip horizontal)
            r_left = r_right.transpose(Image.FLIP_LEFT_RIGHT)
            canvas.paste(r_left, (cx - new_w, cy - new_h // 2), r_left)

        # Macaron du niveau de relique
        if relic_tier and relic_tier >= 1:
            macaron_name = "relic_gl.webp" if is_gl else f"relic_{relic_color}.webp"
            macaron_path = Path(f"assets/overlays/{macaron_name}")
            if macaron_path.exists():
                macaron = Image.open(macaron_path).convert("RGBA")
                scale = 0.85
                mw = int(macaron.width * scale)
                mh = int(macaron.height * scale)
                macaron = macaron.resize((mw, mh), Image.LANCZOS)
                mx = x + (PORTRAIT_CELL - mw) // 2
                my = y + PORTRAIT_CELL - (mh // 2) - 10
                canvas.paste(macaron, (mx, my), macaron)
                
                # Texte du tier
                draw.text((x + PORTRAIT_CELL//2, my + mh//2), str(relic_tier), font=badge_font, fill=(255, 255, 255), anchor="mm")
            else:
                draw.ellipse([x + PORTRAIT_CELL//2 - 12, y + PORTRAIT_CELL - 20, x + PORTRAIT_CELL//2 + 12, y + PORTRAIT_CELL], fill=border_color)
                draw.text((x + PORTRAIT_CELL//2, y + PORTRAIT_CELL - 10), str(relic_tier), font=badge_font, fill=(255, 255, 255), anchor="mm")
        else:
            # Macaron de niveau (pour Gear 13 sans relique)
            level_path = Path("assets/overlays/level.webp")
            if level_path.exists():
                lvl_img = Image.open(level_path).convert("RGBA")
                scale = 0.85
                mw = int(lvl_img.width * scale)
                mh = int(lvl_img.height * scale)
                lvl_img = lvl_img.resize((mw, mh), Image.LANCZOS)
                mx = x + (PORTRAIT_CELL - mw) // 2
                my = y + PORTRAIT_CELL - (mh // 2) - 10
                canvas.paste(lvl_img, (mx, my), lvl_img)
                draw.text((x + PORTRAIT_CELL//2, my + mh//2), str(level), font=level_font, fill=(255, 255, 255), anchor="mm")
            else:
                draw.ellipse([x + PORTRAIT_CELL//2 - 12, y + PORTRAIT_CELL - 20, x + PORTRAIT_CELL//2 + 12, y + PORTRAIT_CELL], fill=(20, 20, 20), outline=border_color, width=2)
                draw.text((x + PORTRAIT_CELL//2, y + PORTRAIT_CELL - 10), str(level), font=level_font, fill=(255, 255, 255), anchor="mm")
    else:
        # Macaron de niveau classique
        level_path = Path("assets/overlays/level.webp")
        if level_path.exists():
            lvl_img = Image.open(level_path).convert("RGBA")
            lvl_img = lvl_img.resize((32, 32), Image.LANCZOS)
            mx = x + (PORTRAIT_CELL - 32) // 2
            my = y + PORTRAIT_CELL - 24
            canvas.paste(lvl_img, (mx, my), lvl_img)
            
            draw.text((x + PORTRAIT_CELL//2, my + 16), str(level), font=level_font, fill=(255, 255, 255), anchor="mm")

    # --- 6. Zetas / Omicrons ---
    # Omicrons (Gauche)
    if omicrons > 0 or missing_omicron:
        omi_path = Path("assets/overlays/tex.charui_omicron.png")
        ox, oy = x, y + PORTRAIT_CELL - 28
        if omi_path.exists():
            omi = Image.open(omi_path).convert("RGBA").resize((28, 28), Image.LANCZOS)
            canvas.paste(omi, (ox, oy), omi)
        else:
            draw.ellipse([ox + 2, oy + 2, ox + 26, oy + 26], fill="#9b59b6")
        
        # Nombre ou indicateur
        text_val = str(omicrons) if not missing_omicron else "!"
        text_color = (255, 255, 255) if not missing_omicron else (255, 100, 100)
        draw.text((ox + 14, oy + 14), text_val, font=_get_font("bold", 12), fill=text_color, anchor="mm")

    # Zetas (Droite)
    if zetas > 0:
        zeta_path = Path("assets/overlays/tex.charui_zeta.png")
        zx, zy = x + PORTRAIT_CELL - 28, y + PORTRAIT_CELL - 28
        if zeta_path.exists():
            zeta_img = Image.open(zeta_path).convert("RGBA").resize((28, 28), Image.LANCZOS)
            canvas.paste(zeta_img, (zx, zy), zeta_img)
        else:
            draw.ellipse([zx + 2, zy + 2, zx + 26, zy + 26], fill="#f1c40f")
            
        draw.text((zx + 14, zy + 14), str(zetas), font=_get_font("bold", 12), fill=(255, 255, 255), anchor="mm")

    # Dessin des étoiles
    star_path = Path("assets/overlays/tex.charui_star_character.png")
    if star_path.exists():
        star = Image.open(star_path).convert("RGBA").resize((12, 12), Image.LANCZOS)
        start_x = x + (PORTRAIT_CELL - (7 * 10)) // 2 + 2
        sy = y + PORTRAIT_CELL - 10
        for i in range(7):
            canvas.paste(star, (start_x + (i * 10), sy), star)


def _draw_portrait_row(
    canvas: Image.Image,
    units: list[dict],
    y: int,
    is_enemy: bool = False,
) -> None:
    """Dessine une rangée de portraits alignés horizontalement."""
    x = PADDING
    for unit in units:
        _draw_portrait_cell(
            canvas=canvas,
            x=x,
            y=y,
            base_id=unit.get("base_id"),
            relic_tier=unit.get("relic_tier"),
            gear_tier=unit.get("gear_tier"),
            ready=unit.get("ready", True),
            owned=unit.get("owned", True),
            is_enemy=is_enemy,
            missing_omicron=unit.get("missing_omicron", False),
            is_ship=unit.get("combat_type") == 2,
            level=unit.get("level", 85),
        )
        x += PORTRAIT_CELL + PORTRAIT_GAP


# ---------------------------------------------------------------------------
# Calcul de la hauteur totale de l'image
# ---------------------------------------------------------------------------
def _compute_height(suggestions: list[dict]) -> int:
    height = H_HEADER + PADDING
    for _ in suggestions:
        height += (
            H_TEAM_LABEL
            + H_PORTRAIT_ROW     # équipe ennemie
            + H_COUNTER_LABEL
            + H_PORTRAIT_ROW     # contres
            + H_SEPARATOR
            + PADDING
        )
    height += PADDING
    return height


# ---------------------------------------------------------------------------
# Fonction principale
# ---------------------------------------------------------------------------
def generate_gac_report(
    my_name: str,
    enemy_name: str,
    suggestions: list[dict],
    fmt: str,
) -> discord.File:
    """
    Génère un rapport GAC sous forme d'image PNG et retourne un discord.File.

    Args:
        my_name:     Pseudo du joueur qui demande.
        enemy_name:  Pseudo de l'adversaire.
        suggestions: Liste de {enemy_team, counters} produite par gac_counter_engine.
        fmt:         '5v5' ou '3v3'.

    Returns:
        discord.File prêt à être envoyé dans un salon Discord.
    """
    height = _compute_height(suggestions)
    canvas = Image.new("RGBA", (IMG_WIDTH, height), C_BG)
    draw   = ImageDraw.Draw(canvas)

    # -----------------------------------------------------------------------
    # Header
    # -----------------------------------------------------------------------
    title_font    = _get_font("bold", 22)
    subtitle_font = _get_font("regular", 16)

    label = "5 contre 5" if fmt == "5v5" else "3 contre 3"
    draw.text((PADDING, 18), f"RAPPORT GAC — FORMAT {label.upper()}", font=title_font, fill=C_GOLD)
    vs_text = f"{my_name}  ⚔  {enemy_name}"
    draw.text((PADDING, 48), vs_text, font=subtitle_font, fill=C_TEXT)

    # Ligne de séparation sous le header
    y = H_HEADER
    draw.line([(0, y), (IMG_WIDTH, y)], fill=C_BORDER, width=1)
    y += PADDING

    # -----------------------------------------------------------------------
    # Sections par équipe
    # -----------------------------------------------------------------------
    medals      = ["#1", "#2", "#3", "#4", "#5"]
    team_font   = _get_font("bold", 16)
    label_font  = _get_font("regular", 14)
    small_font  = _get_font("regular", 12)

    for i, suggestion in enumerate(suggestions):
        team     = suggestion["enemy_team"]
        counters = suggestion["counters"]
        medal    = medals[i] if i < len(medals) else f"#{i+1}"

        # Fond de la section
        section_bottom = y + H_TEAM_LABEL + H_PORTRAIT_ROW + H_COUNTER_LABEL + H_PORTRAIT_ROW + PADDING
        draw.rounded_rectangle(
            [PADDING // 2, y - 4, IMG_WIDTH - PADDING // 2, section_bottom],
            radius=SECTION_RADIUS,
            fill=C_SECTION,
            outline=C_BORDER,
            width=1,
        )

        # --- Label équipe ennemie ---
        draw.text(
            (PADDING, y + 6),
            f"{medal}  Équipe ennemie  ·  {team['leader_name']}",
            font=team_font,
            fill=C_ENEMY,
        )
        y += H_TEAM_LABEL

        # --- Portraits ennemis (avec vrais tiers relic/gear si disponibles) ---
        enemy_units = []
        members_ids = team.get("members_base_ids", [])
        for i, m in enumerate(team["members"]):
            bid = members_ids[i] if i < len(members_ids) else base_id_from_name(m)
            unit_data = team.get("units_data", {}).get(bid.upper() if bid else "", {})
            enemy_units.append({
                "base_id":    bid,
                "relic_tier": unit_data.get("relic_tier"),
                "gear_tier":  unit_data.get("gear_tier"),
                "ready":      True,
                "owned":      True,
            })
        _draw_portrait_row(canvas, enemy_units, y, is_enemy=True)

        # Noms sous les portraits ennemis
        xe = PADDING
        for m in team["members"]:
            name_short = m[:12] + "…" if len(m) > 12 else m
            draw.text((xe, y + PORTRAIT_CELL + 4), name_short, font=small_font, fill=C_MUTED)
            xe += PORTRAIT_CELL + PORTRAIT_GAP
        y += H_PORTRAIT_ROW

        # --- Label contres ---
        nb_ready = sum(1 for c in counters if c.get("ready") and c.get("owned"))
        draw.text(
            (PADDING, y + 6),
            f"▶  Contres recommandés  ({nb_ready}/{len(counters)} prêts)",
            font=label_font,
            fill=C_READY if nb_ready > 0 else C_WARN,
        )
        y += H_COUNTER_LABEL

        # --- Portraits contres ---
        if counters:
            _draw_portrait_row(canvas, counters, y, is_enemy=False)
            xc = PADDING
            for c in counters:
                name_short = c["name"][:12] + "…" if len(c["name"]) > 12 else c["name"]
                color = C_READY if c.get("ready") and c.get("owned") else (C_WARN if c.get("owned") else C_MISSING)
                draw.text((xc, y + PORTRAIT_CELL + 4), name_short, font=small_font, fill=color)
                xc += PORTRAIT_CELL + PORTRAIT_GAP
        else:
            draw.text((PADDING, y + 20), "Aucun contre répertorié", font=label_font, fill=C_MUTED)

        y += H_PORTRAIT_ROW + PADDING + H_SEPARATOR

    # -----------------------------------------------------------------------
    # Export en buffer mémoire → discord.File
    # -----------------------------------------------------------------------
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return discord.File(buf, filename="gac_report.png")


def base_id_from_name(name: str) -> str | None:
    """Reverse lookup nom → base_id via STATIC_NAMES."""
    from services.unit_names import STATIC_NAMES
    for bid, n in STATIC_NAMES.items():
        if n == name:
            return bid
    return None
