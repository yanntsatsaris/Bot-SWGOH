"""
scripts/inspect_player_datacrons.py — Inspecte les Datacrons d'un joueur via Comlink
Usage : python scripts/inspect_player_datacrons.py <ally_code>
"""
import sys
import os
import json
import asyncio

# Ajout du chemin racine du projet
project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_dir)

from services.comlink import get_player

async def inspect(ally_code: str):
    clean_code = str(ally_code).replace("-", "").strip()
    print(f"🔍 Interrogation de Comlink pour le code allié : {clean_code}...")

    try:
        player_data = await get_player(ally_code=clean_code)
    except Exception as e:
        print(f"❌ Erreur lors de la récupération du joueur : {e}")
        return

    player_name = player_data.get("name", "Inconnu")
    guild_name = player_data.get("guildName", "Sans Guilde")
    print(f"\n👤 Joueur : {player_name} ({clean_code}) | Guilde : {guild_name}")

    # Recherche des champs liés aux Datacrons
    datacrons = player_data.get("datacron", [])
    print(f"🎲 Total Datacrons trouvés : {len(datacrons)}")

    if not datacrons:
        print("⚠️ Aucun Datacron trouvé dans le payload du joueur (ou champ vide).")
        # Affichage des clés de premier niveau disponibles pour vérification
        print("Clés disponibles dans player_data :", list(player_data.keys()))
        return

    # Sauvegarde d'un échantillon brut
    temp_dir = os.path.join(project_dir, "temp_data")
    os.makedirs(temp_dir, exist_ok=True)
    sample_file = os.path.join(temp_dir, "my_datacrons_sample.json")
    with open(sample_file, "w", encoding="utf-8") as f:
        json.dump(datacrons, f, indent=2, ensure_ascii=False)
    print(f"💾 Données brutes des Datacrons sauvegardées dans : {sample_file}\n")

    print("=" * 60)
    for idx, dtc in enumerate(datacrons, 1):
        dtc_id = dtc.get("id")
        set_id = dtc.get("setId")
        template_id = dtc.get("templateId")
        affixes = dtc.get("affix", [])
        reroll_count = dtc.get("rerollCount", 0)

        print(f"\n[{idx}/{len(datacrons)}] Datacron ID: {dtc_id}")
        print(f"  • Set ID : {set_id} | Template : {template_id} | Rerolls : {reroll_count}")
        print(f"  • Paliers débloqués ({len(affixes)}) :")
        
        for aff_idx, aff in enumerate(affixes, 1):
            stat_type = aff.get("statType")
            stat_val = aff.get("statValue")
            ability_id = aff.get("abilityId")
            target_rule = aff.get("targetRule")
            scope = aff.get("scope")
            
            # Affichage clair
            if ability_id:
                print(f"    - Palier {aff_idx} (Capacité/Scope {scope}) : Ability ID = {ability_id} (Target: {target_rule})")
            elif stat_type:
                val_display = f"{stat_val / 10000:.2f}%" if isinstance(stat_val, int) and stat_val > 100 else f"{stat_val}"
                print(f"    - Palier {aff_idx} (Stat/Scope {scope}) : StatType {stat_type} = {val_display} (Target: {target_rule})")
            else:
                print(f"    - Palier {aff_idx} : {aff}")
    print("=" * 60)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/inspect_player_datacrons.py <ally_code>")
        sys.exit(1)

    code = sys.argv[1]
    asyncio.run(inspect(code))
