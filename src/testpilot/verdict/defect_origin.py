"""Origine du défaut + garde-fou de confirmation humaine ASYMÉTRIQUE (§5).

À partir de la cause racine (``defect_taxonomy``), on décide si un échec est un
« test à réparer » ou un « vrai bug » — et surtout le régime de confirmation :

- « test à réparer » (non-bloquant) DOIT être confirmé par un humain avant classement
  définitif : le classer à tort masquerait un vrai bug (faux négatif inacceptable).
- « vrai bug » peut être remonté DIRECTEMENT (un faux positif est acceptable).
- indéterminé → confirmation humaine par prudence.

Module PUR.
"""

from __future__ import annotations

from dataclasses import dataclass

from testpilot.verdict import defect_taxonomy as dt

# Origines
TEST_A_REPARER = "test_a_reparer"
VRAI_BUG = "vrai_bug"
INDETERMINE = "indetermine"
# Régimes de confirmation (miroir de la colonne repair_attempt.confirmation_status)
PENDING_HUMAN = "pending_human"
NOT_REQUIRED = "not_required"

_ORIGIN_BY_CAUSE = {
    dt.ASSERTION_MISMATCH: VRAI_BUG,           # l'app répond faux → constat produit direct
    dt.MISSING_SERVER_CONTEXT: TEST_A_REPARER,
    dt.WRONG_NAVIGATION: TEST_A_REPARER,
    dt.WRONG_FIELD_NAME: TEST_A_REPARER,
    dt.MISSING_ROLE: TEST_A_REPARER,
    dt.UNKNOWN: INDETERMINE,
}


@dataclass
class DefectVerdict:
    cause_category: str
    defect_origin: str
    confirmation_status: str

    @property
    def requires_human_confirmation(self) -> bool:
        return self.confirmation_status == PENDING_HUMAN


def classify_defect_origin(cause_category: str) -> str:
    return _ORIGIN_BY_CAUSE.get(cause_category, INDETERMINE)


def confirmation_for(defect_origin: str) -> str:
    """Asymétrie §5 : seul « vrai bug » se remonte sans confirmation humaine."""
    return NOT_REQUIRED if defect_origin == VRAI_BUG else PENDING_HUMAN


def diagnose(failures) -> DefectVerdict | None:
    """Diagnostic d'un ensemble d'échecs (cause dominante). None si aucun échec."""
    cause = dt.dominant_category(failures)
    if cause is None:
        return None
    origin = classify_defect_origin(cause)
    return DefectVerdict(cause_category=cause, defect_origin=origin,
                         confirmation_status=confirmation_for(origin))
