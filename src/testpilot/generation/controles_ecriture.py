"""Les contrôles d'écriture rejoués sur un test MODIFIÉ À LA MAIN (étape 5 du plan unique).

Pourquoi. L'IA ne peut écrire un test qu'à travers `write_feature_file` / `write_steps_file`, qui refusent ce qui fausserait
le verdict (vérification toujours vraie, oracle interrogé à la main, signal réservé au harnais, réseau direct, attribut de
contexte inventé, masque de secret, séquence d'échappement…). Une édition à la main du script (`PATCH /cases/{id}/script`,
rôle Dev) ne passait par AUCUN d'eux : seule la relecture humaine la gardait, sans savoir quoi regarder.

Ici, les MÊMES fonctions, sans le contexte propre à une génération (aucun annuaire de l'application, aucune variable,
aucun gel) : seuls les contrôles qui ne dépendent que du texte du test. Écrit dans un dossier temporaire, jamais à côté
des tests réels. Rend les messages de refus (vide : rien à signaler).
"""

from __future__ import annotations

import tempfile
from pathlib import Path


def refus_hors_generation(feature: str, steps: str, *, connector_type: str | None = None,
                          profil_instance: str | None = None) -> list[str]:
    from testpilot import config
    from testpilot.generation import litteraux_observes, steps_library
    from testpilot.generation.tools import ToolContext
    from testpilot.generation.tools import write as write_tools

    catalogue = steps_library.catalogue(connector_type=connector_type, profil_instance=profil_instance)
    refus = []
    with tempfile.TemporaryDirectory(prefix="tp-controle-") as dossier:
        ctx = ToolContext(module_name="controle_manuel", generated_dir=Path(dossier),
                          reserved_steps=frozenset(s.label for s in catalogue), shared_steps=catalogue,
                          attributs_contexte=frozenset(litteraux_observes.attributs_du_harnais(config.BEHAVE_RUNTIME_DIR)))
        if (feature or "").strip():
            sortie = write_tools.write_feature_file(ctx, feature)
            if not sortie.ok:
                refus.append(sortie.observation)
        if (steps or "").strip():
            sortie = write_tools.write_steps_file(ctx, steps)
            if not sortie.ok:
                refus.append(sortie.observation)
    return refus
