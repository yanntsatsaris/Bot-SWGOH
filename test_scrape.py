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
    
    if not rounds:
        # On essaie de trouver les mots clés GAC
        print("Recherche de 'GAC' ou 'Round' dans les divs...")
        for div in soup.find_all("div"):
            text = div.get_text(separator=' ', strip=True)
            if "Round" in text and "Banners" in text:
                print(f"Div suspect trouvé (classes: {div.get('class')}): {text[:100]}...")
                break
    else:
        print(f"Nombre de divs 'round/match' trouvés : {len(rounds)}")
        if rounds:
            print(f"Exemple du premier bloc : classes={rounds[0].get('class')}")

if __name__ == "__main__":
    analyze_gac_html()
