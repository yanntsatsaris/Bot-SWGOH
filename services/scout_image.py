"""
services/scout_image.py — Génère la carte GAC (Scouting)
"""
import io
import logging
from PIL import Image, ImageDraw

from services.image_generator import (
    C_BG, C_SECTION, C_BORDER, C_GOLD, C_TEXT, C_MUTED, C_ENEMY, C_READY, C_WARN,
    PORTRAIT_CELL, PORTRAIT_GAP, SECTION_RADIUS, PADDING, IMG_WIDTH,
    _get_font, _draw_portrait_cell
)

log = logging.getLogger(__name__)

H_ZONE_TITLE = 40

# Taille adaptative selon le format : en 5v5, les portraits sont plus petits pour tenir sur la largeur
_CELL_5V5 = 72   # cellule portrait en 5v5 (vs 88px en 3v3)
_GAP_5V5  = 6    # espacement portrait en 5v5 (vs 8px en 3v3)

def generate_scout_map(zones: dict, quotas: dict, league: str, fmt: str, player_name: str, source: str, roster_index: dict = None, is_player: bool = False) -> io.BytesIO:
    """
    Génère l'image PNG de la carte GAC scanned.
    """
    # Dimensions et tailles adaptatives selon le format
    is_5v5 = fmt == "5v5"
    cell = _CELL_5V5 if is_5v5 else PORTRAIT_CELL
    gap  = _GAP_5V5  if is_5v5 else PORTRAIT_GAP
    # En 5v5, le canvas est élargi (1360px) pour accueillir 5 persos + Datacron + Label Historique sans chevauchement
    width = 1360 if is_5v5 else 900
    
    north_teams = zones.get("North", [])
    south_teams = zones.get("South", [])
    back_teams = zones.get("Back", [])
    fleet_teams = zones.get("Fleet", [])
    
    # Calcul de la largeur fleet (capital + 3 fronts + 4 renforts)
    _cell_w = cell + gap
    _fleet_x_start = PADDING + 20
    _fleet_row_width = _cell_w + gap * 3 + (3 * _cell_w) + gap * 2 + (4 * _cell_w)
    _fleet_wraps = _fleet_row_width > (width - _fleet_x_start - PADDING)
    fleet_row_h = (cell + 10) * 2 + 10 if _fleet_wraps else cell + 20
    
    max_ns = max(len(north_teams), len(south_teams)) if north_teams or south_teams else 0
    team_row_h = cell + 30  # hauteur d'une ligne d'équipe (portrait + étoiles + marge)
    
    height = 100 + PADDING
    if max_ns > 0:
        height += H_ZONE_TITLE + (max_ns * team_row_h) + PADDING
    
    if back_teams:
        height += H_ZONE_TITLE + (len(back_teams) * team_row_h) + PADDING
    if fleet_teams:
        height += H_ZONE_TITLE + (len(fleet_teams) * fleet_row_h) + PADDING
        
    canvas = Image.new("RGBA", (width, height), C_BG)
    draw = ImageDraw.Draw(canvas)
    datacrons_to_overlay = []
    
    # Header
    title_font = _get_font("bold", 22)
    sub_font = _get_font("regular", 16)
    
    draw.text((PADDING, 20), f"MAP GAC — {league} ({fmt})", font=title_font, fill=C_GOLD)
    draw.text((PADDING, 50), f"Joueur : {player_name}  |  Analyse : {source}", font=sub_font, fill=C_TEXT)
    
    def _draw_zone_team(t, x, y, is_fleet=False):
        """Dessine une équipe (leader + membres) à la position (x, y). Retourne le x final."""
        nonlocal cell, gap
        leader_id = t.get("leader_id")
        members = t.get("members_ids", [])
        cur_x = x
        
        def get_unit_details(uid):
            if not uid or not roster_index or uid.upper() not in roster_index:
                return None, None, 0, 0, 7
            u = roster_index[uid.upper()]
            return u.get("relic_tier"), u.get("gear_tier"), u.get("zetas", 0), u.get("omicrons", 0), u.get("rarity", 7)
        
        def _draw_scaled(cvs, px, py, uid, rel, gr, ready_, owned_, enemy_, miss_omi, ship_, zts=0, omis=0, stars_=7):
            """Dessine un portrait redimensionné à 'cell' px via un canvas temporaire."""
            if cell == PORTRAIT_CELL:
                # Taille native : appel direct
                _draw_portrait_cell(cvs, px, py, uid, rel, gr, ready_, owned_, enemy_, miss_omi, ship_, zetas=zts, omicrons=omis, stars=stars_)
            else:
                # Taille réduite : on dessine dans un canvas temporaire PORTRAIT_CELL×PORTRAIT_CELL puis on redimensionne
                tmp = Image.new("RGBA", (PORTRAIT_CELL, PORTRAIT_CELL + 16), C_BG)  # +16 pour les étoiles
                _draw_portrait_cell(tmp, 0, 0, uid, rel, gr, ready_, owned_, enemy_, miss_omi, ship_, zetas=zts, omicrons=omis, stars=stars_)
                scaled = tmp.resize((cell, cell + int(cell * 16 / PORTRAIT_CELL)), Image.LANCZOS)
                cvs.paste(scaled, (px, py), scaled)
        
        if is_fleet:
            slots = 8
            cell_w = cell + gap
            fleet_row_width = cell_w + gap * 3 + (3 * cell_w) + gap * 2 + (4 * cell_w)
            wrap = fleet_row_width > (width - cur_x - PADDING)

            f_rel, f_gr, f_zts, f_omis, f_star = get_unit_details(leader_id)
            _draw_scaled(canvas, cur_x, y, leader_id, f_rel, f_gr, True, True, not is_player, False, True, zts=f_zts, omis=f_omis, stars_=f_star)
            cx = cur_x + cell + gap * 3
            drawn = 1
            row2_y = y + cell + 10
            row2_x = cur_x

            for m in members:
                if m != leader_id and drawn < slots:
                    if wrap and drawn == 4:
                        cx = row2_x
                    cur_y = row2_y if (wrap and drawn >= 4) else y
                    m_rel, m_gr, m_zts, m_omis, m_star = get_unit_details(m)
                    _draw_scaled(canvas, cx, cur_y, m, m_rel, m_gr, True, True, not is_player, False, True, zts=m_zts, omis=m_omis, stars_=m_star)
                    cx += cell + gap
                    if drawn == 3 and not wrap:
                        cx += gap * 2
                    drawn += 1

            while drawn < slots:
                if wrap and drawn == 4:
                    cx = row2_x
                cur_y = row2_y if (wrap and drawn >= 4) else y
                _draw_scaled(canvas, cx, cur_y, None, None, None, True, True, not is_player, False, True)
                cx += cell + gap
                if drawn == 3 and not wrap:
                    cx += gap * 2
                drawn += 1

            cur_x = cx
        else:
            slots = 3 if fmt == "3v3" else 5
            rel, gr, zetas, omis, stars = get_unit_details(leader_id)
            _draw_scaled(canvas, cur_x, y, leader_id, rel, gr, True, True, not is_player, False, False, zts=zetas, omis=omis, stars_=stars)
            cur_x += cell + gap
            drawn = 1
            for m in members:
                if m != leader_id and drawn < slots:
                    rel, gr, zetas, omis, stars = get_unit_details(m)
                    _draw_scaled(canvas, cur_x, y, m, rel, gr, True, True, not is_player, False, False, zts=zetas, omis=omis, stars_=stars)
                    cur_x += cell + gap
                    drawn += 1
            while drawn < slots:
                _draw_scaled(canvas, cur_x, y, None, None, None, True, True, True, False, False)
                cur_x += cell + gap
                drawn += 1

        # Mémorisation du badge Datacron pour incrustation HD native
        dtc = t.get("datacron")
        if dtc and not is_fleet:
            datacrons_to_overlay.append((cur_x + 4, y, dtc, cell))
            cur_x += cell + gap + 4
        
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
            
        draw.text((cur_x + 8, y + cell // 2 - 8), source_label, font=_get_font("bold", 11 if is_5v5 else 13), fill=label_color)

    y_current = 100
    
    # NORTH and SOUTH in parallel
    if max_ns > 0:
        if north_teams:
            draw.text((PADDING, y_current), f"ZONE NORTH (Quota: {quotas.get('North', 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
        if south_teams:
            draw.text((width // 2, y_current), f"ZONE SOUTH (Quota: {quotas.get('South', 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
            
        for i in range(max_ns):
            y_team = y_current + H_ZONE_TITLE + (i * team_row_h)
            if i < len(north_teams):
                _draw_zone_team(north_teams[i], PADDING + 10, y_team)
            if i < len(south_teams):
                _draw_zone_team(south_teams[i], width // 2 + 10, y_team)
                
        y_current += H_ZONE_TITLE + (max_ns * team_row_h) + PADDING

    # BACK
    if back_teams:
        draw.text((PADDING, y_current), f"ZONE BACK (Quota: {quotas.get('Back', 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
        for i, t in enumerate(back_teams):
            y_team = y_current + H_ZONE_TITLE + (i * team_row_h)
            _draw_zone_team(t, PADDING + 10, y_team)
        y_current += H_ZONE_TITLE + (len(back_teams) * team_row_h) + PADDING

    # FLEET
    if fleet_teams:
        draw.text((PADDING, y_current), f"ZONE FLEET (Quota: {quotas.get('Fleet', 0)})", font=_get_font("bold", 18), fill=C_ENEMY)
        for i, t in enumerate(fleet_teams):
            y_team = y_current + H_ZONE_TITLE + (i * fleet_row_h)
            _draw_zone_team(t, PADDING + 10, y_team, is_fleet=True)

    # Suréchantillonnage 2x LANCZOS pour affichage Retina HD net sur mobile
    canvas_hd = canvas.resize((canvas.width * 2, canvas.height * 2), Image.LANCZOS)

    # Incrustation des Badges Datacrons en Ultra HD 2x Native (Vector-Sharp)
    from services.datacron_renderer import render_datacron_badge
    for (ox, oy, dtc_info, dtc_cell) in datacrons_to_overlay:
        try:
            lvl = dtc_info.get("level") or (len(dtc_info.get("affix", [])) if "affix" in dtc_info else 3)
            is_foc = dtc_info.get("is_focused", False)
            char_id = dtc_info.get("character_base_id") or dtc_info.get("target_unit_id")
            cube_tex = dtc_info.get("cube_texture_url") or dtc_info.get("icon_url")
            
            hd_size = dtc_cell * 2
            badge_hd = render_datacron_badge(
                level=lvl,
                max_tiers=dtc_info.get("max_tiers"),
                is_focused=is_foc,
                character_base_id=char_id,
                character_icon_url=dtc_info.get("character_icon_url"),
                cube_texture_url=cube_tex,
                size=(hd_size, hd_size)
            )
            canvas_hd.paste(badge_hd, (ox * 2, oy * 2), badge_hd)
        except Exception as e:
            log.warning("Erreur rendu badge Datacron Retina 2x: %s", e)

    out = io.BytesIO()
    canvas_hd.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out

def generate_attack_plan_image(attack_plan: dict, league: str, fmt: str, enemy_name: str, my_name: str, my_roster_index: dict = None, enemy_roster_index: dict = None) -> io.BytesIO:
    """
    Génère l'image PNG du Plan d'Attaque Global GAC (Retina HD).
    Affiche pour chaque zone et chaque slot l'équipe ennemie et en face le contre assigné.
    """
    is_5v5 = fmt == "5v5"
    # En 5v5 : portraits réduits (72px) et canvas élargi (1360px) pour tenir 5+DTC + séparateur + 5+DTC
    p_cell = _CELL_5V5 if is_5v5 else PORTRAIT_CELL  # 72 ou 88
    p_gap  = _GAP_5V5  if is_5v5 else PORTRAIT_GAP   # 6 ou 8
    width  = 1360 if is_5v5 else 1150
    slots_per_row = 5 if is_5v5 else 3
    # Hauteur d'une ligne : portrait + labels ("Slot #N Ennemi" + étoiles)
    row_height = p_cell + 50
    
    height = 100 + PADDING
    for zone, slots in attack_plan.items():
        if slots:
            height += H_ZONE_TITLE + (len(slots) * row_height) + PADDING
            
    canvas = Image.new("RGBA", (width, height), C_BG)
    draw = ImageDraw.Draw(canvas)
    datacrons_to_overlay = []
    
    title_font = _get_font("bold", 22)
    sub_font = _get_font("regular", 16)
    section_font = _get_font("bold", 18)
    label_font = _get_font("bold", 13)
    
    draw.text((PADDING, 20), f"PLAN D'ATTAQUE GLOBAL GAC — {league} ({fmt})", font=title_font, fill=C_GOLD)
    draw.text((PADDING, 50), f"Stratégie : {my_name} ⚔️ {enemy_name}", font=sub_font, fill=C_TEXT)

    def _draw_scaled_cell(cvs, px, py, uid, rel, gr, ready_, owned_, enemy_, miss_omi, ship_=False, lvl=85, zts=0, omis=0, stars_=7):
        """Dessine un portrait redimensionné à p_cell px si nécessaire."""
        if p_cell == PORTRAIT_CELL:
            _draw_portrait_cell(cvs, px, py, uid, rel, gr, ready_, owned_, enemy_, miss_omi, ship_, lvl, zts, omis, stars_)
        else:
            tmp = Image.new("RGBA", (PORTRAIT_CELL, PORTRAIT_CELL + 16), C_BG)
            _draw_portrait_cell(tmp, 0, 0, uid, rel, gr, ready_, owned_, enemy_, miss_omi, ship_, lvl, zts, omis, stars_)
            scaled = tmp.resize((p_cell, p_cell + int(p_cell * 16 / PORTRAIT_CELL)), Image.LANCZOS)
            cvs.paste(scaled, (px, py), scaled)
    
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
            status = slot.get("status", "OPEN")
            offset = slot.get("counter_offset", 0)
            
            panel_fill = (18, 20, 26) if status == "CLEARED" else C_SECTION
            panel_border = C_READY if status == "CLEARED" else (C_ENEMY if status == "FAILED" else C_BORDER)
            
            panel_rect = [PADDING, current_y, width - PADDING, current_y + row_height - 6]
            draw.rounded_rectangle(panel_rect, radius=SECTION_RADIUS, fill=panel_fill, outline=panel_border, width=2 if status != "OPEN" else 1)
            
            # Label secteur + badge statut
            if status == "CLEARED":
                draw.text((PADDING + 15, current_y + 10), f"Slot #{s_idx} Ennemi — ✔ TOMBÉ", font=label_font, fill=C_READY)
            elif status == "FAILED":
                draw.text((PADDING + 15, current_y + 10), f"Slot #{s_idx} Ennemi — ⚠ ÉCHEC", font=label_font, fill=C_ENEMY)
            else:
                draw.text((PADDING + 15, current_y + 10), f"Slot #{s_idx} Ennemi", font=label_font, fill=C_ENEMY)
            
            e_leader = e_team.get("leader_id")
            e_members = e_team.get("members_ids", [])
            all_e_ids = [e_leader] + [m for m in e_members if m]
            
            x_def = PADDING + 15
            y_portraits = current_y + 24
            for bid in all_e_ids[:slots_per_row]:
                e_data = enemy_roster_index.get(bid.upper()) if enemy_roster_index else None
                e_rel  = e_data.get("relic_tier") if e_data else None
                e_gr   = e_data.get("gear_tier")  if e_data else None
                e_zts  = e_data.get("zetas", 0)   if e_data else 0
                e_omis = e_data.get("omicrons", 0) if e_data else 0
                e_star = e_data.get("rarity", 7)  if e_data else 7
                e_lvl  = e_data.get("level", 85)   if e_data else 85
                _draw_scaled_cell(canvas, x_def, y_portraits, bid, e_rel, e_gr, True, True, True, False, False, e_lvl, e_zts, e_omis, e_star)
                if status == "CLEARED":
                    overlay = Image.new("RGBA", (p_cell, p_cell), (0, 0, 0, 160))
                    canvas.paste(overlay, (x_def, y_portraits), overlay)
                x_def += p_cell + p_gap

            # Incrustation du Datacron ennemi si présent
            e_dtc = e_team.get("datacron")
            if e_dtc and status != "CLEARED":
                datacrons_to_overlay.append((x_def + 4, y_portraits, e_dtc, p_cell))
                x_def += p_cell + p_gap + 4
                
            x_mid = x_def + 20
            mid_y_icon  = current_y + max(24, row_height // 2 - 18)
            mid_y_label = mid_y_icon + 28
            if status == "CLEARED":
                # Badge circulaire vert avec coche '✔' (100% compatible toute police / OS)
                badge_radius = 12
                bx = x_mid + 10
                by = mid_y_icon + 10
                draw.ellipse([bx - badge_radius, by - badge_radius, bx + badge_radius, by + badge_radius], fill=(34, 197, 94))
                check_font = _get_font("bold", 15)
                draw.text((bx - 5, by - 10), "✔", font=check_font, fill=(255, 255, 255))
                draw.text((x_mid - 8, mid_y_label), "Victoire", font=label_font, fill=C_READY)
            else:
                swords_font = _get_font("bold", 20)
                draw.text((x_mid + 2, mid_y_icon - 2), "⚔", font=swords_font, fill=C_GOLD)
                if c_info:
                    w_col = C_READY if win_pct >= 70 else (C_WARN if win_pct >= 40 else C_ENEMY)
                    draw.text((x_mid - 15, mid_y_label), f"{win_pct}% Win", font=label_font, fill=w_col)
                else:
                    draw.text((x_mid - 20, mid_y_label), "Aucun contre", font=label_font, fill=C_ENEMY)
                
            x_counter = x_mid + 80
            opt_str = f" (Option #{offset + 1})" if offset > 0 else ""
            c_missing = [m.upper() for m in c_info.get("missing_omicron", [])] if c_info else []
            omi_warn_str = " (⚠️ Sans Omi)" if c_missing else ""

            if status == "CLEARED":
                draw.text((x_counter, current_y + 10), "Secteur Vaincu", font=label_font, fill=C_MUTED)
                draw.text((x_counter, current_y + 30), "✔ Territoire libéré", font=sub_font, fill=C_READY)
            elif status == "FAILED":
                draw.text((x_counter, current_y + 10), f"Contre de Rattrapage{opt_str}{omi_warn_str}", font=label_font, fill=C_ENEMY)
            elif not c_info:
                draw.text((x_counter, current_y + 10), "Aucun Contre Dispo", font=label_font, fill=C_ENEMY)
            elif win_pct < 40:
                draw.text((x_counter, current_y + 10), f"⚠️ Contre Risqué{opt_str}{omi_warn_str}", font=label_font, fill=C_WARN)
            elif win_pct < 70:
                draw.text((x_counter, current_y + 10), f"Contre Possible{opt_str}{omi_warn_str}", font=label_font, fill=C_TEXT)
            else:
                draw.text((x_counter, current_y + 10), f"Contre Recommandé{opt_str}{omi_warn_str}", font=label_font, fill=C_READY)
            
            if status != "CLEARED":
                if c_info:
                    c_leader = c_info["atk_leader_id"]
                    c_members = c_info.get("atk_members_ids", [])
                    all_c_ids = [c_leader] + [m for m in c_members if m]
                    
                    for bid in all_c_ids[:slots_per_row]:
                        u_data = my_roster_index.get(bid.upper()) if my_roster_index else None
                        rel    = u_data.get("relic_tier") if u_data else None
                        gr     = u_data.get("gear_tier")  if u_data else None
                        zts    = u_data.get("zetas", 0)   if u_data else 0
                        omis   = u_data.get("omicrons", 0) if u_data else 0
                        owned  = u_data is not None
                        rarity = u_data.get("rarity", 0)  if u_data else 0
                        lvl    = u_data.get("level", 85)   if u_data else 85
                        is_ready = owned and rarity == 7 and ((rel or 0) > 0 or (gr or 0) >= 12)
                        is_miss_omi = bid.upper() in c_missing
                        _draw_scaled_cell(canvas, x_counter, y_portraits, bid, rel, gr, is_ready, owned, False, is_miss_omi, False, lvl, zts, omis, rarity)
                        x_counter += p_cell + p_gap

                    # Incrustation du Datacron d'attaque si assigné
                    c_dtc = c_info.get("datacron")
                    if c_dtc:
                        datacrons_to_overlay.append((x_counter + 4, y_portraits, c_dtc, p_cell))
                        x_counter += p_cell + p_gap + 4
                else:
                    draw.text((x_counter, current_y + 36), "⚠️ Roster insuffisant pour cette équipe", font=sub_font, fill=C_MUTED)
                
            current_y += row_height

        current_y += PADDING


    canvas_hd = canvas.resize((canvas.width * 2, canvas.height * 2), Image.LANCZOS)

    # Incrustation des Badges Datacrons en Ultra HD 2x Native
    from services.datacron_renderer import render_datacron_badge
    for (ox, oy, dtc_info, dtc_cell) in datacrons_to_overlay:
        try:
            lvl = dtc_info.get("level") or (len(dtc_info.get("affix", [])) if "affix" in dtc_info else 3)
            is_foc = dtc_info.get("is_focused", False)
            char_id = dtc_info.get("character_base_id") or dtc_info.get("target_unit_id")
            cube_tex = dtc_info.get("cube_texture_url") or dtc_info.get("icon_url")
            
            hd_size = dtc_cell * 2
            badge_hd = render_datacron_badge(
                level=lvl,
                max_tiers=dtc_info.get("max_tiers"),
                is_focused=is_foc,
                character_base_id=char_id,
                character_icon_url=dtc_info.get("character_icon_url"),
                cube_texture_url=cube_tex,
                size=(hd_size, hd_size)
            )
            canvas_hd.paste(badge_hd, (ox * 2, oy * 2), badge_hd)
        except Exception as e:
            log.warning("Erreur rendu badge Datacron planneur Retina 2x: %s", e)

    out = io.BytesIO()
    canvas_hd.save(out, format="PNG", optimize=True)
    out.seek(0)
    return out

