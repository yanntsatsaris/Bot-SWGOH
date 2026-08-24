"""
scripts/gac_omicrons_sb_worker.py — Worker SeleniumBase pour scrapper la liste des Omicrons GAC depuis swgoh.gg
"""
import sys
import os
import platform
import json
import logging
from bs4 import BeautifulSoup
from seleniumbase import SB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gac_omicrons_worker")

def scrape_gac_omicrons(output_json_path: str) -> bool:
    project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if not os.path.exists(project_dir):
        project_dir = os.getcwd()
        
    is_windows = (platform.system() == "Windows")
    if not is_windows:
        os.environ["HOME"] = project_dir
        os.environ["XDG_CONFIG_HOME"] = os.path.join(project_dir, ".config")
    
    display = None
    url = "https://swgoh.gg/stats/ability-report/?fo=grand-arena&ft=all"
    log.info(f"Ouverture de {url} avec SeleniumBase...")
    
    try:
        if not is_windows:
            try:
                from pyvirtualdisplay import Display
                display = Display(visible=0, size=(1920, 1080))
                display.start()
            except Exception as e:
                log.warning(f"pyvirtualdisplay non démarré: {e}")

        profile_dir = os.path.join(project_dir, "chrome_profile")
        omicrons = []
        page = 1
        seen_keys = set()

        with SB(uc=True, headless=False if not is_windows else True, user_data_dir=profile_dir) as sb:
            while True:
                page_url = f"https://swgoh.gg/stats/ability-report/?fo=grand-arena&ft=all&page={page}"
                log.info(f"Scraping page {page} : {page_url}...")
                
                if page == 1:
                    sb.uc_open_with_reconnect(page_url, reconnect_time=3)
                else:
                    sb.open(page_url)
                
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
                rows = soup.find_all("tr")
                
                page_count = 0
                for r in rows:
                    cols = r.find_all("td")
                    if len(cols) < 2:
                        continue
                        
                    # 1. Base ID / Slug de l'unité
                    portrait_div = cols[0].find(attrs={"data-unit-def-tooltip-app": True})
                    base_id = ""
                    if portrait_div and portrait_div.get("data-unit-def-tooltip-app"):
                        base_id = portrait_div["data-unit-def-tooltip-app"].strip().upper()
                    else:
                        link = cols[0].find("a", href=True)
                        if link and "/units/" in link["href"]:
                            slug = link["href"].split("/units/")[1].split("/")[0]
                            base_id = slug.upper()

                    # 2. Nom de la capacité et icône
                    ability_col = cols[1]
                    icon_img = ability_col.find("img", class_="ability-icon__img")
                    icon_url = icon_img["src"] if icon_img and icon_img.get("src") else ""

                    text_divs = ability_col.find_all("div")
                    ability_name = ""
                    for td in text_divs:
                        t = td.get_text(strip=True)
                        if t and not t.startswith("(") and len(t) > 1 and not td.find("img"):
                            ability_name = t
                            break

                    if base_id and ability_name:
                        key = (base_id, ability_name)
                        if key not in seen_keys:
                            seen_keys.add(key)
                            omicrons.append({
                                "base_id": base_id,
                                "ability_name": ability_name,
                                "icon_url": icon_url,
                            })
                            page_count += 1

                log.info(f"Page {page} : {page_count} nouveaux Omicrons extraits (Total cumulé: {len(omicrons)}).")
                
                # Si aucune nouvelle ligne trouvée sur cette page, on s'arrête
                if page_count == 0:
                    break
                    
                # Vérifier si un lien vers la page suivante existe dans la pagination
                next_page_link = soup.find("a", href=lambda h: h and f"page={page+1}" in h)
                if not next_page_link:
                    log.info(f"Dernière page atteinte (page {page}).")
                    break
                    
                page += 1

        log.info(f"✅ Scraping terminé : {len(omicrons)} Omicrons GAC extraits au total sur {page} page(s).")
        
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(omicrons, f, ensure_ascii=False, indent=2)
            
        return True
    except Exception as e:
        log.error(f"❌ Erreur lors du scraping des Omicrons GAC: {e}", exc_info=True)
        return False
    finally:
        if display:
            try:
                display.stop()
            except Exception:
                pass

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python gac_omicrons_sb_worker.py <output_json_path>")
        sys.exit(1)
    
    out_path = sys.argv[1]
    success = scrape_gac_omicrons(out_path)
    sys.exit(0 if success else 1)
