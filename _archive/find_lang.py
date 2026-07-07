import json

def find_locales(obj, path=""):
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if "FRE_FR" in str(v) or "ENG_US" in str(v) or "Loc_" in str(v) or "localizationBundleVersion" in k:
                if isinstance(v, str):
                    results.append(f"{path}.{k} = {v}")
            results.extend(find_locales(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if "FRE_FR" in str(v) or "ENG_US" in str(v) or "Loc_" in str(v):
                if isinstance(v, str):
                    results.append(f"{path}[{i}] = {v}")
            results.extend(find_locales(v, f"{path}[{i}]"))
    return results

try:
    with open("meta_dump.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
        
    print("Recherche des identifiants de langue...")
    matches = find_locales(meta, "meta")
    if matches:
        print("\n".join(matches))
    else:
        print("Aucune clé FRE_FR ou ENG_US trouvée dans le JSON.")
except Exception as e:
    print(f"Erreur: {e}")
