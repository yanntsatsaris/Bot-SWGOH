import asyncio
import logging
from database.db import get_db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("FixPortraits")

# Dictionnaire de correction des personnages (Base ID -> Chemin d'image supposé correct)
# Si tu vois une erreur de nom de fichier ici, tu pourras la modifier plus tard ou utiliser /fix-portrait
CORRECTIONS = {
    "AHSOKATANO": "assets/portraits/charui_ahsoka.png",
    "ARC170REX": "assets/vaisseaux/arc170_02.png",
    "BISHOP": "assets/portraits/charui_crosshair.png",  # Hunter, Tech, etc. ont leurs noms, Crosshair est souvent décalé
    "BOBAFETTSCION": "assets/portraits/charui_bobafett_scion.png",
    "C3POCHEWBACCA": "assets/portraits/charui_chewbacca_c3po.png",
    "CHEWBACCALEGENDARY": "assets/portraits/charui_chewbacca_ot.png",
    "DEATHTROOPER": "assets/portraits/charui_deathtrooper.png",
    "EPIXPOE": "assets/portraits/charui_poe_tros.png",
    "FINN": "assets/portraits/charui_finn.png", # Probablement une erreur de clic lors de la revue
    "FOSITHTROOPER": "assets/portraits/charui_firstorder_sithtrooper.png",
    "FULCRUMAHSOKA": "assets/portraits/charui_ahsokaadult.png",
    "GLAHSOKATANO": "assets/portraits/charui_glahsoka.png", 
    "HONDO": "assets/portraits/charui_hondo.png",
    "JEDIKNIGHTCONSULAR": "assets/portraits/charui_jedi_consular.png",
    "JEDIKNIGHTREVAN": "assets/portraits/charui_revan_jedi.png",
    "LUKESKYWALKER": "assets/portraits/charui_luke_farmboy.png",
    "MAULS7": "assets/portraits/charui_maul_s7.png",
    "MILLENNIUMFALCONEP7": "assets/vaisseaux/mfalcon_ep7.png",
    "MILLENNIUMFALCONPRISTINE": "assets/vaisseaux/mfalcon_pristine.png",
    "MISSIONVAO": "assets/portraits/charui_mission.png",
    "RACCOON": "assets/portraits/charui_krrsantan.png", # Souvent un nom de code pour Krrsantan ou similaire
    "REY": "assets/portraits/charui_rey.png", # Rey Pillard
    "REYJEDITRAINING": "assets/portraits/charui_rey_tlj.png",
    "SCOUTTROOPER_V3": "assets/portraits/charui_scouttrooper.png",
    "SMUGGLERCHEWBACCA": "assets/portraits/charui_chewbacca_vandor.png",
    "SMUGGLERHAN": "assets/portraits/charui_han_young.png",
    "STORMTROOPER": "assets/portraits/charui_stormtrooper.png",
    "STORMTROOPERHAN": "assets/portraits/charui_han_stormtrooper.png",
    "THEMANDALORIANBESKARARMOR": "assets/portraits/charui_mandalorian_beskar.png",
    "TIEFIGHTERFIRSTORDER": "assets/vaisseaux/tiefighter_firstorder.png",
    "TIEFIGHTERFOSF": "assets/vaisseaux/tiefighter_fosf.png",
    "TIEFIGHTERPILOT": "assets/portraits/charui_tiepilot.png",
    "UWINGROGUEONE": "assets/vaisseaux/uwing_cassian.png",
    "YOUNGCHEWBACCA": "assets/portraits/charui_chewbacca_young.png",
    "YOUNGHAN": "assets/portraits/charui_han_young.png",
}

async def fix_portraits():
    print("🚀 Remise en file d'attente pour vérification manuelle...")
    updated = 0
    
    async with get_db() as db:
        for base_id, image_path in CORRECTIONS.items():
            # Met à jour le chemin d'image mais remet is_image_valid à NULL pour forcer la vérification
            cursor = await db.execute(
                "UPDATE units_directory SET image_path = ?, is_image_valid = NULL WHERE base_id = ?",
                (image_path, base_id)
            )
            if cursor.rowcount > 0:
                print(f"🔄 À vérifier : {base_id} -> {image_path}")
                updated += 1
            else:
                print(f"⚠️ Non trouvé dans la base : {base_id}")
                
        await db.commit()
        
    print(f"\n✨ Terminé ! {updated} portraits ont été mis à jour et replacés dans la file de vérification (/review-portraits).")

if __name__ == "__main__":
    asyncio.run(fix_portraits())
