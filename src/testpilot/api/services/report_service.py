"""Reconstruction du rapport à deux axes depuis la base (sans relire de fichier).

Le rapport est rebâti à la demande depuis l'exécution persistée (execution + scenario_result
+ repair_attempt), via ``reporting.build_report`` — la même logique que le CLI, mais alimentée
par le référentiel plutôt que par un ``ExecutionOutcome`` en mémoire.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from testpilot.api.schemas import _field_fallbacks
from testpilot.reporting import report as report_mod
from testpilot.store.repositories import (
    CaseRepo,
    ExecutionRepo,
    RepairRepo,
    VersionRepo,
)
from testpilot.verdict.defect_origin import DefectVerdict
from testpilot.verdict.status import (
    LIBELLES_STATUT,
    CaseVerdict,
    ScenarioVerdict,
    statut_de_test,
    statuts_par_iteration,
)


def _rangs(texte) -> tuple[int, ...]:
    """« 1,3 » (`scenario_result.iterations`, migration 71) → (1, 3). Illisible ou vide : () = toutes."""
    return tuple(int(p) for p in str(texte or "").split(",") if p.strip().isdigit() and int(p) >= 1)


def iterations_jouees(execution: dict, scenario_rows: list[dict]) -> list[dict]:
    """A52 : [{numero, jeu, statut}] — une entrée par itération jouée, son statut calculé par la règle du cas
    (`verdict.status.statuts_par_iteration`). Vide quand l'exécution n'a pas joué plusieurs lignes."""
    iterations = _donnees_jouees(execution.get("parametres_joues")).get("iterations") or []
    if not iterations:
        return []
    verdicts = _verdict_from_db(execution, scenario_rows).scenarios
    statut_du_cas = statut_de_test(execution.get("execution_status"), execution.get("functional_status"))
    statuts = statuts_par_iteration(verdicts, len(iterations), statut_du_cas)
    return [{"numero": rang, "jeu": it["jeu"], "statut": statut}
            for rang, (it, statut) in enumerate(zip(iterations, statuts), start=1)]


def _verdict_from_db(execution: dict, scenario_rows: list[dict]) -> CaseVerdict:
    scenarios = [
        ScenarioVerdict(
            name=s["scenario_name"],
            execution_status=s["execution_status"],
            functional_status=s["functional_status"],
            failure_type=s.get("failure_type", ""),
            cause_category=s.get("cause_category", ""),
            error=s.get("error_summary", ""),
            iterations=_rangs(s.get("iterations")),
        )
        for s in scenario_rows
    ]
    return CaseVerdict(
        execution_status=execution["execution_status"],
        functional_status=execution["functional_status"],
        scenarios=scenarios,
        scenarios_passed=execution.get("scenarios_passed", 0),
        scenarios_failed=execution.get("scenarios_failed", 0),
    )


@dataclass
class _TentativeRapportee(DefectVerdict):
    """`DefectVerdict` + ce que l'agent a tenté (décision 0014).

    Sous-classe locale plutôt qu'un champ ajouté à `DefectVerdict` : celui-ci est un verdict
    d'ORIGINE (module pur du pilier verdict), pas une tentative de réparation. Les mélanger
    ferait remonter une notion de réparation dans un module qui n'en connaît aucune.
    """

    what_was_tried: str = ""


def _repairs_from_db(repair_rows: list[dict]) -> list[DefectVerdict]:
    return [
        _TentativeRapportee(
            cause_category=r.get("cause_category", ""),
            defect_origin=r.get("defect_origin", "indetermine"),
            confirmation_status=r.get("confirmation_status", "not_required"),
            what_was_tried=r.get("what_was_tried", "") or "",
        )
        for r in repair_rows
    ]


def build_report_for_execution(conn: sqlite3.Connection, execution_id: int):
    """Rebâtit le ``TestReport`` d'une exécution. None si l'exécution n'existe pas."""
    execs = ExecutionRepo(conn)
    execution = execs.get(execution_id)
    if execution is None:
        return None

    case = CaseRepo(conn).get(execution["test_case_id"])
    version = VersionRepo(conn).get(execution["version_id"])
    lignes = execs.list_scenario_results(execution_id)
    verdict = _verdict_from_db(execution, lignes)
    donnees = _donnees_jouees(execution.get("parametres_joues"))
    if donnees.get("iterations"):   # A52 : chaque itération avec son résultat
        for it, jouee in zip(donnees["iterations"], iterations_jouees(execution, lignes)):
            it["statut"] = jouee["statut"]
            it["statut_libelle"] = LIBELLES_STATUT.get(jouee["statut"], LIBELLES_STATUT["untested"])
    repairs = _repairs_from_db(RepairRepo(conn).list_for_execution(execution_id))

    return report_mod.build_report(
        verdict,
        # Affichage : nom métier du module (repli sur le slug technique si non rattaché).
        module_name=(case.get("module_name") or case.get("feature_slug") or "") if case else "",
        title=case["title"] if case else "",
        version_number=version["version_number"] if version else 1,
        cost_usd=execution.get("cost_usd", 0.0),
        cost_source="estimated",
        iterations=execution.get("iterations", 0),
        duration_seconds=execution.get("duration_seconds", 0.0),
        repairs=repairs,
        generated_at=execution.get("started_at"),
        # Contre quoi ce verdict a été rendu (migration 20). Lu depuis l'exécution — jamais depuis
        # la configuration courante : le projet a pu changer d'adresse depuis, le rapport doit
        # dire ce qui a été testé CE JOUR-LÀ.
        target_url=execution.get("target_url", "") or "",
        target_database=execution.get("target_database", "") or "",
        target_username=execution.get("target_username", "") or "",
        residus=_field_fallbacks(execution.get("residus")),
        donnees_de_test=donnees,
    )


def _donnees_jouees(texte: str | None) -> dict:
    """Ce qui a été posé dans le test (lot PT-02c). Illisible ou absent : rien — jamais une valeur reconstituée."""
    try:
        donnees = json.loads(texte or "{}")
    except ValueError:
        return {}
    if not isinstance(donnees, dict):
        return {}
    # Forme attendue seulement : `{nom: {valeur, origine}}` — une ligne mal formée est écartée, jamais devinée (le rapport
    # écran comme l'imprimable lisent ces champs).
    valeurs = donnees.get("valeurs") if isinstance(donnees.get("valeurs"), dict) else {}
    propres = {str(nom): {"valeur": str(v["valeur"]), "origine": str(v.get("origine") or "")}
               for nom, v in valeurs.items() if isinstance(v, dict) and "valeur" in v}
    jeu = donnees.get("jeu")
    # A52 : plusieurs lignes jouées, une itération chacune — même forme que `valeurs`, par itération.
    iterations = []
    for it in donnees.get("iterations") if isinstance(donnees.get("iterations"), list) else []:
        if isinstance(it, dict) and isinstance(it.get("valeurs"), dict):
            iterations.append({"jeu": str(it.get("jeu") or ""),
                               "valeurs": {str(n): {"valeur": str(v["valeur"]), "origine": str(v.get("origine") or "")}
                                           for n, v in it["valeurs"].items() if isinstance(v, dict) and "valeur" in v}})
    if not propres and not iterations and not isinstance(jeu, str):
        return {}
    return {"jeu": jeu if isinstance(jeu, str) else "", "valeurs": propres,
            **({"iterations": iterations} if iterations else {})}
