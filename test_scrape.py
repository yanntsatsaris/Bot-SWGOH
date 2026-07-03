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
    
    # Recherche avancée des équipes (qui contiennent des bannières ou des scores)
    print("\n--- Recherche des matchs (Banners / Score) ---")
    
    # On cherche tous les éléments qui contiennent le mot Banners
    elements = soup.find_all(string=lambda text: text and ("Banners" in text or "Score" in text))
    
    if elements:
        for i, el in enumerate(elements[:5]):
            parent = el.parent
            while parent and parent.name != 'div':
                parent = parent.parent
            if parent:
                # On remonte de quelques niveaux pour avoir le bloc entier
                grandparent = parent.parent.parent if parent.parent else parent
                print(f"\n[BLOC {i+1}] (Classes: {grandparent.get('class')})")
                print(grandparent.get_text(separator=' | ', strip=True)[:300])
    else:
        print("Aucun texte contenant 'Banners' ou 'Score' trouvé...")

if __name__ == "__main__":
    analyze_gac_html()
