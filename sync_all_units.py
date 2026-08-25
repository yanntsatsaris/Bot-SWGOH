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

            new_portraits_count = 0
            downloaded_names = []

            # Construction de la table de correspondance des catégories/factions
            category_map = {}
            for cat in data.get("category", []):
                cat_id = cat.get("id")
                desc_key = cat.get("descKey")
                if cat_id:
                    translated = name_map.get(desc_key) if desc_key else None
                    category_map[cat_id] = translated or cat_id

            async with get_db() as db:
                for unit in playable_units:
                    bid = unit.get("baseId", "")
                    name_key = unit.get("nameKey", "")
                    name_key = name_key.strip()

                    final_name = bid
                    if name_key in name_map and name_map[name_key]:
                        final_name = name_map[name_key]

                    combat_type = unit.get("combatType", 1)
                    unit_type = "character" if combat_type == 1 else "ship"
                    thumb = unit.get("thumbnailName", "")

                    # Extraction de l'alignement, du rôle, du statut GL / Leader et des factions
                    cat_ids = unit.get("categoryId", unit.get("categoryIdList", []))
                    
                    alignment = None
                    if "alignment_light" in cat_ids:
                        alignment = "Light Side"
                    elif "alignment_dark" in cat_ids:
                        alignment = "Dark Side"
                    elif "alignment_neutral" in cat_ids:
                        alignment = "Neutral"

                    role = None
                    if "role_attacker" in cat_ids:
                        role = "Attacker"
                    elif "role_support" in cat_ids:
                        role = "Support"
                    elif "role_tank" in cat_ids:
                        role = "Tank"
                    elif "role_healer" in cat_ids:
                        role = "Healer"

                    is_gl = "galactic_legend" in cat_ids
                    skills_list = unit.get("skillReference", unit.get("skillReferenceList", []))
                    is_leader = "role_leader" in cat_ids or any("leader" in str(s).lower() for s in skills_list)

                    excluded_cat_prefixes = ("alignment_", "role_", "type_")
                    excluded_cats = {"galactic_legend", "obtainable", "character", "ship", "crew", "preview", "capital"}
                    
                    unit_factions = []
                    for cid in cat_ids:
                        if cid in excluded_cats or any(cid.startswith(p) for p in excluded_cat_prefixes):
                            continue
                        f_name = category_map.get(cid, name_map.get(cid, cid))
                        # Nettoyer d'éventuels préfixes bruts si non traduit
                        if f_name.startswith("faction_") or f_name.startswith("species_") or f_name.startswith("profession_"):
                            f_name = f_name.split("_", 1)[-1].capitalize()
                        if f_name and f_name not in unit_factions:
                            unit_factions.append(f_name)

                    factions_json = json.dumps(unit_factions, ensure_ascii=False)

                    dest_dir = Path("assets/vaisseaux") if combat_type == 2 else Path("assets/portraits")
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    
                    image_path = None
                    # 1. Vérification par get_portrait_path (doit faire > 3 Ko pour être valide et éviter les vieilles vignettes corrompues)
                    existing_path = get_portrait_path(bid)
                    if existing_path and existing_path.exists() and existing_path.stat().st_size > 3000:
                        image_path = existing_path.as_posix()
                    else:
                        # 2. Vérification si un fichier HD existe déjà sous un nom nettoyé
                        clean_thumb = thumb.replace("tex.avatars_", "").replace("tex.", "") if thumb else ""
                        possible_files = []
                        if thumb:
                            possible_files.append(dest_dir / f"{thumb}.png")
                        if clean_thumb:
                            if not clean_thumb.startswith("charui_"):
                                possible_files.append(dest_dir / f"charui_{clean_thumb}.png")
                            possible_files.append(dest_dir / f"{clean_thumb}.png")

                        for p in possible_files:
                            if p.exists() and p.stat().st_size > 3000:
                                image_path = p.as_posix()
                                break


                        # 3. Téléchargement de la version Ultra HD (18-24 KB) depuis le CDN EA
                        if not image_path and thumb:
                            target_filename = f"{thumb}.png" if thumb.startswith("tex.") else f"tex.{thumb}.png"
                            local_file = dest_dir / target_filename
                            
                            urls_to_try = [
                                f"https://game-assets.swgoh.gg/textures/{thumb}.png",
                                f"https://game-assets.swgoh.gg/{thumb}.png",
                                f"https://swgoh.gg/static/img/assets/{thumb}.png",
                            ]
                            for u in urls_to_try:
                                try:
                                    async with session.get(u) as r:
                                        if r.status == 200:
                                            local_file.write_bytes(await r.read())
                                            new_portraits_count += 1
                                            downloaded_names.append(final_name)
                                            print(f"  ✨ Portrait HD (18-24 KB) téléchargé : {final_name} ({bid}) -> {local_file.name}")
                                            image_path = local_file.as_posix()
                                            break
                                except Exception:
                                    pass

                    await db.execute(
                        """
                        INSERT INTO game_characters (
                            base_id, name, type, thumbnail_name, image_path, is_image_valid,
                            alignment, role, factions, is_galactic_legend, is_leader
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(base_id) DO UPDATE SET
                            name=excluded.name,
                            type=excluded.type,
                            thumbnail_name=excluded.thumbnail_name,
                            image_path=COALESCE(excluded.image_path, game_characters.image_path),
                            is_image_valid=CASE WHEN excluded.image_path IS NOT NULL THEN 1 ELSE game_characters.is_image_valid END,
                            alignment=excluded.alignment,
                            role=excluded.role,
                            factions=excluded.factions,
                            is_galactic_legend=excluded.is_galactic_legend,
                            is_leader=excluded.is_leader
                    """,
                        (
                            bid, final_name, unit_type, thumb, image_path, 1 if image_path else 0,
                            alignment, role, factions_json,
                            1 if is_gl else 0, 1 if is_leader else 0
                        ),
                    )
                    
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
            
            summary = {
                "total_comlink": len(playable_units),
                "new_portraits_count": new_portraits_count,
                "downloaded_names": downloaded_names
            }
            print(f"✅ Terminé ! {len(playable_units)} unités Comlink synchronisées en BDD ({new_portraits_count} nouveaux portraits téléchargés, {omicrons_found} Omicrons, {zetas_found} Zetas).")
            return summary


    except Exception as e:
        print(f"❌ Erreur lors de la synchronisation : {e}")


if __name__ == "__main__":
    asyncio.run(sync())
