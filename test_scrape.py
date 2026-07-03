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
    
    print("\n--- Extraction de la structure exacte d'un match ---")
    
    # On cherche les blocs de statistiques
    stats_blocks = soup.find_all('div', class_=lambda c: c and 'gac-counters-battle-summary__stats' in c)
    
    if stats_blocks:
        print(f"Trouvé {len(stats_blocks)} matchs dans l'historique !")
        
        # On prend le premier match pour l'analyser
        match_block = stats_blocks[0]
        
        # On remonte juste au parent direct qui englobe la ligne de match
        parent = match_block.parent
        
        # On affiche le HTML formaté de ce seul match
        print("\n[CODE HTML DU PREMIER MATCH]")
        print(parent.prettify()[:1500]) # On coupe à 1500 caractères pour ne pas inonder le terminal
        
        # On extrait les liens pour voir s'ils contiennent les noms des personnages (href)
        print("\n[LIENS DANS CE MATCH]")
        for a in parent.find_all('a', href=True):
            if '/characters/' in a['href'] or '/ships/' in a['href']:
                print(f"- Personnage détecté : {a['href']}")
            elif 'insight' in a['href']:
                print(f"- Lien Insight : {a['href']}")
    else:
        print("Impossible de trouver gac-counters-battle-summary__stats")

if __name__ == "__main__":
    analyze_gac_html()
