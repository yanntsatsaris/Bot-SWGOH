import json

try:
    with open("meta_dump.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    print("latestLocalizationBundleVersion:", meta.get("latestLocalizationBundleVersion"))
    print("latestLocalizationRevision:", meta.get("latestLocalizationRevision"))
except Exception as e:
    print(f"Erreur: {e}")
