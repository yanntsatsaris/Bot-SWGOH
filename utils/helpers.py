"""
utils/helpers.py — Fonctions utilitaires génériques
"""
import re


def format_ally_code(ally_code: str) -> str:
    """
    Normalise un code allié SWGOH au format XXX-XXX-XXX.

    Args:
        ally_code: Chaîne brute saisie par l'utilisateur.

    Returns:
        Code allié formaté, ex : "123-456-789".

    Raises:
        ValueError: Si la chaîne ne contient pas exactement 9 chiffres.
    """
    digits = re.sub(r"\D", "", ally_code)
    if len(digits) != 9:
        raise ValueError(
            "Le code allié doit contenir exactement 9 chiffres (ex : 123-456-789)."
        )
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
