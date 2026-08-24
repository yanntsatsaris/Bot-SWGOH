"""
scripts/datacrons_sb_worker.py — Worker SeleniumBase pour scrapper les Datacrons (Sets, Variantes, Paliers L1-L15) depuis swgoh.gg
"""
import sys
import os
import platform
import json
import logging
import re
from bs4 import BeautifulSoup
from seleniumbase import SB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("datacrons_worker")

def clean_character_id_from_url(url_or_thumb: str) -> str:
    """Extrait le base_id ou nom de perso propre depuis une URL ou thumbnail."""
    if not url_or_thumb:
        return ""
    # Ex: /units/colonel-ward/ -> COLONELWARD
    if "/units/" in url_or_thumb:
        slug = url_or_thumb.split("/units/")[1].split("/")[0]
        return slug.replace("-", "").upper()
    # Ex: https://game-assets.swgoh.gg/textures/tex.charui_colonelward.png -> COLONELWARD
    name = url_or_thumb.split("/")[-1].replace(".png", "")
    name = re.sub(r"^tex\.charui_", "", name)
    name = re.sub(r"^charui_", "", name)
    return name.replace("-", "").replace("_", "").upper()

def scrape_datacrons(output_json_path: str) -> bool:
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if not os.path.exists(project_dir):
        project_dir = os.getcwd()
        
    is_windows = (platform.system() == "Windows")
    if not is_windows:
        os.environ["HOME"] = project_dir
        os.environ["XDG_CONFIG_HOME"] = os.path.join(project_dir, ".config")
    
    display = None
    index_url = "https://swgoh.gg/datacrons/"
    log.info(f"Ouverture de l'index Datacrons : {index_url} avec SeleniumBase...")
    
    try:
        profile_dir = os.path.join(project_dir, "chrome_profile")
        
        # Nettoyer les verrous résiduels éventuels de Chrome sur Linux
        for lock_file in ["SingletonLock", "SingletonSocket", "SingletonCookie"]:
            lf_path = os.path.join(profile_dir, lock_file)
            if os.path.exists(lf_path):
                try:
                    os.remove(lf_path)
                except Exception:
                    pass

        if not is_windows:
            try:
                from pyvirtualdisplay import Display
                display = Display(visible=0, size=(1920, 1080))
                display.start()
            except Exception as e:
                log.warning(f"pyvirtualdisplay non démarré: {e}")

        all_sets_data = []

        with SB(uc=True, headless=False, user_data_dir=profile_dir) as sb:
            # 1. Scraping de l'index des sets
            sb.uc_open_with_reconnect(index_url, reconnect_time=3)
            
            # Vérification Cloudflare Turnstile
            quick_check = sb.get_page_source()
            if any(cf in quick_check for cf in ["Just a moment", "Un instant", "cf-turnstile", "Checking your browser"]):
                try:
                    sb.uc_gui_click_captcha()
                except Exception:
                    pass
                sb.sleep(8)
            else:
                sb.sleep(2)

            html = sb.get_page_source()
            soup = BeautifulSoup(html, "html.parser")
            
            set_cards = soup.find_all("a", href=re.compile(r"/datacrons/\d+/"))
            log.info(f"Trouvé {len(set_cards)} sets de Datacrons sur l'index.")
            
            parsed_sets = []
            seen_set_ids = set()

            for card in set_cards:
                href = card.get("href", "")
                m = re.search(r"/datacrons/(\d+)/", href)
                if not m:
                    continue
                set_id = int(m.group(1))
                if set_id in seen_set_ids:
                    continue
                seen_set_ids.add(set_id)

                # Nom du set
                name_elem = card.find(class_=re.compile(r"font-bold"))
                set_name = name_elem.get_text(strip=True) if name_elem else f"Set {set_id}"
                
                # Expiration
                exp_elem = card.find("time", class_="js-gg-time-diff-app")
                expiration_date = exp_elem.get("datetime") if exp_elem else None
                
                # Statut actif
                card_text = card.get_text()
                is_active = ("Active" in card_text) or bool(card.find(class_="text-success"))

                # Icône du cube
                icon_img = card.find("img", class_="datacron-icon__box-img")
                icon_url = icon_img.get("src") if icon_img else ""

                parsed_sets.append({
                    "set_id": set_id,
                    "name": set_name,
                    "expiration_date": expiration_date,
                    "is_active": is_active,
                    "icon_url": icon_url,
                    "url": f"https://swgoh.gg/datacrons/{set_id}/",
                    "templates": []
                })

            log.info(f"Détail des sets identifiés : {[s['set_id'] for s in parsed_sets]}")

            # Filtrer UNIQUEMENT les sets actifs (généralement 3 ou 4 sets)
            active_sets = [s for s in parsed_sets if s["is_active"]]
            if not active_sets:
                log.warning("Aucun set tagué 'Active' trouvé avec certitude, limitation aux 4 sets les plus récents.")
                active_sets = parsed_sets[:4]

            log.info(f"🎯 Sets ACTIFS à scrapper ({len(active_sets)}) : {[s['set_id'] for s in active_sets]}")

            # 2. Explorer chaque set ACTIF pour extraire les templates et tiers
            for s_info in active_sets:
                set_id = s_info["set_id"]
                set_url = s_info["url"]
                log.info(f"--- Analyse du Set ACTIF {set_id} ({s_info['name']}) : {set_url} ---")
                
                sb.open(set_url)
                sb.sleep(2)
                
                set_html = sb.get_page_source()
                set_soup = BeautifulSoup(set_html, "html.parser")

                # Récupération des templates / variantes
                template_links = []
                # Template de base
                base_tpl_id = f"datacron_set_{set_id}_base"
                template_links.append((base_tpl_id, set_url, False, None, None, 9))

                # Chercher les variantes et focused datacrons
                focused_anchors = set_soup.find_all("a", href=re.compile(r"template_id="))
                for a in focused_anchors:
                    t_href = a.get("href", "")
                    m_tpl = re.search(r"template_id=([^&]+)", t_href)
                    if not m_tpl:
                        continue
                    t_id = m_tpl.group(1)
                    full_tpl_url = f"https://swgoh.gg/datacrons/{set_id}/?template_id={t_id}"
                    
                    is_focused = "focused" in t_id or "datacron-icon--focused" in a.get("class", []) or bool(a.find(class_="datacron-icon--focused"))
                    
                    # Image du perso callout
                    callout_img = a.find("img", class_="datacron-icon__callout-affix-img")
                    target_char_icon = callout_img.get("src") if callout_img else None
                    target_char_id = clean_character_id_from_url(target_char_icon) if target_char_icon else None

                    # Max tiers / dots
                    max_tiers = 3
                    primaries = a.find(class_=re.compile(r"datacron-icon__primaries--max-(\d+)"))
                    if primaries:
                        m_max = re.search(r"datacron-icon__primaries--max-(\d+)", str(primaries))
                        if m_max:
                            max_tiers = int(m_max.group(1))

                    template_links.append((t_id, full_tpl_url, is_focused, target_char_id, target_char_icon, max_tiers))

                # Dédupliquer les templates par t_id
                unique_templates = {}
                for t_id, t_url, is_foc, c_id, c_icon, m_tiers in template_links:
                    if t_id not in unique_templates:
                        unique_templates[t_id] = {
                            "template_id": t_id,
                            "url": t_url,
                            "is_focused": is_foc,
                            "target_character_id": c_id,
                            "target_character_icon": c_icon,
                            "max_tiers": m_tiers,
                            "tiers": []
                        }

                # Explorer chaque template pour extraire ses tiers L1-L15
                for t_id, t_data in unique_templates.items():
                    log.info(f"  -> Scraping Template {t_id}...")
                    sb.open(t_data["url"])
                    sb.sleep(1.5)
                    
                    tpl_html = sb.get_page_source()
                    tpl_soup = BeautifulSoup(tpl_html, "html.parser")

                    tier_panels = tpl_soup.find_all("div", class_="datacron-template-tier-collapsable")
                    
                    for tp in tier_panels:
                        # Niveau du tier (ex: Level 3, Level 6, Level 9, Level 15)
                        lvl_elem = tp.find(class_="datacron-template-tier-collapsable__trigger-level")
                        if not lvl_elem:
                            continue
                        lvl_text = lvl_elem.get_text(strip=True)
                        m_lvl = re.search(r"Level\s+(\d+)", lvl_text, re.IGNORECASE)
                        tier_level = int(m_lvl.group(1)) if m_lvl else 1

                        # Prérequis exact de Relique (ex: 6, 3, 1...)
                        relic_elem = tp.find(class_="datacron-template-tier-collapsable__relic")
                        required_relic = int(relic_elem.get_text(strip=True)) if (relic_elem and relic_elem.get_text(strip=True).isdigit()) else None

                        # Scope / Affixes disponibles
                        affix_sets = tp.find_all(class_=re.compile(r"datacron-affix-template-set"))
                        
                        for aff in affix_sets:
                            classes = " ".join(aff.get("class", []))
                            scope = 1
                            if "scope-2" in classes:
                                scope = 2
                            elif "scope-3" in classes:
                                scope = 3
                            elif "scope-4" in classes:
                                scope = 4

                            # Nom du scope (ex: Carson Teva, Colonel Ward, Grogu & Anzellans...)
                            scope_name_elem = aff.find(class_="datacron-affix-template-set__scope-name")
                            scope_name = scope_name_elem.get_text(strip=True) if scope_name_elem else ""

                            # Icône du perso / affix
                            aff_icon_img = aff.find("img", class_="datacron-primary-icon__img")
                            aff_icon_url = aff_icon_img.get("src") if aff_icon_img else ""
                            
                            # Cible unité
                            target_unit_id = clean_character_id_from_url(aff_icon_url) if aff_icon_url else ""
                            unit_link = aff.find("a", href=re.compile(r"/units/"))
                            if unit_link:
                                target_unit_id = clean_character_id_from_url(unit_link.get("href"))

                            # Description / texte de la capacité ou stats
                            desc_elem = aff.find(class_="text-gg-ability-text") or aff.find("ul")
                            desc_text = desc_elem.get_text(" ", strip=True) if desc_elem else ""

                            # Ability ID si présent
                            ab_link = aff.find("a", href=re.compile(r"/ability/"))
                            ability_id = ""
                            if ab_link:
                                m_ab = re.search(r"/ability/([^/]+)/", ab_link.get("href", ""))
                                if m_ab:
                                    ability_id = m_ab.group(1)

                            target_align, target_fac, target_role = parse_target_scopes(desc_text, scope_name, target_unit_id)

                            # Stats numériques éventuelles (Scope 1)
                            stat_type = ""
                            stat_val = 0.0
                            if scope == 1:
                                m_stat = re.search(r"(\d+(?:\.\d+)?%?)\s+(.*)", desc_text)
                                if m_stat:
                                    raw_val, stat_type = m_stat.group(1), m_stat.group(2)
                                    stat_val = float(raw_val.replace("%", ""))

                            # Analyse automatique du périmètre d'impact (Alignement, Faction, Rôle)
                            combined_text = f"{scope_name} {desc_text}".upper()
                            target_alignment = None
                            target_faction = None
                            target_role = None

                            if "LIGHT SIDE" in combined_text or "CÔTÉ LUMINEUX" in combined_text:
                                target_alignment = "LIGHT_SIDE"
                            elif "DARK SIDE" in combined_text or "CÔTÉ OBSCUR" in combined_text:
                                target_alignment = "DARK_SIDE"

                            factions_kw = [
                                ("REBEL", "REBEL"), ("EMPIRE", "EMPIRE"), ("GALACTIC REPUBLIC", "GALACTIC_REPUBLIC"),
                                ("SITH", "SITH"), ("JEDI", "JEDI"), ("FIRST ORDER", "FIRST_ORDER"),
                                ("RESISTANCE", "RESISTANCE"), ("BOUNTY HUNTER", "BOUNTY_HUNTERS"),
                                ("MANDALORIAN", "MANDALORIAN"), ("SEPARATIST", "SEPARATIST"),
                                ("DROID", "DROID"), ("SCOUNDREL", "SCOUNDREL"), ("CLONE TROOPER", "CLONE_TROOPER"),
                                ("EWOK", "EWOK"), ("GEONOSIAN", "GEONOSIAN"), ("HUTT CARTEL", "HUTT_CARTEL"),
                                ("INQUISITORIUS", "INQUISITORIUS"), ("IMPERIAL REMNANT", "IMPERIAL_REMNANT"),
                                ("IMPERIAL TROOPER", "IMPERIAL_TROOPER"), ("NIGHTSISTER", "NIGHTSISTERS"),
                                ("TUSKEN", "TUSKEN"), ("UNALIGNED FORCE USER", "UNALIGNED_FORCE_USER"),
                                ("SMUGGLER", "SMUGGLER"), ("JAWA", "JAWA"), ("BAD BATCH", "BAD_BATCH")
                            ]
                            for kw, fac_val in factions_kw:
                                if re.search(rf"\b{kw}\b", combined_text):
                                    target_faction = fac_val
                                    break

                            roles_kw = [("ATTACKER", "ATTACKER"), ("TANK", "TANK"), ("SUPPORT", "SUPPORT"), ("HEALER", "HEALER"), ("LEADER", "LEADER")]
                            for kw, r_val in roles_kw:
                                if re.search(rf"\b{kw}\b", combined_text):
                                    target_role = r_val
                                    break

                            t_data["tiers"].append({
                                "tier": tier_level,
                                "scope": scope,
                                "scope_name": scope_name,
                                "target_unit_id": target_unit_id,
                                "target_alignment": target_alignment,
                                "target_faction": target_faction,
                                "target_role": target_role,
                                "ability_id": ability_id,
                                "description": desc_text,
                                "icon_url": aff_icon_url,
                                "stat_type": stat_type,
                                "stat_value": stat_val,
                                "required_relic": required_relic
                            })

                    # Mettre à jour le max tiers si on a vu des tiers supérieurs
                    if t_data["tiers"]:
                        max_seen = max(t["tier"] for t in t_data["tiers"])
                        if max_seen > t_data["max_tiers"]:
                            t_data["max_tiers"] = max_seen

                    s_info["templates"].append(t_data)

                all_sets_data.append(s_info)

        # 3. Sauvegarde dans le fichier JSON de sortie
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(all_sets_data, f, ensure_ascii=False, indent=2)

        log.info(f"✅ Scraping terminé avec succès ! Données sauvegardées dans {output_json_path} ({len(all_sets_data)} sets traités).")
        return True

    except Exception as e:
        log.exception(f"❌ Erreur lors du scraping des Datacrons : {e}")
        return False
    finally:
        if display:
            try:
                display.stop()
            except Exception:
                pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python datacrons_sb_worker.py <output_json_path>")
        sys.exit(1)
        
    out_file = sys.argv[1]
    success = scrape_datacrons(out_file)
    sys.exit(0 if success else 1)
