import asyncio
import logging
from database.db import get_db

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("FixPortraits")

# Dictionnaire de correction des personnages (Base ID -> Chemin d'image supposé correct)
# Si tu vois une erreur de nom de fichier ici, tu pourras la modifier plus tard ou utiliser /fix-portrait
CORRECTIONS = {
    "BISHOP": "assets/portraits/charui_colonelward.png", # Pas de Crosshair dispo, Colonel Ward en substitution ?
    "BOBAFETTSCION": "assets/portraits/charui_bobafettold.png", # Boba Fett Old = Scion
    "CAPITALJEDICRUISER": "assets/vaisseaux/venator.png", # Endurance = Venator
    "DEATHTROOPER": "assets/portraits/charui_trooperdeath.png",
    "FINN": "assets/portraits/charui_finnjakku.png", # Finn classique = Jakku (EPIXFINN utilise l'autre)
    "GLAHSOKATANO": "assets/portraits/charui_ahsokatanogray.png",
    "HONDO": "assets/portraits/charui_hondoohnaka.png",
    "JEDIKNIGHTCONSULAR": "assets/portraits/charui_jedi_consular_03.png",
    "JEDIKNIGHTREVAN": "assets/portraits/charui_jedirevan.png",
    "LUKESKYWALKER": "assets/portraits/charui_luke_ep4.png", # Farmboy = ep4
    "MAULS7": "assets/portraits/charui_maul_cyborg.png",
    "MILLENNIUMFALCONPRISTINE": "assets/vaisseaux/mil_fal_pristine.png",
    "RACCOON": "assets/portraits/charui_rotta.png", # Raccoon est le nom de code de Rotta le Hutt !
    "REY": "assets/portraits/charui_reyjakku.png", # Rey pillard = Jakku
    "SCOUTTROOPER_V3": "assets/portraits/charui_trooperscout.png",
    "SMUGGLERCHEWBACCA": "assets/portraits/charui_tfa_chewbacca.png", # Veteran = TFA
    "SMUGGLERHAN": "assets/portraits/charui_tfa_han.png", # Veteran = TFA
    "STORMTROOPER": "assets/portraits/charui_trooperstorm.png",
    "STORMTROOPERHAN": "assets/portraits/charui_trooperstorm_han.png",
    "THEMANDALORIANBESKARARMOR": "assets/portraits/charui_mandobeskar.png",
    "TIEFIGHTERFIRSTORDER": "assets/vaisseaux/firstorder_tiefighter.png",
    "TIEFIGHTERFOSF": "assets/vaisseaux/fosf_tie_fighter.png",
    "UWINGROGUEONE": "assets/vaisseaux/uwing_hero.png", # Uwing de Cassian
    "YOUNGCHEWBACCA": "assets/portraits/charui_chewbacca_vandor.png", # Vandor = Young
    "YWINGCLONEWARS": "assets/vaisseaux/ywing_btlb.png",
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
