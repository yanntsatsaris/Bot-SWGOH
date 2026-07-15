"""
services/gac_meta.py — Définitions centralisées des équipes et flottes
Intègre le système Core/Subs pour s'adapter au Roster du joueur et séparer le 3v3 du 5v5.
"""

GAC_TEAMS = {
    # ==========================================
    #             GALACTIC LEGENDS
    # ==========================================
    "GLLEIA_5V5": {
        "leader_id": "GLLEIA", "format": "5v5", "offense": 10, "defense": 2,
        "core": ["GLLEIA", "CAPTAINDROGAN", "R2D2_LEGENDARY"],
        "subs": ["BAZEMALBUS", "MONMOTHMA", "CHIRRUTIMWE", "BENSOLO", "OLDBENKENOBI"],
        "role": "offense"  # Equipe attaque uniquement, ne tient pas en défense
    },
    "GLLEIA_3V3": {
        "leader_id": "GLLEIA", "format": "3v3", "offense": 10, "defense": 2,
        "core": ["GLLEIA", "CAPTAINDROGAN", "R2D2_LEGENDARY"],
        "subs": [],
        "role": "offense"  # Equipe attaque uniquement, ne tient pas en défense
    },
    
    "GLAHSOKATANO_5V5": {
        "leader_id": "GLAHSOKATANO", "format": "5v5", "offense": 10, "defense": 9,
        "core": ["GLAHSOKATANO"],
        "subs": ["EZRABRIDGEREXILE", "PADAWANSABINEWREN", "HUYANG", "GENERALSYNDULLA"]
    },
    "GLAHSOKATANO_3V3": {
        "leader_id": "GLAHSOKATANO", "format": "3v3", "offense": 9, "defense": 9,
        "core": ["GLAHSOKATANO"],
        "subs": ["EZRABRIDGEREXILE", "GENERALSYNDULLA"]
    },
    "GLAHSOKATANO_3V3_NOEZRA": {
        "leader_id": "GLAHSOKATANO", "format": "3v3", "offense": 7, "defense": 7,
        "core": ["GLAHSOKATANO"],
        "subs": ["HUYANG", "GENERALSYNDULLA"]
    },
    
    "SLKR_5V5": {
        "leader_id": "SUPREMELEADERKYLOREN", "format": "5v5", "offense": 10, "defense": 9,
        "core": ["SUPREMELEADERKYLOREN"],
        "subs": ["GENERALHUX", "KYLORENUNMASKED", "FIRSTORDERTIEPILOT", "SITHTROOPER", "FIRSTORDERSTORMTROOPER", "KYLOREN", "FIRSTORDEREXECUTIONER", "FIRSTORDERSPECIALFORCES", "CAPTAINPHASMA", "FIRSTORDEROFFICER"],
        "role": "offense"
    },
    "SLKR_DSREY_3V3": {
        "leader_id": "SUPREMELEADERKYLOREN", "format": "3v3", "offense": 10, "defense": 9,
        "core": ["SUPREMELEADERKYLOREN"], 
        "subs": ["DARKREVISION", "KYLORENUNMASKED", "SITHTROOPER", "FIRSTORDERTIEPILOT", "GENERALHUX"],
        "role": "offense"
    },
    "SLKR_HUX_3V3": {
        "leader_id": "SUPREMELEADERKYLOREN", "format": "3v3", "offense": 8, "defense": 7,
        "core": ["SUPREMELEADERKYLOREN", "GENERALHUX", "FIRSTORDERSTORMTROOPER"],
        "subs": ["SITHTROOPER"]
    },
    
    "DARTHBANE_5V5": {
        "leader_id": "DARTHBANE", "format": "5v5", "offense": 9, "defense": 1,
        "core": ["DARTHBANE", "SITHASSASSIN"],
        "subs": [],
        "min_size": 2
    },
    "DARTHBANE_3V3": {
        "leader_id": "DARTHBANE", "format": "3v3", "offense": 9, "defense": 1,
        "core": ["DARTHBANE", "SITHASSASSIN"],
        "subs": []
    },
    "SEE_BANE_3V3": {
        "leader_id": "SITHPALPATINE", "format": "3v3", "offense": 9, "defense": 1,
        "core": ["SITHPALPATINE", "DARTHBANE"],
        "subs": []
    },
    "SEE_5V5": {
        "leader_id": "SITHPALPATINE", "format": "5v5", "offense": 8, "defense": 7,
        "core": ["SITHPALPATINE"],
        "subs": ["DARTHREVAN", "DARTHMALAK", "SAVAGEOPRESS", "DARTHTALON", "SITHASSASSIN", "COUNTDOOKU", "SITHMARAUDER", "SITHTROOPER", "DARTHSION", "DARTHNIHILUS"],
        "role": "offense"
    },
    "SEE_3V3": {
        "leader_id": "SITHPALPATINE", "format": "3v3", "offense": 7, "defense": 7,
        "core": ["SITHPALPATINE"],
        "subs": ["DARTHMALAK", "DARTHTALON", "SAVAGEOPRESS", "DARTHREVAN", "SITHASSASSIN"],
        "role": "offense"
    },

    "JMK_5V5": {
        "leader_id": "JEDIMASTERKENOBI", "format": "5v5", "offense": 9, "defense": 8,
        "core": ["JEDIMASTERKENOBI", "COMMANDERAHSOKA"],
        "subs": ["AHSOKATANO", "GENERALKENOBI", "PADMEAMIDALA", "MACEWINDU"]
    },
    "JMK_3V3": {
        "leader_id": "JEDIMASTERKENOBI", "format": "3v3", "offense": 8, "defense": 8,
        "core": ["JEDIMASTERKENOBI", "COMMANDERAHSOKA"],
        "subs": ["GENERALKENOBI", "AHSOKATANO"]
    },
    
    "JABBA_5V5": {
        "leader_id": "JABBATHEHUTT", "format": "5v5", "offense": 9, "defense": 8,
        "core": ["JABBATHEHUTT", "KRRSANTAN", "BOUSHH"],
        "subs": ["UNDERCOVERLANDO", "EMBO", "BOBAFETT"]
    },
    "JABBA_3V3": {
        "leader_id": "JABBATHEHUTT", "format": "3v3", "offense": 8, "defense": 8,
        "core": ["JABBATHEHUTT", "KRRSANTAN", "BOUSHH"],
        "subs": []
    },

    "LORDVADER_5V5": {
        "leader_id": "LORDVADER", "format": "5v5", "offense": 9, "defense": 8,
        "core": ["LORDVADER", "MAULS7"],
        "subs": ["GRANDADMIRALTHRAWN", "ROYALGUARD", "VADER", "STORMTROOPER"]
    },
    "LORDVADER_CLONES_3V3": {
        "leader_id": "LORDVADER", "format": "3v3", "offense": 9, "defense": 9,
        "core": ["LORDVADER"],
        "subs": ["CX2", "CC1119APPO", "ROYALGUARD", "STORMTROOPER"]
    },
    "LORDVADER_MAUL_3V3": {
        "leader_id": "LORDVADER", "format": "3v3", "offense": 8, "defense": 7,
        "core": ["LORDVADER", "MAULS7"],
        "subs": ["GRANDADMIRALTHRAWN", "ROYALGUARD"]
    },

    "GLREY_5V5": {
        "leader_id": "GLREY", "format": "5v5", "offense": 8, "defense": 9,
        "core": ["GLREY", "BENSOLO"],
        "subs": ["CALKESTIS", "REYJEDITRAINING", "EZRABRIDGEREXILE", "AMILYNHOLDO", "L3_37", "FINN", "POE", "BB8", "RESISTANCEHEROFINN", "RESISTANCEHEROPOE"]
    },
    "REYZRA_3V3": {
        "leader_id": "GLREY", "format": "3v3", "offense": 9, "defense": 9,
        "core": ["GLREY", "EZRABRIDGEREXILE", "BENSOLO"],
        "subs": []
    },
    "GLREY_3V3": {
        "leader_id": "GLREY", "format": "3v3", "offense": 8, "defense": 8,
        "core": ["GLREY", "BENSOLO"],
        "subs": ["CALKESTIS", "REYJEDITRAINING", "L3_37"]
    },
    
    "JMLS_5V5": {
        "leader_id": "JEDIMASTERLUKESKYWALKER", "format": "5v5", "offense": 8, "defense": 7,
        "core": ["JEDIMASTERLUKESKYWALKER", "JEDIKNIGHTREVAN", "JEDIKNIGHTLUKESKYWALKER"],
        "subs": ["JEDIKNIGHTCALKESTIS", "GRANDMASTERYODA", "HERMITYODA", "SHAAKTI"]
    },
    "JMLS_3V3": {
        "leader_id": "JEDIMASTERLUKESKYWALKER", "format": "3v3", "offense": 8, "defense": 7,
        "core": ["JEDIMASTERLUKESKYWALKER"],
        "subs": ["HERMITYODA", "JEDIKNIGHTLUKESKYWALKER", "JEDIKNIGHTCALKESTIS", "JEDIKNIGHTREVAN"]
    },
    
    # ==========================================
    #             BESKAR & KYBER TIER
    # ==========================================
    "REVA_5V5": {
        "leader_id": "THIRDSISTER", "format": "5v5", "offense": 9, "defense": 7,
        "core": ["THIRDSISTER", "GRANDINQUISITOR", "SEVENTHSISTER"],
        "subs": ["FIFTHBROTHER", "EIGHTHBROTHER", "NINTHSISTER"]
    },
    "REVA_3V3": {
        "leader_id": "THIRDSISTER", "format": "3v3", "offense": 8, "defense": 7,
        "core": ["THIRDSISTER", "GRANDINQUISITOR", "SEVENTHSISTER"],
        "subs": []
    },
    
    "QUADME_5V5": {
        "leader_id": "QUEENAMIDALA", "format": "5v5", "offense": 7, "defense": 8,
        "core": ["QUEENAMIDALA", "PADAWANOBIWAN", "MASTERQUIGON"],
        "subs": ["CT210408", "SHAAKTI", "BARRISSOFFEE"]
    },
    "QUADME_3V3": {
        "leader_id": "QUEENAMIDALA", "format": "3v3", "offense": 7, "defense": 8,
        "core": ["QUEENAMIDALA", "PADAWANOBIWAN", "MASTERQUIGON"],
        "subs": []
    },
    
    "BAYLANSKOLL_5V5": {
        "leader_id": "BAYLANSKOLL", "format": "5v5", "offense": 8, "defense": 7,
        "core": ["BAYLANSKOLL", "SHIN_HATI", "MARROK"],
        "subs": ["VANDORCHEWBACCA", "L3_37", "ENFYSNEST", "IG11", "KUIIL", "HONDOHNAKA", "DASHRENDAR", "BAM", "FULCRUMAHSOKA", "KYLORENUNMASKED"]
    },
    "BAYLANSKOLL_3V3": {
        "leader_id": "BAYLANSKOLL", "format": "3v3", "offense": 8, "defense": 7,
        "core": ["BAYLANSKOLL", "SHIN_HATI", "MARROK"],
        "subs": []
    },
    
    "CERE_MALICOS_5V5": {
        "leader_id": "CEREJUNDA", "format": "5v5", "offense": 7, "defense": 8,
        "core": ["CEREJUNDA", "TARONMALICOS", "CALKESTIS"],
        "subs": ["FULCRUMAHSOKA", "KYLORENUNMASKED", "REYSCAVENGER"]
    },
    "CERE_MALICOS_3V3": {
        "leader_id": "CEREJUNDA", "format": "3v3", "offense": 7, "defense": 8,
        "core": ["CEREJUNDA", "TARONMALICOS"],
        "subs": ["KYLORENUNMASKED", "CALKESTIS"]
    },

    "BOSSNASS_5V5": {
        "leader_id": "BOSSNASS", "format": "5v5", "offense": 7, "defense": 7,
        "core": ["BOSSNASS", "JARJARBINKS", "CAPTAINTARPALS", "GUNGANPHALANX"],
        "subs": ["BOOMADIER"]
    },
    "BOSSNASS_3V3": {
        "leader_id": "BOSSNASS", "format": "3v3", "offense": 7, "defense": 7,
        "core": ["BOSSNASS", "JARJARBINKS", "GUNGANPHALANX"],
        "subs": []
    },

    "BOKATANMANDALOR_5V5": {
        "leader_id": "BOKATANMANDALOR", "format": "5v5", "offense": 7, "defense": 7,
        "core": ["BOKATANMANDALOR", "PAZVIZSLA", "IG12"],
        "subs": ["THEMANDALORIANBESKARARMOR", "BOKATAN", "ARMORER"]
    },
    "BOKATANMANDALOR_3V3": {
        "leader_id": "BOKATANMANDALOR", "format": "3v3", "offense": 8, "defense": 6,
        "core": ["BOKATANMANDALOR", "IG12", "PAZVIZSLA"],
        "subs": []
    },

    "STARKILLER_5V5": {
        "leader_id": "EMPERORPALPATINE", "format": "5v5", "offense": 8, "defense": 6,
        "core": ["EMPERORPALPATINE", "STARKILLER", "MARAJADE"],
        "subs": ["VISASMARR", "OBIWANKE", "JUCANI"]
    },
    "STARKILLER_3V3": {
        "leader_id": "EMPERORPALPATINE", "format": "3v3", "offense": 7, "defense": 6,
        "core": ["EMPERORPALPATINE", "STARKILLER", "MARAJADE"],
        "subs": []
    },

    "GREATMOTHERS_5V5": {
        "leader_id": "GREATMOTHERS", "format": "5v5", "offense": 7, "defense": 6,
        "core": ["GREATMOTHERS", "MORGANELSBETH", "NIGHTSISTERSPIRIT"],
        "subs": ["NIGHTSISTERACOLYTE", "TALIA"]
    },
    "GREATMOTHERS_3V3": {
        "leader_id": "GREATMOTHERS", "format": "3v3", "offense": 7, "defense": 6,
        "core": ["GREATMOTHERS", "MORGANELSBETH", "NIGHTSISTERSPIRIT"],
        "subs": []
    },

    "DARTHMALGUS_5V5": {
        "leader_id": "DARTHMALGUS", "format": "5v5", "offense": 7, "defense": 6,
        "core": ["DARTHMALGUS", "DARTHREVAN", "BASTILASHANDARK"],
        "subs": ["DARTHMALAK", "DARTHTALON", "SITHASSASSIN"]
    },
    "DARTHMALGUS_3V3": {
        "leader_id": "DARTHMALGUS", "format": "3v3", "offense": 7, "defense": 7,
        "core": ["DARTHMALGUS", "DARTHREVAN", "BASTILASHANDARK"],
        "subs": []
    },
    
    "SAWGERRERA_5V5": {
        "leader_id": "SAWGERRERA", "format": "5v5", "offense": 6, "defense": 7,
        "core": ["SAWGERRERA", "LUTHENRAEL", "CAPTAINREX"],
        "subs": ["CHIRRUTIMWE", "BAZEMALBUS", "KYLEKATARN"]
    },
    "SAWGERRERA_3V3": {
        "leader_id": "SAWGERRERA", "format": "3v3", "offense": 6, "defense": 7,
        "core": ["SAWGERRERA", "LUTHENRAEL", "KYLEKATARN"],
        "subs": []
    },
    
    "DARTHTRAYA_5V5": {
        "leader_id": "DARTHTRAYA", "format": "5v5", "offense": 6, "defense": 5,
        "core": ["DARTHTRAYA", "DARTHNIHILUS", "DARTHSION"],
        "subs": ["SITHTROOPER", "SITHEMPIRE", "SAVAGEOPRESS"],
        "role": "offense"
    },
    "DARTHTRAYA_3V3": {
        "leader_id": "DARTHTRAYA", "format": "3v3", "offense": 6, "defense": 5,
        "core": ["DARTHTRAYA", "DARTHNIHILUS", "DARTHSION"],
        "subs": [],
        "role": "offense"
    },

    "DOCTORAPHRA_5V5": {
        "leader_id": "DOCTORAPHRA", "format": "5v5", "offense": 6, "defense": 5,
        "core": ["DOCTORAPHRA", "BT1", "TRIPLEZERO"],
        "subs": ["VADER", "PROBEDROID", "IG88"]
    },
    "DOCTORAPHRA_3V3": {
        "leader_id": "DOCTORAPHRA", "format": "3v3", "offense": 6, "defense": 6,
        "core": ["DOCTORAPHRA", "BT1", "TRIPLEZERO"],
        "subs": []
    },
    
    "MOFFGIDEONDARK_5V5": {
        "leader_id": "MOFFGIDEONDARK", "format": "5v5", "offense": 6, "defense": 6,
        "core": ["MOFFGIDEONDARK", "SCOUTTROOPER_V3", "DEATHTROOPER"],
        "subs": ["MOFFGIDEON", "STORMTROOPER", "SHORETROOPER"]
    },
    "MOFFGIDEONDARK_3V3": {
        "leader_id": "MOFFGIDEONDARK", "format": "3v3", "offense": 6, "defense": 6,
        "core": ["MOFFGIDEONDARK", "SCOUTTROOPER_V3", "DEATHTROOPER"],
        "subs": []
    },
    
    "GENERALSKYWALKER_5V5": {
        "leader_id": "GENERALSKYWALKER", "format": "5v5", "offense": 6, "defense": 6,
        "core": ["GENERALSKYWALKER"],
        "subs": ["CT7567", "CT5555", "ARCTROOPER501ST", "CT210408", "CLONESERGEANTPHASEI", "CC2224", "AHSOKATANO", "BARRISSOFFEE", "SHAAKTI", "BADBATCHECHO", "BADBATCHHUNTER", "BADBATCHTECH", "BADBATCHWRECKER"]
    },
    "GENERALSKYWALKER_3V3": {
        "leader_id": "GENERALSKYWALKER", "format": "3v3", "offense": 6, "defense": 6,
        "core": ["GENERALSKYWALKER"],
        "subs": ["CT210408", "ARCTROOPER501ST", "CT7567", "CT5555"]
    },
    
    "WAMPA_SOLO": {
        "leader_id": "WAMPA", "format": "5v5", "offense": 5, "defense": 1,
        "core": ["WAMPA"], "subs": [],
        "min_size": 1,
        "requires_omicron": ["WAMPA"]
    },
    "WAMPA_SOLO_3V3": {
        "leader_id": "WAMPA", "format": "3v3", "offense": 5, "defense": 1,
        "core": ["WAMPA"], "subs": [],
        "min_size": 1,
        "requires_omicron": ["WAMPA"]
    },
    
    "SAVAGEOPRESS_SOLO": {
        "leader_id": "SAVAGEOPRESS", "format": "5v5", "offense": 5, "defense": 1,
        "core": ["SAVAGEOPRESS"], "subs": [],
        "min_size": 1,
        "requires_omicron": ["SAVAGEOPRESS"]
    },
    "SAVAGEOPRESS_SOLO_3V3": {
        "leader_id": "SAVAGEOPRESS", "format": "3v3", "offense": 5, "defense": 1,
        "core": ["SAVAGEOPRESS"], "subs": [],
        "min_size": 1,
        "requires_omicron": ["SAVAGEOPRESS"]
    },
    
    "IDENVERSIOEMPIRE_3V3": {
        "leader_id": "IDENVERSIOEMPIRE", "format": "3v3", "offense": 5, "defense": 5,
        "core": ["IDENVERSIOEMPIRE", "RANGETROOPER", "SHORETROOPER"],
        "subs": []
    },
    "GRIEVOUS_3V3": {
        "leader_id": "GRIEVOUS", "format": "3v3", "offense": 5, "defense": 5,
        "core": ["GRIEVOUS", "STAP", "MAGNAGUARD"],
        "subs": []
    },
    "ENOCH_3V3": {
        "leader_id": "ENOCH", "format": "3v3", "offense": 5, "defense": 5,
        "core": ["ENOCH", "NIGHTTROOPER", "DEATHTROOPERPERIDEA"],
        "subs": []
    },
    
    "MONMOTHMA_LUTHEN_3V3": {
        "leader_id": "MONMOTHMA", "format": "3v3", "offense": 5, "defense": 5,
        "core": ["MONMOTHMA", "LUTHENRAEL", "KYLEKATARN"],
        "subs": []
    },
    "QUIGONJINN_3V3": {
        "leader_id": "QUIGONJINN", "format": "3v3", "offense": 5, "defense": 4,
        "core": ["QUIGONJINN", "KIADIMUNDI", "JEDIKNIGHTANAKIN"],
        "subs": []
    },
    "TUSKENCHIEFTAIN_3V3": {
        "leader_id": "TUSKENCHIEFTAIN", "format": "3v3", "offense": 4, "defense": 5,
        "core": ["TUSKENCHIEFTAIN", "TUSKENWARRIOR", "TUSKENRAIDER"],
        "subs": []
    },
    "ADMIRALRADDUS_3V3": {
        "leader_id": "ADMIRALRADDUS", "format": "3v3", "offense": 4, "defense": 5,
        "core": ["ADMIRALRADDUS", "JYNERSO", "SCARIFREBEL"],
        "subs": []
    },
    "BOBAFETT_HAN_3V3": {
        "leader_id": "BOBAFETT", "format": "3v3", "offense": 4, "defense": 4,
        "core": ["BOBAFETT", "HANSOLO", "CHEWBACCALEGENDARY"],
        "subs": []
    },
    "DARTHREVAN_SAVAGE_3V3": {
        "leader_id": "DARTHREVAN", "format": "3v3", "offense": 4, "defense": 4,
        "core": ["DARTHREVAN", "BASTILASHANDARK", "SAVAGEOPRESS"],
        "subs": []
    },
    "MOTHERTALZIN_3V3": {
        "leader_id": "MOTHERTALZIN", "format": "3v3", "offense": 5, "defense": 3,
        "core": ["MOTHERTALZIN", "ASAJVENTRESS", "MERRIN"],
        "subs": []
    },
    "COMMANDERLUKESKYWALKER_3V3": {
        "leader_id": "COMMANDERLUKESKYWALKER", "format": "3v3", "offense": 4, "defense": 4,
        "core": ["COMMANDERLUKESKYWALKER", "C3POCHEWBACCA", "C3POLEGENDARY"],
        "subs": []
    },
    
    "JEDIKNIGHTCALKESTIS_3V3": {
        "leader_id": "BASTILASHAN", "format": "3v3", "offense": 5, "defense": 3,
        "core": ["BASTILASHAN", "JEDIKNIGHTCALKESTIS", "MACEWINDU"],
        "subs": []
    },
    "OMEGA_3V3": {
        "leader_id": "HUNTER", "format": "3v3", "offense": 5, "defense": 3,
        "core": ["HUNTER", "CT210408", "TECH"],
        "subs": []
    },
    "PADMEAMIDALA_GIDEON_3V3": {
        "leader_id": "PADMEAMIDALA", "format": "3v3", "offense": 6, "defense": 2,
        "core": ["PADMEAMIDALA", "SHAAKTI", "MOFFGIDEON"],
        "subs": []
    },
    "GRANDINQUISITOR_3V3": {
        "leader_id": "GRANDINQUISITOR", "format": "3v3", "offense": 4, "defense": 4,
        "core": ["GRANDINQUISITOR", "SEVENTHSISTER", "NINTHSISTER"],
        "subs": []
    },
    "SANA_3V3": {
        "leader_id": "SANA", "format": "3v3", "offense": 4, "defense": 4,
        "core": ["SANA", "STORMTROOPERHAN", "CARADUNE"],
        "subs": []
    },
    "DASHRENDAR_3V3": {
        "leader_id": "DASHRENDAR", "format": "3v3", "offense": 4, "defense": 4,
        "core": ["DASHRENDAR", "VANDORCHEWBACCA", "L3_37"],
        "subs": []
    },
    "JEDIKNIGHTREVAN_3V3": {
        "leader_id": "JEDIKNIGHTREVAN", "format": "3v3", "offense": 4, "defense": 3,
        "core": ["JEDIKNIGHTREVAN", "GRANDMASTERYODA", "JOLEEBINDO"],
        "subs": []
    },
    
    # -------------------------------------------------------------
    # Fallback générique : Permet de piocher les subs restants
    # -------------------------------------------------------------
    "GENERIC_5V5": {
        "leader_id": None, "format": "5v5", "offense": 3, "defense": 3,
        "core": [], "subs": []
    }
}

GAC_FLEETS = {
    "CAPITALLEVIATHAN": {"members": ["CAPITALLEVIATHAN", "SITHFIGHTER", "SITHBOMBER", "FURYCLASSINTERCEPTOR", "MKVIINTERCEPTOR", "SITHASSASSIN", "TIEDAGGER", "EBONHAWK"], "defense": 10},
    "CAPITALEXECUTOR": {"members": ["CAPITALEXECUTOR", "HOUNDSTOOTH", "RAZORCREST", "XANADUBLOOD", "IG2000", "SLAVE1", "EBONHAWK", "TIEFIGHTER"], "defense": 10},
    "CAPITALPROFUNDITY": {"members": ["CAPITALPROFUNDITY", "MILLENNIUMFALCON", "OUTRIDER", "YWINGREBEL", "GHOST", "PHANTOM2", "CASSIANSUWING", "BISTANSUWING"], "defense": 8},
    "CAPITALNEGOTIATOR": {"members": ["CAPITALNEGOTIATOR", "JEDISTARFIGHTERANAKIN", "UMBARANSTARFIGHTER", "JEDISTARFIGHTERAHSOKATANO", "YWINGCLONEWARS", "BLADEOFDORIN", "ARC170CLONESERGEANT", "ARC170REX"], "defense": 8},
    "CAPITALMALEVOLENCE": {"members": ["CAPITALMALEVOLENCE", "VULTUREDROID", "HYENABOMBER", "GEONOSIANSTARFIGHTERSUNFAC", "GEONOSIANSTARFIGHTERSPY", "GEONOSIANSTARFIGHTER", "IG2000", "EBONHAWK"], "defense": 7},
    "CAPITALCHIMAERA": {"members": ["CAPITALCHIMAERA", "TIEADVANCED", "TIEBOMBER", "TIEDEFENDER", "TIEINTERCEPTOR", "TIEFIGHTER", "GAUNTLETSTARFIGHTER", "EMPERORSSHUTTLE"], "defense": 6},
    "CAPITALSTARDESTROYER": {"members": ["CAPITALSTARDESTROYER", "TIEADVANCED", "TIEBOMBER", "TIEDEFENDER", "TIEINTERCEPTOR", "TIEFIGHTER", "GAUNTLETSTARFIGHTER", "EMPERORSSHUTTLE"], "defense": 5},
    "CAPITALFINALIZER": {"members": ["CAPITALFINALIZER", "KYLORENSCOMMANDSHUTTLE", "TIESILENCER", "FIRSTORDERSPECIALFORCESTIEFIGHTER", "FIRSTORDERTIEFIGHTER", "FIRSTORDER_ECHELON", "HOUNDSTOOTH", "EBONHAWK"], "defense": 3},
    "CAPITALRADDUS": {"members": ["CAPITALRADDUS", "REYSMILLENNIUMFALCON", "RESISTANCEYWING", "POEDAMERONXWING", "RESISTANCE_XWING", "EBOE_XWING", "LOBOT_XWING", "MILLENNIUMFALCONEP7"], "defense": 5},
}
