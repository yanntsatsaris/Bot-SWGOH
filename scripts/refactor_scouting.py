import re

def refactor_predict_zones():
    filepath = r"c:\Users\yann\Documents\Projet\Bot-SWGOH\services\scouting.py"
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
        
    # Extraire le bloc META (1. PERSONNAGES)
    meta_start = content.find("    # 1. PERSONNAGES (Via la Meta Dynamique de swgoh.gg)")
    meta_end = content.find("    # Identification des personnages strictement réservés à l'attaque", meta_start)
    meta_block = content[meta_start:meta_end]
    
    # Extraire le bloc HISTOIRE (0. INJECTION DE L'HISTORIQUE RÉEL)
    histo_start = content.find("    # 0. INJECTION DE L'HISTORIQUE RÉEL")
    histo_end = meta_start
    histo_block = content[histo_start:histo_end]
    
    # Nouveau bloc HISTOIRE avec logique de remplacement
    new_histo_block = """    # 0. INJECTION DE L'HISTORIQUE RÉEL (Avec logique d'Upgrade)
    if habits and habits.get("total_rounds", 0) > 0:
        mapping = {"top": "North", "bottom": "South", "back": "Back", "fleet": "Fleet"}
        for hz, h_name in mapping.items():
            teams = habits["zones"].get(hz, [])
            quota = quotas.get(h_name, 0)
            
            for t in teams[:quota]:
                leader = t["leader_id"]
                members = t["members"]
                percent = t["percent"]
                
                valid_members = [m for m in members if m not in used_base_ids]
                if leader not in used_base_ids:
                    # Logique de remplacement (Upgrade)
                    best_upgrade = None
                    if hz != "fleet":
                        # Chercher si une équipe Meta partage des personnages clés et est plus forte
                        history_set = set([leader] + valid_members)
                        
                        for meta_team in available_teams:
                            if meta_team["leader_id"] in used_base_ids:
                                continue
                                
                            meta_set = set([meta_team["leader_id"]] + meta_team["members"])
                            overlap = len(history_set.intersection(meta_set))
                            
                            # Si on a un chevauchement significatif (au moins 2 persos en 5v5, 1 ou 2 en 3v3)
                            # Ou si le leader est le même mais la compo Meta est meilleure
                            # Et que le score de défense de la Meta est très bon
                            if overlap >= (1 if expected_size == 3 else 2) or leader == meta_team["leader_id"]:
                                # Un upgrade est valide si la Meta a un meilleur score défensif strict
                                # ou si la Meta contient des personnages Premium (GL, Reva, Bane) non présents historiquement
                                premium_units = ["THIRDSISTER", "GLREY", "JEDIMASTERKENOBI", "SUPREMELEADERKYLOREN", "SITHPALPATINE", "JEDIMASTERLUKE", "LORDVADER", "JABBATHEHUTT", "LEIAORGANA", "DARTHBANE", "TARONMALICOS", "BOKATANMANDALOR"]
                                has_new_premium = any(p in meta_set and p not in history_set for p in premium_units)
                                
                                # On simule le score def de l'équipe historique si c'était une Meta
                                # Pour simplifier, on dit que si la Meta a >= 7 en défense ou a un premium, on upgrade.
                                # Sauf si l'historique a déjà un excellent percent (ex: > 80%).
                                if (meta_team["defense"] >= 7 or has_new_premium) and percent < 90:
                                    if best_upgrade is None or meta_team["defense"] > best_upgrade["defense"]:
                                        best_upgrade = meta_team
                                        
                    if best_upgrade:
                        # Remplacement par l'Upgrade
                        upgrade_leader = best_upgrade["leader_id"]
                        upgrade_members = best_upgrade["members"]
                        
                        zones[h_name].append({
                            "leader_id": upgrade_leader,
                            "members_ids": upgrade_members,
                            "source": f"Upgrade (Ancien: {leader})",
                            "target_size": expected_size
                        })
                        used_base_ids.add(upgrade_leader)
                        used_base_ids.update(upgrade_members)
                        # On retire l'équipe Meta des available_teams pour ne pas la réutiliser
                        best_upgrade["leader_id"] = "USED"
                    else:
                        # Ajout classique de l'équipe historique
                        zones[h_name].append({
                            "leader_id": leader,
                            "members_ids": valid_members,
                            "source": f"Historique ({percent}%)",
                            "target_size": expected_size if hz != "fleet" else 8
                        })
                        used_base_ids.add(leader)
                        used_base_ids.update(valid_members)
    
"""
    
    # Remplacer dans le code
    new_content = content[:histo_start] + meta_block + new_histo_block + content[meta_end:]
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
        
    print("Refactoring terminé avec succès.")

if __name__ == "__main__":
    refactor_predict_zones()
