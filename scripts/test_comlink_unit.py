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
            print("=" * 60)
            print(f"📊 RÉSULTAT COMLINK POUR : {target_base_id}")
            print("=" * 60)
            print(f"• Clés disponibles dans l'unité : {list(target_unit.keys())}")
            
            # Afficher les champs potentiels de catégories / factions
            for k in ["categoryIdList", "categoryList", "categories", "factions", "tags", "alignment", "forceAlignment", "combatType"]:
                if k in target_unit:
                    print(f"• {k} : {target_unit[k]}")

            # Vérifier si Comlink a d'autres collections comme categoryList
            print("\n• Autres collections présentes dans data :", list(data.keys()))
            
            # Afficher le JSON complet de l'unité (tronqué si trop long)
            print("\n📋 Extrait JSON complet de l'unité :")
            unit_dump = json.dumps(target_unit, indent=2)
            print(unit_dump[:2000] + ("\n... [suite tronquée]" if len(unit_dump) > 2000 else ""))
            print("=" * 60)

if __name__ == "__main__":
    unit_arg = sys.argv[1] if len(sys.argv) > 1 else "GLREY"
    asyncio.run(fetch_unit_from_comlink(unit_arg))
