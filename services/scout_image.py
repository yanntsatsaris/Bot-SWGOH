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

def generate_scout_map(zones: dict, quotas: dict, league: str, fmt: str, player_name: str, source: str, roster_index: dict = None) -> io.BytesIO:
    """
    Génère l'image PNG de la carte GAC scannée.
    """
    width = 1000 if fmt == "5v5" else 860
    
    north_teams = zones.get("North", [])
    south_teams = zones.get("South", [])
    back_teams = zones.get("Back", [])
    fleet_teams = zones.get("Fleet", [])
    
    # Calcul de la largeur fleet (capital + 3 fronts + 4 renforts)
    _cell_w = PORTRAIT_CELL + PORTRAIT_GAP
    _fleet_x_start = PADDING + 20
    _fleet_row_width = _cell_w + PORTRAIT_GAP * 3 + (3 * _cell_w) + PORTRAIT_GAP * 2 + (4 * _cell_w)
    _fleet_wraps = _fleet_row_width > (width - _fleet_x_start - PADDING)
    fleet_row_h = (PORTRAIT_CELL + 10) * 2 + 10 if _fleet_wraps else PORTRAIT_CELL + 20
    
    max_ns = max(len(north_teams), len(south_teams)) if north_teams or south_teams else 0
    
    height = 100 + PADDING
    if max_ns > 0:
        height += H_ZONE_TITLE + (max_ns * (PORTRAIT_CELL + 30)) + PADDING
    
    if back_teams:
        height += H_ZONE_TITLE + (len(back_teams) * (PORTRAIT_CELL + 30)) + PADDING
    if fleet_teams:
        height += H_ZONE_TITLE + (len(fleet_teams) * fleet_row_h) + PADDING
        
    canvas = Image.new("RGBA", (width, height), C_BG)
    draw = ImageDraw.Draw(canvas)
    
    # Header
    title_font = _get_font("bold", 22)
    sub_font = _get_font("regular", 16)
    
    draw.text((PADDING, 20), f"MAP GAC — {league} ({fmt})", font=title_font, fill=C_GOLD)
    draw.text((PADDING, 50), f"Joueur : {player_name}  |  Analyse : {source}", font=sub_font, fill=C_TEXT)
    
    def _draw_zone_team(t, x, y, is_fleet=False):
        leader_id = t.get("leader_id")
        members = t.get("members_ids", [])
        
        def get_unit_details(uid):
            if not uid or not roster_index or uid not in roster_index:
                return None, None, 0, 0
            u = roster_index[uid]
            return u.get("relic_tier"), u.get("gear_tier"), u.get("zetas", 0), u.get("omicrons", 0)
        
        if is_fleet:
            slots = 8
            cell_w = PORTRAIT_CELL + PORTRAIT_GAP
            fleet_row_width = cell_w + PORTRAIT_GAP * 3 + (3 * cell_w) + PORTRAIT_GAP * 2 + (4 * cell_w)
            wrap = fleet_row_width > (width - x - PADDING)

            _draw_portrait_cell(canvas, x, y, leader_id, None, None, True, True, True, False, is_ship=True)
            cx = x + PORTRAIT_CELL + PORTRAIT_GAP * 3
            drawn = 1
            row2_y = y + PORTRAIT_CELL + 10
            row2_x = x

            for m in members:
                if m != leader_id and drawn < slots:
                    if wrap and drawn == 4:
                        cx = row2_x
                    cur_y = row2_y if (wrap and drawn >= 4) else y
                    _draw_portrait_cell(canvas, cx, cur_y, m, None, None, True, True, True, False, is_ship=True)
                    cx += PORTRAIT_CELL + PORTRAIT_GAP
                    if drawn == 3 and not wrap:
                        cx += PORTRAIT_GAP * 2
                    drawn += 1

            while drawn < slots:
                if wrap and drawn == 4:
                    cx = row2_x
                cur_y = row2_y if (wrap and drawn >= 4) else y
                _draw_portrait_cell(canvas, cx, cur_y, None, None, None, True, True, True, False, is_ship=True)
                cx += PORTRAIT_CELL + PORTRAIT_GAP
                if drawn == 3 and not wrap:
                    cx += PORTRAIT_GAP * 2
                drawn += 1

            # Adjust x for source label
            x = cx
        else:
            slots = 3 if fmt == "3v3" else 5
            rel, gr, zetas, omis = get_unit_details(leader_id)
            _draw_portrait_cell(canvas, x, y, leader_id, rel, gr, True, True, True, False, is_ship=False, zetas=zetas, omicrons=omis)
            x += PORTRAIT_CELL + PORTRAIT_GAP
            drawn = 1
            for m in members:
                if m != leader_id and drawn < slots:
                    rel, gr, zetas, omis = get_unit_details(m)
                    _draw_portrait_cell(canvas, x, y, m, rel, gr, True, True, True, False, is_ship=False, zetas=zetas, omicrons=omis)
                    x += PORTRAIT_CELL + PORTRAIT_GAP
                    drawn += 1
            while drawn < slots:
                _draw_portrait_cell(canvas, x, y, None, None, None, True, True, True, False, is_ship=False)
                x += PORTRAIT_CELL + PORTRAIT_GAP
                drawn += 1
        
        team_source = t.get("source", "predictive")
        if "Historique" in team_source:
            source_label = team_source
            label_color = C_GOLD
        elif "Upgrade" in team_source:
            source_label = team_source
            label_color = "#b967ff"
        elif team_source == "leftover":
            source_label = "Leftover"
            label_color = C_MUTED
        elif team_source == "empty":
            source_label = "Vide"
            label_color = C_MUTED
        else:
            source_label = "Prédiction"
            label_color = C_MUTED
            
        draw.text((x + 20, y + PORTRAIT_CELL // 2 - 8), source_label, font=_get_font("bold", 13), fill=label_color)

    y_current = 100
    
    # NORTH and SOUTH in parallel
    if max_ns > 0:
        if north_teams:
            draw.text((PADDING, y_current), f"ZONE NORTH (Quota: {quotas.get('North', 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
        if south_teams:
            draw.text((width // 2, y_current), f"ZONE SOUTH (Quota: {quotas.get('South', 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
            
        for i in range(max_ns):
            y_team = y_current + H_ZONE_TITLE + (i * (PORTRAIT_CELL + 30))
            if i < len(north_teams):
                _draw_zone_team(north_teams[i], PADDING + 20, y_team)
            if i < len(south_teams):
                _draw_zone_team(south_teams[i], width // 2 + 20, y_team)
                
        y_current += H_ZONE_TITLE + (max_ns * (PORTRAIT_CELL + 30)) + PADDING

    # BACK
    if back_teams:
        draw.text((PADDING, y_current), f"ZONE BACK (Quota: {quotas.get('Back', 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
        for i, t in enumerate(back_teams):
            y_team = y_current + H_ZONE_TITLE + (i * (PORTRAIT_CELL + 30))
            _draw_zone_team(t, PADDING + 20, y_team)
        y_current += H_ZONE_TITLE + (len(back_teams) * (PORTRAIT_CELL + 30)) + PADDING

    # FLEET
    if fleet_teams:
        draw.text((PADDING, y_current), f"ZONE FLEET (Quota: {quotas.get('Fleet', 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
        for i, t in enumerate(fleet_teams):
            y_team = y_current + H_ZONE_TITLE + (i * fleet_row_h)
            _draw_zone_team(t, PADDING + 20, y_team, is_fleet=True)

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    out.seek(0)
    return out

def generate_attack_plan_image(attack_plan: dict, league: str, fmt: str, enemy_name: str, my_name: str, my_roster_index: dict = None) -> io.BytesIO:
    """
    Génère l'image PNG du Plan d'Attaque Global GAC.
    Affiche pour chaque zone et chaque slot l'équipe ennemie et en face le contre assigné.
    """
    width = 1100
    row_height = PORTRAIT_CELL + 35
    
    height = 100 + PADDING
    for zone, slots in attack_plan.items():
        if slots:
            height += H_ZONE_TITLE + (len(slots) * row_height) + PADDING
            
    canvas = Image.new("RGBA", (width, height), C_BG)
    draw = ImageDraw.Draw(canvas)
    
    title_font = _get_font("bold", 22)
    sub_font = _get_font("regular", 16)
    section_font = _get_font("bold", 18)
    label_font = _get_font("bold", 13)
    
    draw.text((PADDING, 20), f"PLAN D'ATTAQUE GLOBAL GAC — {league} ({fmt})", font=title_font, fill=C_GOLD)
    draw.text((PADDING, 50), f"Stratégie : {my_name} ⚔️ {enemy_name}", font=sub_font, fill=C_TEXT)
    
    current_y = 100
    
    for zone, slots in attack_plan.items():
        if not slots:
            continue
            
        draw.text((PADDING, current_y), f"ZONE : {zone.upper()}", font=section_font, fill=C_GOLD)
        current_y += H_ZONE_TITLE
        
        for slot in slots:
            s_idx = slot["slot_index"]
            e_team = slot["enemy_team"]
            c_info = slot["counter"]
            win_pct = slot["win_pct"]
            
            panel_rect = [PADDING, current_y, width - PADDING, current_y + row_height - 5]
            draw.rounded_rectangle(panel_rect, radius=SECTION_RADIUS, fill=C_SECTION, outline=C_BORDER, width=1)
            
            draw.text((PADDING + 15, current_y + 10), f"Slot #{s_idx} Ennemi", font=label_font, fill=C_ENEMY)
            
            e_leader = e_team.get("leader_id")
            e_members = e_team.get("members_ids", [])
            all_e_ids = [e_leader] + [m for m in e_members if m]
            
            x_def = PADDING + 15
            y_portraits = current_y + 28
            for bid in all_e_ids[: (3 if fmt == "3v3" else 5)]:
                _draw_portrait_cell(canvas, draw, bid, x_def, y_portraits, unit_data=None, is_leader=(bid == e_leader))
                x_def += PORTRAIT_CELL + PORTRAIT_GAP
                
            x_mid = x_def + 30
            draw.text((x_mid, current_y + 35), "⚔️", font=title_font, fill=C_GOLD)
            if c_info:
                draw.text((x_mid - 15, current_y + 65), f"{win_pct}% Win", font=label_font, fill=C_READY if win_pct >= 75 else C_TEXT)
            else:
                draw.text((x_mid - 20, current_y + 65), "Aucun contre", font=label_font, fill=C_ENEMY)
                
            x_counter = x_mid + 90
            draw.text((x_counter, current_y + 10), "Contre Réalisable", font=label_font, fill=C_READY)
            
            if c_info:
                c_leader = c_info["atk_leader_id"]
                c_members = c_info.get("atk_members_ids", [])
                all_c_ids = [c_leader] + [m for m in c_members if m]
                
                for bid in all_c_ids[: (3 if fmt == "3v3" else 5)]:
                    u_data = my_roster_index.get(bid.upper()) if my_roster_index else None
                    _draw_portrait_cell(canvas, draw, bid, x_counter, y_portraits, unit_data=u_data, is_leader=(bid == c_leader))
                    x_counter += PORTRAIT_CELL + PORTRAIT_GAP
            else:
                draw.text((x_counter, current_y + 40), "⚠️ Roster insuffisant pour cette équipe", font=sub_font, fill=C_MUTED)
                
            current_y += row_height
        current_y += PADDING

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    out.seek(0)
    return out
