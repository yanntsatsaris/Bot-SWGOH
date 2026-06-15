"""
services/unit_names.py — Cache de traduction base_id → nom affiché
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tente de récupérer les noms depuis Comlink /localization,
replie sur un dictionnaire statique des unités GAC les plus courantes.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dictionnaire statique — unités GAC les plus fréquentes
# Clé : base_id Comlink (MAJUSCULES)  |  Valeur : nom affiché
# ---------------------------------------------------------------------------
_STATIC_NAMES: dict[str, str] = {
    # --- Sith / Empire ---
    "SITHPALPATINE":                "Sith Eternal Emperor",
    "DARTHVADER":                   "Darth Vader",
    "LORDVADER":                    "Lord Vader",
    "MARAJADE":                     "Mara Jade",
    "DARTHNIHILUS":                 "Darth Nihilus",
    "ROYALGUARD":                   "Royal Guard",
    "PALPATINE":                    "Emperor Palpatine",
    "THRAWN":                       "Grand Admiral Thrawn",
    "DEATHTROOPER":                 "Death Trooper",
    "RANGETROOPER":                 "Range Trooper",
    "KRENNIC":                      "Director Krennic",
    "STARKILLERBASE":               "Starkiller",
    "GENERALVEERS":                 "General Veers",
    "MAGMATROOPER":                 "Magma Trooper",
    # --- Jabba ---
    "JABBATHEHUTT":                 "Jabba the Hutt",
    "BOBAFETTSCION":                "Boba Fett (Scion)",
    "KRRSANTAN":                    "Black Krrsantan",
    "GAMORREANGUARD":               "Gamorrean Guard",
    "SKIFFGUARD":                   "Skiff Guard",
    "BIBFORTUNA":                   "Bib Fortuna",
    # --- Jedi / République ---
    "JEDIMASTERKENOBI":             "Jedi Master Kenobi",
    "PADMEAMIDALA":                 "Padmé Amidala",
    "GENERALSKYWALKER":             "General Skywalker",
    "JEDIMASTERLUKE":               "Jedi Master Luke Skywalker",
    "JEDIKNIGHTLUKE":               "Jedi Knight Luke Skywalker",
    "COMMANDERLUKESKYWALKER":       "Commander Luke Skywalker",
    "AHSOKATANO":                   "Ahsoka Tano",
    "SHAAKTI":                      "Shaak Ti",
    "GRANDMASTERYODA":              "Grand Master Yoda",
    "HERMITYODA":                   "Hermit Yoda",
    "KITFISTO":                     "Kit Fisto",
    "MACEWINDU":                    "Mace Windu",
    "DARTHREVAN":                   "Darth Revan",
    "JEDIKNIGHTREVAN":              "Jedi Knight Revan",
    # --- First Order ---
    "SUPREMELEADERKYLOREN":         "Supreme Leader Kylo Ren",
    "KYLORENUNMASKED":              "Kylo Ren (Unmasked)",
    "KYLOREN":                      "Kylo Ren",
    "GENERALHUX":                   "General Hux",
    "FIRSTORDERSFTFIGHTER":         "FO SF TIE Pilot",
    "FIRSTORDERTIEPILOT":           "First Order TIE Pilot",
    "CAPTAINPHASMA":                "Captain Phasma",
    # --- Rebels ---
    "HANSOLO":                      "Han Solo",
    "CHEWBACCA":                    "Chewbacca",
    "PRINCESSLEIA":                 "Princess Leia",
    "CHIRRUT":                      "Chirrut Îmwe",
    "BAZE":                         "Baze Malbus",
    "CASSIANANDOR":                 "Cassian Andor",
    "K2SO":                         "K-2SO",
    # --- Nightsisters ---
    "MOTHERTALZIN":                 "Mother Talzin",
    "ASAJVENTRESS":                 "Asajj Ventress",
    "ZOMBIESISTER":                 "Zombie Sister",
    "NIGHTSISTERINIT":              "Nightsister Initiate",
    "TALIA":                        "Talia",
    # --- Mandalorians ---
    "THEMANDALORIAN":               "The Mandalorian",
    "THEMANDALORIANBESKARARMOR":    "The Mandalorian (Beskar)",
    "MOFFGIDEON":                   "Moff Gideon",
    "BOSAKATAN":                    "Bo-Katan Kryze",
    "GROGU":                        "Grogu",
    # --- Resistance ---
    "REYJAKKU":                     "Rey (Jakku)",
    "REYJEDITRAINING":              "Rey (Jedi Training)",
    "FINN":                         "Finn",
    "POE":                          "Poe Dameron",
    "BB8":                          "BB-8",
    "R2D2_LEGENDARY":               "R2-D2",
    "C3POLEGENDARY":                "C-3PO",
    # --- Bounty Hunters ---
    "BOBAFETT":                     "Boba Fett",
    "JANGOFETT":                    "Jango Fett",
    "DENGAR":                       "Dengar",
    "CADSANE":                      "Cad Bane",
    "EMBO":                         "Embo",
    "GREEF":                        "Greef Karga",
    "GREEFKARGA":                   "Greef Karga",
    # --- Galactic Republic ---
    "QUIGONJINN":                   "Qui-Gon Jinn",
    "OBIWAN":                       "Obi-Wan Kenobi",
    "BASTILLASHAN":                 "Bastila Shan",
    "BASTILLASHANDARK":             "Bastila Shan (Fallen)",
    "OLDREPUBLICGUARD":             "Old Republic Guard",
    # --- Separatistes ---
    "GENERALGRIEVOUS":              "General Grievous",
    "DROIDEKA":                     "Droideka",
    "B1BATTLEDROIDV2":              "B1 Battle Droid",
    "MAGNAGUARD":                   "MagnaGuard",
    "NUTE":                         "Nute Gunray",
    # --- Autres ---
    "SITHMARAUDER":                 "Sith Marauder",
    "SITHASSASSIN":                 "Sith Assassin",
    "SITHTROOPER":                  "Sith Trooper",
    "IMPERIALSUPERCOMMANDO":        "Imperial Super Commando",
    "WAMPA":                        "Wampa",
    "ACOLYTE":                      "Sith Eternal Acolyte",
}


# ---------------------------------------------------------------------------
# Interface publique
# ---------------------------------------------------------------------------
_cache: dict[str, str] = {}


async def build_name_cache() -> None:
    """
    Tente de remplir le cache depuis Comlink /localization.
    Replie silencieusement sur le dictionnaire statique en cas d'échec.
    """
    global _cache
    try:
        from services.comlink import _post
        data = await _post("localization", {"id": "Loc_ENG_TXT"})
        bundle = data.get("localizationBundle", "")
        # Le bundle est un texte clé=valeur, une par ligne
        # Format : "UNIT_SITHPALPATINE_NAME:Sith Eternal Emperor"
        names: dict[str, str] = {}
        for line in bundle.splitlines():
            if "_NAME:" in line and "UNIT_" in line:
                key, _, value = line.partition(":")
                # key = "UNIT_SITHPALPATINE_NAME" → base_id = "SITHPALPATINE"
                base_id = key.replace("UNIT_", "").replace("_NAME", "")
                names[base_id] = value.strip()
        if names:
            _cache = names
            log.info("Cache noms chargé depuis Comlink : %d unités", len(names))
            return
    except Exception:
        log.debug("Comlink /localization indisponible, utilisation du dictionnaire statique")

    _cache = dict(_STATIC_NAMES)
    log.info("Cache noms chargé depuis dictionnaire statique : %d unités", len(_cache))


def get_name(base_id: str) -> str:
    """
    Traduit un base_id en nom affiché.
    Retourne le base_id formaté si inconnu.
    """
    if not _cache:
        # Fallback immédiat sans await si le cache n'est pas initialisé
        return _STATIC_NAMES.get(base_id.upper(), base_id.replace("_", " ").title())
    return _cache.get(base_id.upper(), _STATIC_NAMES.get(base_id.upper(), base_id.replace("_", " ").title()))
