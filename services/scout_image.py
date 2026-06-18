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

def generate_scout_map(zones: dict, quotas: dict, league: str, fmt: str, player_name: str, source: str) -> io.BytesIO:
    """
    Génère l'image PNG de la carte GAC scannée.
    """
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
    
    draw.text((PADDING, 20), f"MAP GAC — {league} ({fmt})", font=title_font, fill=C_GOLD)
    draw.text((PADDING, 50), f"Joueur : {player_name}  |  Analyse : {source}", font=sub_font, fill=C_TEXT)
    
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
            
            if zname == "Fleet":
                # Dessine 1 capital, espace, 3 ligne de front, espace, 4 renforts (total 8 max)
                slots = 8
                # Capital
                _draw_portrait_cell(canvas, x, y, leader_id, None, None, True, True, True)
                x += PORTRAIT_CELL + PORTRAIT_GAP * 3
                
                # Membres
                for i in range(1, slots): # skip leader (index 0 if it was in members, but actually members includes leader in our fleet list)
                    member_id = members[i] if i < len(members) else None
                    if member_id == leader_id and member_id is not None:
                        continue # Evite le doublon si le leader est déjà dans la liste
                        
                    _draw_portrait_cell(canvas, x, y, member_id, None, None, True, True, True)
                    x += PORTRAIT_CELL + PORTRAIT_GAP
                    if i == 3: # Espace après les 3 fronts
                        x += PORTRAIT_GAP * 2
            else:
                slots = 3 if fmt == "3v3" else 5
                
                # Leader
                _draw_portrait_cell(canvas, x, y, leader_id, None, None, True, True, True)
                x += PORTRAIT_CELL + PORTRAIT_GAP
                
                # Autres membres
                drawn = 1
                for m in members:
                    if m != leader_id and drawn < slots:
                        _draw_portrait_cell(canvas, x, y, m, None, None, True, True, True)
                        x += PORTRAIT_CELL + PORTRAIT_GAP
                        drawn += 1
                        
                # Compléter avec des vides
                while drawn < slots:
                    _draw_portrait_cell(canvas, x, y, None, None, None, True, True, True)
                    x += PORTRAIT_CELL + PORTRAIT_GAP
                    drawn += 1

            y += PORTRAIT_CELL + 10
            
        y += PADDING
        
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf
