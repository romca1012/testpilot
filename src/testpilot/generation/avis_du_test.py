"""Les points de vigilance qui ne dépendent QUE du test écrit et de ce que la génération a vu — un seul calcul, appelé à
deux moments (étape 2 du plan unique, A61, porteur 2026-10-20) :

- pendant l'écriture (`react_loop`, contrôle de fin d'écriture) : l'IA les reçoit et les corrige avant de rendre la main ;
- sur la version enregistrée (`generation_service.lint_warnings_for_version`) : ce qui reste rend le test bloqué (A63).

Les points qui dépendent de l'HISTOIRE du cas (correction D30, cas changé D31, valeur vue à l'essai, régénération après un
défaut A65, réparation) ne sont pas ici : ils ne se corrigent pas en réécrivant le test, et certains ne doivent jamais être
montrés à l'IA (A65).

Aucune I/O : tout ce qu'il faut est passé en paramètre.
"""
from __future__ import annotations

from datetime import datetime


def avis_du_test(*, feature: str, steps: str, observations: list[dict] | None, target_sha256: str, base_url: str,
                 reference_time: datetime | None, variables_des_lignes, connecteur_web: bool, intention: str,
                 modele: dict | None, verified_fields: dict | None, joue_avec_un_autre_compte: bool = False) -> list[dict]:
    """`observations` à `None` : la version n'a jamais été instrumentée, la preuve d'écran n'est pas contrôlée.
    `verified_fields` à `None` : aucun registre (version d'avant le registre)."""
    from testpilot.generation import assertion_lint, enregistrement_lint, smoke_check, variables_de_test
    from testpilot.generation.evidence import contextual_warnings

    avis = assertion_lint.lint_steps(steps or "")
    # Étape 4, morceau 7 (A89) : un cas joué avec un autre compte — une vérification qui ne lit que par le principal.
    if joue_avec_un_autre_compte:
        avis += assertion_lint.lint_alors_lu_par_le_principal(steps or "")
    if feature:
        # F26, point 1 : filet structurel, sur le Gherkin produit — pas sur ce que le modèle a déclaré avoir fait.
        avis += enregistrement_lint.lint_enregistrements_non_crees(feature)
        # IT-3b : les lignes du cas font varier des variables qu'aucun « Alors » n'emploie.
        avis += variables_de_test.lint_alors_sans_variable_des_lignes(feature, variables_des_lignes)
    if observations is not None:
        avis += contextual_warnings(feature or "", observations, target_sha256=target_sha256, base_url=base_url,
                                    reference_time=reference_time)
    # Lot 07a : seul le connecteur `web` connecte AUTOMATIQUEMENT à l'ouverture. L'intention est celle DÉCLARÉE par le cas.
    if connecteur_web:
        avis += smoke_check.check_intention_connexion(intention, feature or "")
    if modele or verified_fields is not None:
        avis += smoke_check.smoke_check(feature or "", steps or "", modele=modele, verified_fields=verified_fields)
    return avis
