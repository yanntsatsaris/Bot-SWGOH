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
    
    print("\n--- Analyse détaillée d'un match complet ---")
    
    # On cherche les blocs de statistiques
    stats_blocks = soup.find_all('div', class_=lambda c: c and 'gac-counters-battle-summary__stats' in c)
    
    if stats_blocks:
        print(f"Trouvé {len(stats_blocks)} matchs dans l'historique !")
        
        # On prend le premier match pour l'analyser
        match_block = stats_blocks[0]
        
        # On remonte de 2 ou 3 niveaux pour avoir le conteneur principal du match
        parent = match_block.parent.parent.parent if match_block.parent and match_block.parent.parent else match_block.parent
        
        print("\n[STRUCTURE DU MATCH]")
        print("Classes du conteneur principal :", parent.get('class'))
        
        # On cherche tous les liens ou images pour voir les personnages
        chars = parent.find_all(['img', 'a'])
        print("\nÉléments visuels/liens trouvés dans ce match :")
        for c in chars[:15]:
            if c.name == 'img':
                print(f"- Image: alt='{c.get('alt', '')}', src='{c.get('src', '')}'")
            elif c.name == 'a':
                print(f"- Lien: texte='{c.get_text(strip=True)}', href='{c.get('href', '')}'")
                
        # On cherche les sous-conteneurs (ex: attaquant vs défenseur)
        squads = parent.find_all('div', class_=lambda c: c and 'squad' in c.lower())
        if squads:
            print("\nSous-groupes 'squad' trouvés :", len(squads))
    else:
        print("Impossible de trouver gac-counters-battle-summary__stats")

if __name__ == "__main__":
    analyze_gac_html()
