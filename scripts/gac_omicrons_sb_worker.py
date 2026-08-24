"""
scripts/gac_omicrons_sb_worker.py — Worker SeleniumBase pour scrapper la liste des Omicrons GAC depuis swgoh.gg
"""
import sys
import os
import json
import logging
from bs4 import BeautifulSoup
from seleniumbase import SB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gac_omicrons_worker")

def scrape_gac_omicrons(output_json_path: str) -> bool:
    url = "https://swgoh.gg/stats/ability-report/?fo=grand-arena&ft=all"
    log.info(f"Ouverture de {url} avec SeleniumBase...")
    
    try:
        with SB(uc=True, headless=True) as sb:
            sb.open(url)
            # Attendre que le tableau soit chargé
            sb.wait_for_element_visible("table", timeout=20)
            html = sb.get_page_source()

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        omicrons = []
        
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
                omicrons.append({
                    "base_id": base_id,
                    "ability_name": ability_name,
                    "icon_url": icon_url,
                })

        log.info(f"✅ {len(omicrons)} Omicrons GAC extraits avec succès.")
        
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(omicrons, f, ensure_ascii=False, indent=2)
            
        return True
    except Exception as e:
        log.error(f"❌ Erreur lors du scraping des Omicrons GAC: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python gac_omicrons_sb_worker.py <output_json_path>")
        sys.exit(1)
    
    out_path = sys.argv[1]
    success = scrape_gac_omicrons(out_path)
    sys.exit(0 if success else 1)
