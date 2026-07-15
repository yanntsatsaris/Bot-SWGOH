"""
services/gac_planner.py
Planifie des équipes d'attaque et de défense en croisant la Meta GAC globale (swgoh.gg)
avec le roster réel du joueur.
"""
import json
import logging
from services.comlink import get_player
from database.db import get_db

logger = logging.getLogger("gac_planner")

class GacPlanner:
    def __init__(self):
        pass

    async def get_team_suggestions(
        self, 
        ally_code: str, 
        format_type: str = "5v5", 
        mode: str = "defense",
        min_relic: int = -1,
        min_gear: int = 12
    ) -> list[dict]:
        """
        Retourne une liste d'équipes suggérées (par ordre de performance) 
        que le joueur possède réellement.
        
        mode = "defense" ou "attack"
        """
        # 1. Récupérer le roster du joueur
        profile = await get_player(ally_code)
        if not profile:
            logger.error(f"Impossible de récupérer le profil pour {ally_code}")
            return []

        roster = profile.get("rosterUnit", [])
        
        # Indexer le roster pour un accès rapide
        # Clé = definitionId (base_id), Valeur = dict(relic, gear, stars)
        player_units = {}
        for unit in roster:
            def_id = unit.get("definitionId", "")
            base_id = def_id.split(":")[0] if ":" in def_id else def_id
            
            raw_relic = (unit.get("relic") or {}).get("currentTier", 0)
            relic = max(0, raw_relic - 2) if raw_relic >= 2 else 0
            gear = unit.get("currentTier", 0)
            
            player_units[base_id] = {
                "relic": relic,
                "gear": gear,
                "stars": unit.get("currentRarity", 0)
            }

        # 2. Récupérer la meta de la BDD
        async with get_db() as db:
            # Pour la défense, on se base sur hold_percent, pour l'attaque sur seen
            order_by = "hold_percent DESC" if mode == "defense" else "seen DESC"
            
            # On récupère plus de lignes pour avoir une bonne base statistique par leader
            async with db.execute(
                f"SELECT squad_units, seen, hold_percent, avg_banners FROM gac_global_meta WHERE format = ? AND mode = ? ORDER BY {order_by} LIMIT 500",
                (format_type, mode)
            ) as cur:
                meta_rows = await cur.fetchall()

        from services.portrait_cache import get_unit_name
        import re

        slug_to_base = {}
        for base_id in player_units.keys():
            name = get_unit_name(base_id)
            if name:
                computed_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
                slug_to_base[computed_slug] = base_id
            slug_to_base[base_id.lower()] = base_id

        # 3. Grouper par Leader et calculer les scores des membres
        leaders_data = {}
        
        for row in meta_rows:
            raw_units = json.loads(row["squad_units"])
            if not raw_units or len(raw_units) == 0:
                continue

            units = []
            for slug in raw_units:
                base = slug_to_base.get(slug.lower())
                if not base:
                    base = slug_to_base.get(slug.lower().replace("-", ""))
                if base:
                    units.append(base)
                else:
                    units.append(slug.upper())

            leader_id = units[0]
            members = units[1:]

            # Certains personnages sont TOUJOURS en leader dans leur équipe méta.
            # Si swgoh.gg les met ailleurs dans la liste, on les remonte en position 0.
            FORCED_LEADERS = {
                "JABBATHEHUTT", "GLLEIA", "GLREY", "GLAHSOKATANO",
                "SUPREMELEADERKYLOREN", "LORDVADER", "SITHPALPATINE",
                "JEDIMASTERKENOBI", "JEDIMASTERLUKESKYWALKER",
            }
            for forced in FORCED_LEADERS:
                if forced in units and units[0] != forced:
                    units.remove(forced)
                    units.insert(0, forced)
                    leader_id = forced
                    members = units[1:]
                    break
            seen = row["seen"] or 0
            hold_percent = row["hold_percent"] or 0

            if leader_id not in leaders_data:
                leaders_data[leader_id] = {
                    "leader_score": hold_percent if mode == "defense" else seen,
                    "members_freq": {},
                    "best_hold": hold_percent,
                    "best_banners": row["avg_banners"]
                }
            
            # Mettre à jour le score global du leader (le max)
            if mode == "defense" and hold_percent > leaders_data[leader_id]["leader_score"]:
                leaders_data[leader_id]["leader_score"] = hold_percent
                leaders_data[leader_id]["best_hold"] = hold_percent
                leaders_data[leader_id]["best_banners"] = row["avg_banners"]
            elif mode == "attack" and seen > leaders_data[leader_id]["leader_score"]:
                leaders_data[leader_id]["leader_score"] = seen
                leaders_data[leader_id]["best_hold"] = hold_percent
                leaders_data[leader_id]["best_banners"] = row["avg_banners"]

            # Ajouter la fréquence d'apparition pour chaque membre
            for m in members:
                if m not in leaders_data[leader_id]["members_freq"]:
                    leaders_data[leader_id]["members_freq"][m] = 0
                leaders_data[leader_id]["members_freq"][m] += seen

        # 4. Trier les leaders par leur score global
        sorted_leaders = sorted(
            leaders_data.items(), 
            key=lambda x: x[1]["leader_score"], 
            reverse=True
        )

        suggestions = []
        used_characters = set()
        target_team_size = 5 if format_type == "5v5" else 3

        # 5. Construire les équipes en piochant dans les personnages disponibles
        for leader_id, l_data in sorted_leaders:
            # Vérifier si le joueur possède le leader au bon niveau
            if leader_id not in player_units:
                continue
                
            leader_stats = player_units[leader_id]
            if min_relic >= 0 and leader_stats["relic"] < min_relic:
                continue
            if leader_stats["gear"] < min_gear:
                continue
            
            if leader_id in used_characters:
                continue
                
            # Trier les candidats pour ce leader par fréquence d'apparition (les plus utilisés d'abord)
            sorted_candidates = sorted(
                l_data["members_freq"].items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            valid_members = []
            
            for candidate_id, _ in sorted_candidates:
                if candidate_id not in player_units:
                    continue
                
                stats = player_units[candidate_id]
                if min_relic >= 0 and stats["relic"] < min_relic:
                    continue
                if stats["gear"] < min_gear:
                    continue
                    
                if candidate_id in used_characters:
                    continue
                    
                valid_members.append(candidate_id)
                if len(valid_members) == target_team_size - 1:
                    break # On a assez de membres
            
            # En défense, on exige une équipe complète (0 trou). 
            # En attaque, on pourrait tolérer un trou, mais pour l'instant on garde la même exigence pour avoir des bonnes suggestions.
            if len(valid_members) == target_team_size - 1:
                suggestions.append({
                    "leader": leader_id,
                    "members": valid_members,
                    "valid_members": [leader_id] + valid_members,
                    "missing_units": [], # Par définition, il n'y a plus de "missing" car on compose avec ce qu'on a
                    "seen": l_data["leader_score"] if mode == "attack" else 0, # Juste pour info
                    "hold_percent": l_data["best_hold"],
                    "avg_banners": l_data["best_banners"]
                })
                
                used_characters.add(leader_id)
                for u in valid_members:
                    used_characters.add(u)
                
                if len(suggestions) >= 15:
                    break
                    
        return suggestions
