"""
services/scout_image.py — Génère la carte GAC (Scouting)
"""
import io
import logging
from PIL import Image, ImageDraw

from services.image_generator import (
    C_BG, C_SECTION, C_BORDER, C_GOLD, C_TEXT, C_MUTED, C_ENEMY, C_READY,
    PORTRAIT_CELL, PORTRAIT_GAP, SECTION_RADIUS, PADDING, IMG_WIDTH,
    _get_font, _draw_portrait_cell
)

log = logging.getLogger(__name__)

H_ZONE_TITLE = 40

def generate_scout_map(scout_data: dict) -> io.BytesIO:
    """
    Génère l'image PNG de la carte GAC scannée.
    """
    zones = scout_data["zones"]
    quotas = scout_data["quotas"]
    
    # Hauteur dynamique
    height = 100 + PADDING # Header
    
    for zname in ["North", "South", "Back", "Fleet"]:
        teams = zones.get(zname, [])
        height += H_ZONE_TITLE
        for t in teams:
            height += PORTRAIT_CELL + 20
        height += PADDING
        
    canvas = Image.new("RGBA", (IMG_WIDTH, height), C_BG)
    draw = ImageDraw.Draw(canvas)
    
    # Header
    title_font = _get_font("bold", 22)
    sub_font = _get_font("regular", 16)
    
    draw.text((PADDING, 20), f"SCOUTING GAC — {scout_data['league']} ({scout_data['format']})", font=title_font, fill=C_GOLD)
    draw.text((PADDING, 50), f"Adversaire : {scout_data['enemy_name']}  |  Source : {scout_data['source']}", font=sub_font, fill=C_TEXT)
    
    y = 100
    
    # Zones
    for zname in ["North", "South", "Back", "Fleet"]:
        teams = zones.get(zname, [])
        if not teams:
            continue
            
        draw.text((PADDING, y), f"ZONE {zname.upper()} (Quota: {quotas.get(zname, 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
        y += H_ZONE_TITLE
        
        for idx, t in enumerate(teams):
            leader_id = t.get("leader_id")
            members = t.get("members_ids", [])
            
            x = PADDING + 20
            
            # Dessiner le leader
            if leader_id:
                _draw_portrait_cell(canvas, x, y, leader_id, None, None, True, True, True)
                x += PORTRAIT_CELL + PORTRAIT_GAP
            
            # Dessiner les membres
            for m in members:
                if m != leader_id:
                    _draw_portrait_cell(canvas, x, y, m, None, None, True, True, True)
                    x += PORTRAIT_CELL + PORTRAIT_GAP
                    
            y += PORTRAIT_CELL + 10
            
        y += PADDING
        
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf
