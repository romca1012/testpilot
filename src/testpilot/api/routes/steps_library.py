"""La bibliothèque de steps PARTAGÉE — ce que l'agent de génération réutilise (décision 0003).

Jusqu'ici, ce catalogue n'existait QUE dans le prompt système de l'agent
(`steps_library.as_prompt_section`) — aucun humain ne pouvait le consulter sans lire le code
Python (2026-08-11). Cette route l'expose telle quelle, en lecture seule.

Une seule bibliothèque pour toute l'instance (`behave_runtime/steps_library/`, commune) — pas par
projet : un seul connecteur réel existe aujourd'hui (Odoo), donc aucune route à préfixer par
`project_id`.
"""

from __future__ import annotations

from fastapi import APIRouter

from testpilot.api import schemas
from testpilot.generation import steps_library

router = APIRouter(prefix="/api/steps-library", tags=["steps_library"])


@router.get("", response_model=list[schemas.SharedStepOut])
def list_shared_steps():
    """Tous les steps partagés — triés par mot-clé Gherkin puis libellé, comme dans le prompt.

    Dédupliqué sur (mot-clé, libellé) : une fonction à double décorateur (`@when` ET `@then` sur
    le même libellé) apparaîtrait sinon deux fois — même règle que `as_prompt_section`.
    """
    vus: dict[tuple[str, str], schemas.SharedStepOut] = {}
    for s in steps_library.catalogue():
        cle = (s.keyword, s.label)
        if cle not in vus:
            vus[cle] = schemas.SharedStepOut(keyword=s.keyword, label=s.label,
                                             source=s.source, note=s.note)
    return sorted(vus.values(), key=lambda s: (s.keyword, s.label))
