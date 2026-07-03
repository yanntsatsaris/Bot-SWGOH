import json
from bs4 import BeautifulSoup
import sys

def analyze_gac_html():
    filename = "gac_history_custom_url.html"
    try:
        with open(filename, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        print(f"Impossible de lire le fichier: {e}")
        return

    soup = BeautifulSoup(html, "html.parser")
    print(f"Titre de la page: {soup.title.text if soup.title else 'Aucun'}")
    
    # Stratégie 1: Rechercher un JSON intégré dans la page
    scripts = soup.find_all("script")
    for s in scripts:
        content = s.string
        if content and "match" in content.lower() and "player" in content.lower() and "{" in content:
            if "__NEXT_DATA__" in content or "window.__INITIAL_STATE__" in content:
                print("\n[!] JSON D'ÉTAT INITIAL TROUVÉ DANS UN SCRIPT !")
                print(content[:500] + "...")
                
    # Stratégie 2: Rechercher les divs qui contiennent les données de match
    print("\n--- Analyse des blocs HTML ---")
    rounds = soup.find_all(lambda tag: tag.name == 'div' and tag.get('class') and any('round' in c.lower() or 'match' in c.lower() for c in tag.get('class')))
    
    # On cherche les blocs de statistiques
    stats_blocks = soup.find_all('div', class_=lambda c: c and 'gac-counters-battle-summary__stats' in c)
    
    if stats_blocks:
        print(f"Trouvé {len(stats_blocks)} matchs dans l'historique !")
        
        for i, match_block in enumerate(stats_blocks[:3]):
            parent = match_block.parent
            print(f"\n[MATCH {i+1}]")
            
            # Dans SWGOH.GG, les équipes sont souvent divisées en deux gros blocs (attaquant / défenseur)
            # ou on peut les trouver dans l'ordre. On va extraire tous les tags avec l'attribut magique :
            characters = parent.find_all(lambda tag: tag.has_attr('data-unit-def-tooltip-app'))
            
            # On cherche aussi comment ils sont groupés
            squad_containers = parent.find_all('div', class_=lambda c: c and 'gac-battle-portrait-layout--character' in c)
            
            if squad_containers and len(squad_containers) >= 2:
                for j, squad in enumerate(squad_containers[:2]):
                    side = "Attaquant" if j == 0 else "Défenseur"
                    units = squad.find_all(lambda tag: tag.has_attr('data-unit-def-tooltip-app'))
                    unit_names = [u['data-unit-def-tooltip-app'] for u in units]
                    print(f"- {side} : {', '.join(unit_names)}")
            else:
                # Fallback : on affiche juste tous les personnages trouvés dans le match dans l'ordre
                names = [c['data-unit-def-tooltip-app'] for c in characters]
                print(f"- Tous les personnages dans l'ordre : {names}")
    else:
        print("Impossible de trouver gac-counters-battle-summary__stats")

if __name__ == "__main__":
    analyze_gac_html()
