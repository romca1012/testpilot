"""§5 — le rapport présente les DEUX axes séparément, en JSON et en HTML, hors-ligne.

Vérrouille : les deux statuts ne sont jamais fusionnés, la cause racine et la provenance
du coût sont rendues, le drapeau de confirmation humaine remonte, et ``write_report`` écrit
bien deux fichiers.
"""

import json

from testpilot.reporting import report as rp
from testpilot.verdict import defect_origin as do
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict.status import (
    CaseVerdict,
    ScenarioVerdict,
    EXEC_SUCCESS,
    EXEC_TECHNICAL_ERROR,
    FUNC_CONFORME,
    FUNC_NON_CONFORME,
)


def _verdict_mixte() -> CaseVerdict:
    scenarios = [
        ScenarioVerdict("cas nominal", EXEC_SUCCESS, FUNC_CONFORME),
        ScenarioVerdict("total faux", EXEC_SUCCESS, FUNC_NON_CONFORME,
                        failure_type="assertion", cause_category=dt.ASSERTION_MISMATCH,
                        error="AssertionError: attendu 0, obtenu 5"),
    ]
    # Un non_conforme surface au niveau du cas (jamais masqué).
    return CaseVerdict(EXEC_SUCCESS, FUNC_NON_CONFORME, scenarios=scenarios,
                       scenarios_passed=1, scenarios_failed=1)


def test_build_report_ne_fusionne_pas_les_axes():
    report = rp.build_report(_verdict_mixte(), module_name="demande_materiel", cost_usd=0.12)
    assert report.execution_status == EXEC_SUCCESS
    assert report.functional_status == FUNC_NON_CONFORME
    assert report.execution_label == "Exécuté"
    assert report.functional_label == "Non conforme"
    assert report.scenarios_passed == 1 and report.scenarios_failed == 1


def test_report_json_porte_les_deux_axes_et_les_causes():
    report = rp.build_report(_verdict_mixte(), module_name="demande_materiel",
                             cost_usd=0.12, cost_source="estimated")
    data = json.loads(rp.render_json(report))
    assert data["execution_status"] == "success"
    assert data["functional_status"] == "non_conforme"
    assert data["cost_source"] == "estimated"
    # La cause racine du scénario en échec est bien reportée.
    failing = [s for s in data["scenarios"] if s["functional_status"] == "non_conforme"][0]
    assert failing["cause_category"] == dt.ASSERTION_MISMATCH
    assert failing["cause_label"] == dt.LABELS[dt.ASSERTION_MISMATCH]


def test_report_html_affiche_les_deux_libelles_distincts():
    report = rp.build_report(_verdict_mixte(), module_name="demande_materiel")
    html = rp.render_html(report)
    assert "Axe exécution" in html
    assert "Axe fonctionnel" in html
    assert "Exécuté" in html
    assert "Non conforme" in html
    # Autonome : aucun asset externe.
    assert "http://" not in html and "https://" not in html and "cdn" not in html.lower()


def test_report_flag_confirmation_humaine_depuis_defect_origin():
    verdict = CaseVerdict(EXEC_TECHNICAL_ERROR, "indetermine", scenarios=[], scenarios_failed=0)
    # Un défaut indéterminé exige une confirmation humaine (asymétrie §5).
    repair = do.DefectVerdict(cause_category=dt.UNKNOWN, defect_origin=do.INDETERMINE,
                              confirmation_status=do.PENDING_HUMAN)
    report = rp.build_report(verdict, module_name="m", repairs=[repair])
    assert report.needs_human_confirmation is True
    assert report.to_dict()["needs_human_confirmation"] is True
    assert "confirmation humaine requise" in rp.render_html(report).lower()


def test_vrai_bug_ne_declenche_pas_de_confirmation():
    verdict = _verdict_mixte()
    repair = do.DefectVerdict(cause_category=dt.ASSERTION_MISMATCH, defect_origin=do.VRAI_BUG,
                              confirmation_status=do.NOT_REQUIRED)
    report = rp.build_report(verdict, module_name="m", repairs=[repair])
    assert report.needs_human_confirmation is False


def test_write_report_ecrit_json_et_html(tmp_path):
    report = rp.build_report(_verdict_mixte(), module_name="demande_materiel")
    json_path, html_path = rp.write_report(report, tmp_path)
    assert json_path.exists() and html_path.exists()
    assert json_path.suffix == ".json" and html_path.suffix == ".html"
    # Le JSON écrit est relisible et cohérent.
    assert json.loads(json_path.read_text(encoding="utf-8"))["module_name"] == "demande_materiel"
