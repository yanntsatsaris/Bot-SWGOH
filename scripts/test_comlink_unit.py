"""
scripts/test_comlink_unit.py — Script de test Comlink pour inspecter les données d'une unité (ex: GLREY)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Usage :
  python scripts/test_comlink_unit.py [BASE_ID]
  Exemple : python scripts/test_comlink_unit.py GLREY
            python scripts/test_comlink_unit.py GRIEVOUS
            python scripts/test_comlink_unit.py QUEENAMIDALA
"""
import sys
import os
import json
import asyncio
import aiohttp
from dotenv import load_dotenv

load_dotenv()

COMLINK_URL = os.getenv("COMLINK_URL", "http://localhost:3200").rstrip("/")

ALIGNMENT_MAP = {
    1: "Neutral",
    2: "Light Side (Côté Lumineux)",
    3: "Dark Side (Côté Obscur)"
}

async def fetch_unit_from_comlink(target_base_id: str = "GLREY"):
    target_base_id = target_base_id.upper().strip()
    print(f"📡 Connexion à Comlink : {COMLINK_URL}")
    print(f"🔍 Recherche de l'unité : {target_base_id}...\n")

    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # 1. Récupérer la version des données du jeu
        try:
            async with session.post(f"{COMLINK_URL}/metadata", json={"payload": {}}) as resp:
                if resp.status != 200:
                    print(f"❌ Erreur HTTP {resp.status} sur /metadata : {await resp.text()}")
                    return
                meta = await resp.json()
                version = meta.get("latestGamedataVersion")
                print(f"✓ Version du jeu active : {version}")
        except Exception as e:
            print(f"❌ Impossible de joindre Comlink sur {COMLINK_URL} : {e}")
            return

        # 2. Récupérer les données de l'unité
        payload = {
            "version": version,
            "includePveUnits": False,
            "requestSegment": 0
        }
        
        print("⏳ Téléchargement des définitions d'unités...")
        async with session.post(
            f"{COMLINK_URL}/data", 
            json={"payload": payload}, 
            headers={"Content-Type": "application/json"}
        ) as resp:
            if resp.status != 200:
                print(f"❌ Erreur HTTP {resp.status} sur /data : {await resp.text()}")
                return
            
            data = await resp.json()
            units = data.get("units", [])
            print(f"✓ {len(units)} unités reçues.")

            target_unit = None
            for u in units:
                bid = u.get("baseId", "")
                if bid.upper() == target_base_id:
                    target_unit = u
                    break

            if not target_unit:
                print(f"\n❌ Unité '{target_base_id}' introuvable dans les données Comlink.")
                print("Exemples d'unités valides : GLREY, GRIEVOUS, QUEENAMIDALA, JEDIMASTERKENOBI, THIRDSISTER, GLHONDO")
                return

            # 3. Analyser et afficher les informations
            cat_list = target_unit.get("categoryId", target_unit.get("categoryIdList", []))
            force_align = target_unit.get("forceAlignment", 0)
            align_str = ALIGNMENT_MAP.get(force_align, f"Inconnu ({force_align})")

            factions = [c.replace("affiliation_", "").replace("profession_", "") for c in cat_list if "affiliation_" in c or "profession_" in c or "unaligned" in c]
            roles = [c.replace("role_", "") for c in cat_list if "role_" in c]
            special = [c for c in cat_list if c in ["galactic_legend", "leader", "crewmember", "capital", "role_leader"]]

            print("=" * 60)
            print(f"📊 RÉSULTAT COMLINK POUR : {target_base_id}")
            print("=" * 60)
            print(f"• Nom clé (nameKey) : {target_unit.get('nameKey')}")
            print(f"• Type de combat   : {'Personnage' if target_unit.get('combatType') == 1 else 'Vaisseau'}")
            print(f"• Alignement brut  : forceAlignment={force_align} -> {align_str}")
            print(f"• Rôles détectés   : {roles}")
            print(f"• Factions         : {factions}")
            print(f"• Statuts spéciaux : {special}")
            print("\n📋 Liste brute des catégories (categoryId) :")
            print(json.dumps(cat_list, indent=2))
            print("=" * 60)

if __name__ == "__main__":
    unit_arg = sys.argv[1] if len(sys.argv) > 1 else "GLREY"
    asyncio.run(fetch_unit_from_comlink(unit_arg))
