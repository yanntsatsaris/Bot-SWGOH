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
    
    # Trouver le nom du joueur et de l'adversaire
    player_names = soup.find_all(lambda tag: tag.name in ['h1', 'h2', 'h3', 'div'] and tag.get('class') and any('name' in c.lower() for c in tag.get('class')))
    print(f"\n--- Noms trouvés dans les headers ---")
    for p in player_names[:5]:
        print(f"[{p.name}] (Classes: {p.get('class')}): {p.get_text(strip=True)}")
        
    print("\n--- Recherche des onglets Attacks / Defenses ---")
    # Les onglets sont souvent des balises 'a' ou 'button' ou 'li' avec le texte Attacks / Defenses
    tabs = soup.find_all(string=lambda t: t and ('Attacks' in t or 'Defenses' in t))
    for t in tabs:
        parent = t.parent
        print(f"Onglet texte '{t.strip()}' -> tag: {parent.name}, classes: {parent.get('class')}")
        
    print("\n--- Recherche des zones de combat pour séparer les matchs ---")
    # On regarde s'il y a des grands conteneurs pour les deux listes de matchs
    match_lists = soup.find_all('ul', class_=lambda c: c and 'match' in c.lower())
    if not match_lists:
        # Peut-être des divs avec id ?
        for div in soup.find_all('div', id=True):
            if 'attack' in div['id'].lower() or 'defense' in div['id'].lower():
                print(f"Trouvé div avec id='{div['id']}'")
                
    # Pour l'instant, dis-moi juste s'il a trouvé des indices sur le joueur / onglets !

if __name__ == "__main__":
    analyze_gac_html()
