import urllib.request
import json

try:
    req = urllib.request.Request(
        "https://swgoh.gg/api/characters/",
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    with urllib.request.urlopen(req) as response:
        chars = json.loads(response.read().decode())
        print(f"✅ Fetched {len(chars)} characters")
        with open("name_map.json", "w", encoding="utf-8") as f:
            json.dump({c["base_id"]: c["name"] for c in chars}, f)
except Exception as e:
    print(f"Error: {e}")
