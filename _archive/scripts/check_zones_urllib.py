import urllib.request
import re

url = "https://swgoh.gg/p/134145313/gac-history/?gac=121"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        
        # Trouver toutes les occurences de "Zone" et regarder ce qu'il y a après
        matches = re.finditer(r'>Zone<.*?(<img[^>]+>)', html, re.IGNORECASE | re.DOTALL)
        for i, match in enumerate(matches):
            if i > 5: break
            print(f"Match {i}: {match.group(1)}")
except Exception as e:
    print(e)
