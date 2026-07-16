"""Origine du défaut + garde-fou de confirmation humaine ASYMÉTRIQUE (§5).

À partir de la cause racine (``defect_taxonomy``), on décide si un échec est un
« test à réparer » ou un « vrai bug » — et surtout le régime de confirmation :

- « test à réparer » (non-bloquant) DOIT être confirmé par un humain avant classement
  définitif : le classer à tort masquerait un vrai bug (faux négatif inacceptable).
- « vrai bug » peut être remonté DIRECTEMENT (un faux positif est acceptable).
- indéterminé → confirmation humaine par prudence.

⚠️ LIMITE CONNUE (constatée sur données réelles, 2026-07-16). Ce module produit une DÉDUCTION,
jamais un constat : rien ici n'observe l'application, on classe une cause racine elle-même
déduite de mots-clés. Or **aucun diagnostic n'est jamais tranché** — les 8 produits à ce jour ont
`confirmed_by = NULL`, faute d'endpoint et d'écran (décision `0001`, non implémentée) :
  - un `pending_human` attend une confirmation qui ne peut pas arriver ;
  - un `not_required` est définitif et IRRÉVOCABLE, même faux.
Le §4.4 dit « faux-positif acceptable », pas « faux-positif irréversible » : il l'est parce qu'un
humain le corrige. Cas réel : le cas 6 est classé `vrai_bug`/`not_required` alors que la vraie
cause est une spec périmée (le test ne remplit que 4 des 8 champs requis — l'application, elle,
refuse correctement un formulaire incomplet).
→ Ne pas « durcir » `_ORIGIN_BY_CAUSE` pour compenser : sans exutoire humain, on ne ferait que
déplacer le problème vers le faux NÉGATIF, lui inacceptable. Le remède est la file de
confirmation/infirmation (`0001` élargi), pas la règle.

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
    # ⚠️ DÉDUCTION, pas constat. Une assertion qui échoue dit « le test attendait X, a obtenu Y » —
    # trois causes possibles, dont deux ne sont PAS l'application : (a) l'app répond faux ;
    # (b) le test attend la mauvaise chose (spec périmée, scénario incomplet) ; (c) l'environnement
    # diffère. Les distinguer automatiquement est indécidable : c'est un jugement humain.
    # On choisit quand même VRAI_BUG — c'est l'asymétrie VOULUE du §4.4 : mieux vaut un
    # faux positif (crier au loup) qu'un faux négatif (masquer un vrai bug). Mais « acceptable »
    # suppose qu'un humain puisse INFIRMER — voir la limite ci-dessous.
    dt.ASSERTION_MISMATCH: VRAI_BUG,
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
