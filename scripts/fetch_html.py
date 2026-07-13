import urllib.request

url = "https://swgoh.gg/p/134145313/gac-history/O1780434000000/2/"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})

print(f"Downloading {url}...")
try:
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        
    out_path = "C:/Users/yann/.gemini/antigravity-ide/brain/c65bb192-f4b3-407a-976f-52dea50b0051/scratch/round_html.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Successfully saved to {out_path}")
except Exception as e:
    print(f"Error: {e}")
