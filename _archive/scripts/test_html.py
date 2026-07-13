import requests
from bs4 import BeautifulSoup

def check():
    url = 'https://swgoh.gg/p/134145313/gac-history/?gac=173'
    r = requests.get(url)
    soup = BeautifulSoup(r.text, 'html.parser')
    blocks = soup.find_all('div', class_=lambda c: c and 'gac-counters-battle-summary__stats' in c)
    if not blocks:
        print("No blocks found.")
        return
        
    for i, block in enumerate(blocks[:3]):
        parent = block.parent
        print(f"\n--- Block {i} ---")
        squads = parent.find_all('div', class_=lambda c: c and 'gac-battle-portrait-layout' in c)
        print(f"Number of squad containers: {len(squads)}")
        for j, squad in enumerate(squads):
            units = squad.find_all(lambda tag: tag.has_attr('data-unit-def-tooltip-app'))
            names = [u['data-unit-def-tooltip-app'] for u in units]
            print(f"  Container {j}: {names}")

check()
