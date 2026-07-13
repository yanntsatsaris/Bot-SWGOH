import json
import sys
sys.path.append('c:/Users/yann/Documents/Projet/Bot-SWGOH')
from services.gac_meta import GAC_TEAMS

def simulate():
    teams = [
        {"leader_id": "SUPREMELEADERKYLOREN", "members": ["KYLORENUNMASKED", "GENERALHUX"]},
        {"leader_id": "THIRDSISTER", "members": ["GRANDINQUISITOR", "FIFTHBROTHER"]},
        {"leader_id": "DARTHREVAN", "members": ["MISSIONVAO", "ZAALBAR"]},
        {"leader_id": "DARTHSIDIOUS", "members": ["COUNTDOOKU", "DIRECTORKRENNIC"]},
        {"leader_id": "ADMINISTRATORLANDO", "members": ["ZEBS3", "EZRABRIDGERS3"]}
    ]
    used_base_ids = set()
    fmt = "3v3"

    for t in teams:
        leader = t["leader_id"]
        members = t["members"]
        valid_members = [m for m in members if m not in used_base_ids]
        
        known_meta_for_leader = [mt for mt in GAC_TEAMS.values() if mt["leader_id"] == leader and mt["format"] == fmt]
        
        if known_meta_for_leader:
            has_synergy = False
            for mt in known_meta_for_leader:
                meta_members_set = set(mt.get("core", []) + mt.get("subs", []))
                overlap = len(set(valid_members).intersection(meta_members_set))
                if overlap > 0:
                    has_synergy = True
                    break
            
            if not has_synergy and len(valid_members) > 0:
                print(f"[{leader}] REJECTED BY ANTI-GARBAGE! valid_members={valid_members}")
                continue
                
        print(f"[{leader}] ACCEPTED!")
        used_base_ids.add(leader)
        used_base_ids.update(valid_members)

if __name__ == "__main__":
    simulate()
