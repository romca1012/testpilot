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


# ── Lot 02 (D1) : `blocked` a un libellé français, jamais la valeur brute ───────────────────

def test_le_rapport_libelle_blocked_en_francais_et_le_distingue_d_une_erreur_technique():
    from testpilot.verdict.status import EXEC_BLOCKED, FUNC_INDETERMINE

    verdict = CaseVerdict(EXEC_BLOCKED, FUNC_INDETERMINE, scenarios=[
        ScenarioVerdict("cas", EXEC_BLOCKED, FUNC_INDETERMINE,
                        cause_category=dt.PRECONDITION_NON_REMPLIE, error="module absent")])

    report = rp.build_report(verdict, module_name="m")
    html = rp.render_html(report)

    assert report.execution_label == "Bloqué (prérequis non rempli)"
    assert "Bloqué (prérequis non rempli)" in html
    assert "Prérequis non rempli (environnement)" in html, "libellé de la cause, pas la valeur brute"
    assert ">blocked<" not in html and "precondition_non_remplie" not in html
    assert 'class="pill warn"' in html, "ton d'avertissement, pas le rouge d'une panne"


# ── Lot 06 (F6) : les résidus de teardown remontent jusqu'au rapport lu par l'humain ────────────

def test_build_report_porte_les_residus_de_bout_en_bout():
    """Sans `residus=` explicite, ce champ resterait invisible dans le rapport que l'humain lit
    (le point relevé par la revue du lot 06 : `field_fallbacks` avait ce même trou avant lui)."""
    report = rp.build_report(_verdict_mixte(), module_name="m",
                             residus=["res.partner#4821 (max_id dépassé, non enregistré)"])
    assert report.residus == ["res.partner#4821 (max_id dépassé, non enregistré)"]
    assert json.loads(rp.render_json(report))["residus"] == [
        "res.partner#4821 (max_id dépassé, non enregistré)"]
    html = rp.render_html(report)
    assert "Résidus possibles" in html
    assert "res.partner#4821 (max_id dépassé, non enregistré)" in html


def test_falsifiable_sans_residu_le_bloc_html_n_apparait_pas():
    """Preuve NÉGATIVE : un rapport sans résidu n'affiche PAS le bloc — sinon un bloc vide
    laisserait croire qu'un teardown a été vérifié et n'a rien trouvé, alors qu'il n'a simplement
    rien à signaler (distinction déjà appliquée ailleurs au champ cible, cf. tête de fichier)."""
    report = rp.build_report(_verdict_mixte(), module_name="m")
    assert report.residus == []
    assert "Résidus possibles" not in rp.render_html(report)


def test_residus_remontent_de_la_base_jusqu_au_rapport(tmp_path, monkeypatch):
    """Bout en bout DB → `report_service.build_report_for_execution` → rapport : sans ce
    câblage, `ExecutionRepo.finalize(residus=...)` écrirait la donnée en base sans qu'aucun
    écran ne la lise — le trou constaté sur `field_fallbacks`, jamais comblé, que ce lot ne
    reproduit pas pour `residus`."""
    from testpilot import config
    from testpilot.api.services import report_service
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import (
        CaseRepo, ExecutionRepo, ModuleRepo, ProjectRepo, VersionRepo,
    )

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    conn = get_initialized_db(tmp_path / "residus.db")
    try:
        pid = ProjectRepo(conn).create(name="P", connector_type="odoo",
                                       base_url="http://x:8069", database="db",
                                       username="qa", password="secret")
        mid = ModuleRepo(conn).create(project_id=pid, name="M")
        cid = CaseRepo(conn).create(title="Cas", module_id=mid, feature_slug="cas")
        vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="",
                                       feature_content="Scenario: x", steps_content="")
        CaseRepo(conn).set_current_version(cid, vid)
        eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
        ExecutionRepo(conn).finalize(
            eid, execution_status="success", functional_status="conforme",
            scenarios_total=1, scenarios_passed=1, scenarios_failed=0,
            cost_usd=0.0, iterations=1, duration_seconds=0.1,
            residus=json.dumps(["res.partner#4821 (max_id dépassé, non enregistré)"]))

        rapport = report_service.build_report_for_execution(conn, eid)
        assert rapport.residus == ["res.partner#4821 (max_id dépassé, non enregistré)"]
        assert "Résidus possibles" in report_service.report_mod.render_html(rapport)
    finally:
        conn.close()
