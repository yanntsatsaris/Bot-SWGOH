"""
services/gac_analysis.py — Logique métier d'analyse GAC via Comlink
"""
import logging

from services.comlink import get_player, get_player_arena

log = logging.getLogger(__name__)

# Tabs Comlink : 1 = Arène Escouade, 2 = Flotte, 3 = Grande Arène (GAC)
_GAC_TAB = 3
_ARENA_TAB = 1


def _parse_squad(cells: list[dict]) -> list[str]:
    """
    Extrait les base_id des personnages depuis les cellules d'un squad.
    unitDefId format : 'BASE_ID:SEVEN_STAR' → on coupe avant ':'
    Le leader a squadUnitType == 2.
    """
    # Tri : leader (type 2) en premier, puis les membres (type 1)
    sorted_cells = sorted(cells, key=lambda c: 0 if c.get("squadUnitType") == 2 else 1)
    return [
        c["unitDefId"].split(":")[0]
        for c in sorted_cells
        if c.get("unitDefId")
    ]


async def get_player_gac_stats(ally_code: str) -> dict:
    """
    Récupère et normalise les statistiques GAC d'un joueur via Comlink.

    Args:
        ally_code: Code allié normalisé (format XXX-XXX-XXX).

    Returns:
        Dictionnaire avec les clés :
        username, ally_code, gac_rank, arena_rank,
        gac_squad (liste de base_id), arena_squad (liste de base_id).
    """
    clean = ally_code.replace("-", "")

    # Récupération en parallèle du profil et de l'arène
    player_raw  = await get_player(clean)
    arena_raw   = await get_player_arena(clean)

    username = player_raw.get("name", "Inconnu")

    # Indexer les tabs par numéro
    pvp: dict[int, dict] = {
        p["tab"]: p
        for p in arena_raw.get("pvpProfile", [])
    }

    # --- GAC (tab 3) ---
    gac_profile  = pvp.get(_GAC_TAB, {})
    gac_rank     = gac_profile.get("rank")
    gac_cells    = gac_profile.get("squad", {}).get("cell", [])
    gac_squad    = _parse_squad(gac_cells) if gac_cells else []

    # --- Arène escouade (tab 1) ---
    arena_profile = pvp.get(_ARENA_TAB, {})
    arena_rank    = arena_profile.get("rank")
    arena_cells   = arena_profile.get("squad", {}).get("cell", [])
    arena_squad   = _parse_squad(arena_cells) if arena_cells else []

    return {
        "username":    username,
        "ally_code":   ally_code,
        "gac_rank":    gac_rank,
        "gac_squad":   gac_squad,
        "arena_rank":  arena_rank,
        "arena_squad": arena_squad,
    }
