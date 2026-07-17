import asyncio
import json
from pathlib import Path

OUTPUT_FILE = Path("database/all_units.json")


async def sync():
    import aiohttp

    print("🚀 Initialisation du référentiel depuis Comlink...")
    base_url = "http://localhost:3200"

    # Timeout étendu pour éviter le "Server disconnected" sur l'énorme dictionnaire
    timeout = aiohttp.ClientTimeout(total=300)

    try:
        # On désactive la compression (Accept-Encoding: identity) et on force Connection: close
        # C'est LA différence avec curl qui faisait crasher Comlink (Node.js manquait de RAM pour GZIP)
        headers = {
            "Content-Type": "application/json",
            "Accept-Encoding": "identity",
            "Connection": "close",
        }
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            # ÉTAPE 1 : EXTRACTION DES VERSIONS (POST /metadata)
            print("1️⃣ Récupération des versions (metadata)...")
            async with session.post(
                f"{base_url}/metadata", json={"payload": {}}
            ) as resp:
                resp.raise_for_status()
                meta = await resp.json()

            game_version = meta.get("latestGamedataVersion")
            loc_version = meta.get("latestLocalizationBundleVersion")

            if not game_version or not loc_version:
                print("❌ Versions introuvables.")
                return

            print(f" -> Version Jeu : {game_version}")
            print(f" -> Version Loc (ID) : {loc_version}")

            # ÉTAPE 2 : TÉLÉCHARGEMENT DU ROSTER (POST /data)
            print("2️⃣ Téléchargement des données...")
            payload_data = {
                "payload": {
                    "version": game_version,
                    "includePveUnits": True,
                    "requestSegment": 0,
                },
                "enums": False,
            }
            async with session.post(f"{base_url}/data", json=payload_data) as resp:
                resp.raise_for_status()
                data = await resp.json()

            print(
                " -> Sauvegarde temporaire des skills pour analyse (debug_skills.json)..."
            )
            with open("database/debug_skills.json", "w", encoding="utf-8") as f:
                json.dump(data.get("skill", []), f, indent=2)

            # ÉTAPE 3 : TÉLÉCHARGEMENT DES TRADUCTIONS (POST /localization)
            print("3️⃣ Téléchargement et ciblage STRICT de l'Anglais (Loc_ENG_US.txt)...")
            payload_loc = {"payload": {"id": loc_version}, "unzip": True}
            async with session.post(
                f"{base_url}/localization", json=payload_loc
            ) as resp:
                resp.raise_for_status()
                loc_data = await resp.json()

            # Extraction ciblée : on fouille le JSON pour ne prendre QUE le fichier Anglais
            def find_eng(obj):
                if isinstance(obj, dict):
                    if "Loc_ENG_US.txt" in obj and isinstance(
                        obj["Loc_ENG_US.txt"], str
                    ):
                        return obj["Loc_ENG_US.txt"]
                    for v in obj.values():
                        res = find_eng(v)
                        if res:
                            return res
                elif isinstance(obj, list):
                    for v in obj:
                        res = find_eng(v)
                        if res:
                            return res
                return None

            bundle = find_eng(loc_data)

            if not bundle or "UNIT_" not in bundle:
                print("❌ ERREUR : Le dictionnaire ANGLAIS n'a pas pu être extrait.")
                return

            print(" -> Dictionnaire ANGLAIS extrait avec succès !")

            # Étape B : Traduction
            name_map = {}
            for line in bundle.splitlines():
                if "|" in line:
                    k, v = line.split("|", 1)
                    # Nettoyage méticuleux des espaces et retours chariots comme dans AWK
                    name_map[k.strip()] = v.strip()

            # ÉTAPE 4 : CROISEMENT DES DONNÉES
            print(
                "4️⃣ Croisement des données (Filtre: obtainable=true & obtainableTime=0)..."
            )

            raw_units = data.get("units", [])
            playable_units = []
            processed_ids = set()

            for u in raw_units:
                obtainable = u.get("obtainable")
                obtainable_time = u.get("obtainableTime")
                # Condition stricte
                if obtainable is True and str(obtainable_time) == "0":
                    bid = u.get("baseId", "")
                    if bid and bid not in processed_ids:
                        playable_units.append(u)
                        processed_ids.add(bid)

            print(f" -> {len(playable_units)} unités jouables trouvées et filtrées.")
            print("---------------------------------------------------")

            from database.db import init_db, get_db
            from services.portrait_cache import get_portrait_path, build_portrait_cache

            await init_db()
            # On charge les portraits validés pour éviter de les réattribuer !
            await build_portrait_cache()

            async with get_db() as db:
                for unit in playable_units:
                    bid = unit.get("baseId", "")
                    name_key = unit.get("nameKey", "")
                    name_key = name_key.strip()

                    # Logique de Fallback
                    final_name = bid
                    if name_key in name_map and name_map[name_key]:
                        final_name = name_map[name_key]

                    combat_type = unit.get("combatType", 1)
                    unit_type = "character" if combat_type == 1 else "ship"
                    thumb = unit.get("thumbnailName", "").replace("tex.avatars_", "")

                    path_obj = get_portrait_path(bid)
                    image_path = path_obj.as_posix() if path_obj else None

                    await db.execute(
                        """
                        INSERT INTO game_characters (base_id, name, type, thumbnail_name, image_path)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(base_id) DO UPDATE SET
                            name=excluded.name,
                            type=excluded.type,
                            thumbnail_name=excluded.thumbnail_name,
                            image_path=CASE WHEN game_characters.is_image_valid IS NOT 1 THEN excluded.image_path ELSE game_characters.image_path END
                    """,
                        (bid, final_name, unit_type, thumb, image_path),
                    )
                    
                # Sauvegarde des Omicrons et Zetas
                print(" -> Traitement des Omicrons et Zetas...")
                await db.execute("DELETE FROM game_omicrons")
                await db.execute("DELETE FROM game_zetas")
                
                omicrons_found = 0
                zetas_found = 0
                for sk in data.get("skill", []):
                    tiers = sk.get("tier", [])
                    skill_id = sk.get("id")
                    for idx, tier in enumerate(tiers):
                        real_tier = idx + 1
                        if tier.get("isOmicronTier"):
                            await db.execute("INSERT INTO game_omicrons (skill_id, omicron_tier) VALUES (?, ?)", (skill_id, real_tier))
                            omicrons_found += 1
                        if tier.get("isZetaTier"):
                            await db.execute("INSERT INTO game_zetas (skill_id, zeta_tier) VALUES (?, ?)", (skill_id, real_tier))
                            zetas_found += 1
                            
                await db.commit()
            print(f"Terminé ! La base de données SQLite est mise à jour ({omicrons_found} Omicrons, {zetas_found} Zetas trouvés).")

    except Exception as e:
        print(f"❌ Erreur lors de la synchronisation : {e}")


if __name__ == "__main__":
    asyncio.run(sync())
