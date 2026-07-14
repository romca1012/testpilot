"""Résolution des modèles Anthropic (Incrément 0 : fournisseur unique).

Trois rôles, chacun résolu depuis ``config`` (surchargeable par .env) :
  - ``generation`` : raisonnement spec→test (défaut Sonnet).
  - ``fast``       : analyse de spec, résumés (défaut Haiku).
  - ``repair``     : cycles de réparation courts (défaut Haiku).
"""

from __future__ import annotations

from testpilot import config

_ROLES: dict[str, str] = {
    "generation": config.MODEL_GENERATION,
    "fast": config.MODEL_FAST,
    "repair": config.MODEL_REPAIR,
}


def resolve(role_or_model: str = "auto") -> str:
    """Retourne un identifiant de modèle Anthropic concret.

    Accepte un rôle (``generation`` | ``fast`` | ``repair``), ``auto`` (→ generation),
    ou un identifiant déjà explicite (retourné tel quel).
    """
    if not role_or_model or role_or_model == "auto":
        return _ROLES["generation"]
    return _ROLES.get(role_or_model, role_or_model)
