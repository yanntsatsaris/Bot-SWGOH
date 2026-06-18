import json

def print_keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "config": continue # Skip config
            print(f"{prefix}{k} : {type(v).__name__}")
            if isinstance(v, (dict, list)):
                if not (prefix == "" and k == "config"):
                    print_keys(v, prefix + "  ")
    elif isinstance(obj, list) and obj:
        print(f"{prefix}[0] : {type(obj[0]).__name__}")
        if isinstance(obj[0], (dict, list)):
            print_keys(obj[0], prefix + "  ")

try:
    with open("meta_dump.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    print("Structure du metadata :")
    print_keys(meta)
except Exception as e:
    print(f"Erreur: {e}")
