"""Script effectif consultable (Phase 2, audit DA 2026-08-13) — décision liée à 0003.

Le Python généré propre à un cas (`steps_content`) est souvent quasi vide : la plupart de ses
steps viennent de la bibliothèque partagée, chargée par Behave à l'exécution mais invisible dans
l'onglet Script. Ce module assemble, pour une version donnée, le texte COMPLET réellement
exécuté — sans lancer de run, sans toucher au fichier propre au cas.

Pure lecture : `resoudre_script_effectif` ne modifie rien, uniquement de la composition à partir
de ce que `steps_library` sait déjà résoudre (`match_referenced` + `load_step_source`).
"""

from __future__ import annotations

from testpilot.generation import steps_library
from testpilot.store.repositories import CaseRepo, ProjectRepo, VersionRepo

_ENTETE = (
    "# " + "=" * 76 + "\n"
    "# Steps partagés — bibliothèque (lecture seule : se modifient dans la bibliothèque,\n"
    "# jamais depuis ce cas)\n"
    "# " + "=" * 76
)


def resoudre_script_effectif(conn, *, case_id: int, version_id: int) -> dict:
    """Charge la version + résout, groupé par fichier d'origine, le code des steps partagés
    que son `.feature` référence réellement.

    Suppose `case_id`/`version_id` déjà validés par l'appelant (existence, appartenance) — cette
    fonction ne fait que de la composition, pas de la garde HTTP (0014, même séparation que les
    autres services de ce dossier).

    Repli : `.feature` vide (cas sans version technique encore générée) → `steps_effectif`
    identique à `steps_content`, aucun step partagé résolu (rien à y chercher).
    """
    version = VersionRepo(conn).get(version_id)
    feature_content = (version or {}).get("feature_content") or ""
    steps_content = (version or {}).get("steps_content") or ""

    if not feature_content:
        return {
            "feature_content": feature_content,
            "steps_content": steps_content,
            "shared_steps": [],
            "steps_effectif": steps_content,
        }

    case = CaseRepo(conn).get(case_id)
    project_id = (case or {}).get("project_id")
    connector_type = (ProjectRepo(conn).get(project_id) or {}).get("connector_type") \
        if project_id else None

    catalogue = steps_library.catalogue(connector_type=connector_type)
    referenced = steps_library.match_referenced(feature_content, catalogue)
    code_par_label = steps_library.load_step_source(referenced)

    shared_steps = [
        {"keyword": s.keyword, "label": s.label, "source": s.source, "note": s.note,
         "code": code_par_label.get(s.label, "")}
        for s in referenced
    ]

    par_source: dict[str, list[str]] = {}
    for s in referenced:
        code = code_par_label.get(s.label)
        if code:
            par_source.setdefault(s.source, []).append(code)

    blocs = [_ENTETE]
    for source in sorted(par_source):
        blocs.append(f"\n# --- {source} ---\n")
        blocs.append("\n".join(par_source[source]))

    steps_effectif = steps_content.rstrip()
    if par_source:
        steps_effectif = (steps_effectif + "\n\n" if steps_effectif else "") + "\n".join(blocs)

    return {
        "feature_content": feature_content,
        "steps_content": steps_content,
        "shared_steps": shared_steps,
        "steps_effectif": steps_effectif,
    }
