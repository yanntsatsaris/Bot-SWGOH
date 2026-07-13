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
) -> None:
    """
    Dessine une cellule portrait (fond + image circulaire + badge de niveau).

    Args:
        canvas:     Image PIL de destination.
        x, y:       Coin supérieur gauche de la cellule.
        base_id:    Base ID du personnage.
        relic_tier: Tier de relique (1-9) ou None.
        gear_tier:  Tier de gear (1-13) ou None.
        ready:      Unité prête pour le GAC (R5+ / G13+).
        owned:      Le joueur possède l'unité.
        is_enemy:   True pour les unités ennemies.
    """
    draw = ImageDraw.Draw(canvas)

    # Couleur de la bordure
    if is_enemy:
        border_color = C_ENEMY
    elif not owned:
        border_color = C_MISSING
    elif ready:
        border_color = C_READY
    else:
        border_color = C_WARN

    # Fond circulaire
    draw.ellipse(
        [x, y, x + PORTRAIT_CELL - 1, y + PORTRAIT_CELL - 1],
        fill=C_SECTION,
        outline=border_color,
        width=3,
    )

    # Portrait
    portrait = _load_portrait(base_id)
    portrait.putalpha(_circle_mask(PORTRAIT_SIZE))
    offset = (PORTRAIT_CELL - PORTRAIT_SIZE) // 2
    canvas.paste(portrait, (x + offset, y + offset), portrait)

    # Overlay semi-transparent si non possédé
    if not owned and not is_enemy:
        overlay = Image.new("RGBA", (PORTRAIT_CELL, PORTRAIT_CELL), (0, 0, 0, 0))
        ov_draw = ImageDraw.Draw(overlay)
        ov_draw.ellipse(
            [0, 0, PORTRAIT_CELL - 1, PORTRAIT_CELL - 1],
            fill=(0, 0, 0, 150),
        )
        canvas.paste(overlay, (x, y), overlay)

    # Badge de niveau (bas-gauche)
    badge_font = _get_font("bold", 11)
    if relic_tier and relic_tier >= 1:
        badge_text  = f"R{relic_tier}"
        badge_color = C_READY if relic_tier >= 5 else C_WARN
    elif gear_tier and gear_tier >= 1:
        badge_text  = f"G{gear_tier}"
        badge_color = C_READY if gear_tier >= 13 else C_WARN
    else:
        badge_text  = None
        badge_color = C_MISSING

    if badge_text:
        bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        bw = bbox[2] - bbox[0] + 8
        bh = bbox[3] - bbox[1] + 4
        bx = x + 2
        by = y + PORTRAIT_CELL - bh - 2
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3, fill=badge_color)
        draw.text((bx + 4, by + 2), badge_text, font=badge_font, fill=(0, 0, 0))


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
