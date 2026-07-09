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
            # Pour la défense, on trie par hold_percent. Pour l'attaque, par seen ou un ratio.
            order_by = "hold_percent DESC" if mode == "defense" else "seen DESC"
            
            async with db.execute(
                f"SELECT squad_units, seen, hold_percent, avg_banners FROM gac_global_meta WHERE format = ? AND mode = ? ORDER BY {order_by} LIMIT 100",
                (format_type, mode)
            ) as cur:
                meta_rows = await cur.fetchall()

        suggestions = []
        used_characters = set() # Pour éviter de suggérer deux équipes avec le même personnage clé

        from services.portrait_cache import get_unit_name
        import re

        slug_to_base = {}
        for base_id in player_units.keys():
            name = get_unit_name(base_id)
            if name:
                computed_slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
                slug_to_base[computed_slug] = base_id
            slug_to_base[base_id.lower()] = base_id

        # 3. Évaluer chaque squad de la meta par rapport au roster du joueur
        for row in meta_rows:
            raw_units = json.loads(row["squad_units"])
            if not raw_units:
                continue

            # Traduire les slugs en base_ids
            units = []
            for slug in raw_units:
                base = slug_to_base.get(slug.lower())
                if not base:
                    # Fallback on removing hyphens
                    base = slug_to_base.get(slug.lower().replace("-", ""))
                if base:
                    units.append(base)
                else:
                    units.append(slug.upper()) # fallback

            leader_id = units[0]
            
            # Vérifier si le joueur possède le leader avec un niveau minimum
            if leader_id not in player_units:
                continue
                
            leader_stats = player_units[leader_id]
            if min_relic >= 0 and leader_stats["relic"] < min_relic:
                continue
            if leader_stats["gear"] < min_gear:
                continue
            
            # Vérifier que le leader n'a pas déjà été utilisé dans une suggestion précédente
            if leader_id in used_characters:
                continue
                
            # Calculer la complétion de l'équipe
            missing_units = []
            valid_members = []
            
            for unit_id in units:
                if unit_id not in player_units:
                    missing_units.append(unit_id)
                else:
                    stats = player_units[unit_id]
                    if (min_relic >= 0 and stats["relic"] < min_relic) or (stats["gear"] < min_gear):
                        missing_units.append(unit_id)
                    else:
                        valid_members.append(unit_id)

            # Ne proposer que les équipes où le joueur a la majorité des personnages au bon niveau
            max_missing = 1 if format_type == "5v5" else 0
            if len(missing_units) <= max_missing:
                # Vérifier qu'aucun autre personnage clé (ex: Galactic Legends) n'est réutilisé
                # Une approche simple : on marque tous les personnages de l'équipe comme utilisés
                # (Dans une v2, on pourrait n'interdire que les Core members)
                conflict = False
                for u in valid_members:
                    if u in used_characters:
                        conflict = True
                        break
                
                if conflict:
                    continue
                    
                suggestions.append({
                    "leader": leader_id,
                    "members": units[1:], # tous les autres
                    "valid_members": valid_members,
                    "missing_units": missing_units,
                    "seen": row["seen"],
                    "hold_percent": row["hold_percent"],
                    "avg_banners": row["avg_banners"]
                })
                
                # Marquer les personnages comme utilisés pour ne pas les suggérer 2 fois
                for u in valid_members:
                    used_characters.add(u)
                
                # On limite le nombre de suggestions
                if len(suggestions) >= 15:
                    break
                    
        return suggestions
