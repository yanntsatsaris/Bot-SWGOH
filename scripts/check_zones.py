import requests
from bs4 import BeautifulSoup

url = "https://swgoh.gg/p/134145313/gac-history/?gac=121"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}
response = requests.get(url, headers=headers)
soup = BeautifulSoup(response.content, 'html.parser')

stats = soup.find_all('div', class_=lambda c: c and 'gac-counters-battle-summary__stat' in c)
for stat in stats:
    label_el = stat.find('div', class_=lambda c: c and 'stat-label' in c)
    value_el = stat.find('div', class_=lambda c: c and 'stat-value' in c)
    if label_el and value_el:
        label = label_el.get_text(strip=True).lower()
        if label == "zone":
            img = value_el.find('img')
            if img:
                print(f"Found zone image: {img['src']}")
