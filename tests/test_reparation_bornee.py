"""Réparation bornée (porteur, 2026-10-22) : jamais un test affaibli, coupé ou à juger livré « prêt à lancer ».

Chaque test reproduit un contournement trouvé par la revue `verdict-reviewer` de la réparation bornée
(`generation_service._reparer_ou_retirer`) et prouve qu'il est fermé :
- la 2e proposition est comparée à la version d'où elle part, pas à une tentative déjà écartée ;
- une proposition coupée (budget, refus) n'est jamais gardée, même sans point de vigilance ;
- chaque appel ne reçoit que le RESTE du budget de réparation ;
- un point qu'une personne doit juger arrête la réparation (le cas reste à juger) ;
- un test non livré n'est jamais joué : ni par `trigger_run`, ni par le fichier resté sur disque ;
- une variable de préparation est refusée dans un « Alors », y compris par un plan, un bloc de texte ou un tableau ;
- une régénération qui échoue garde l'ancien test approuvé (même métier), et le dit.
"""

from __future__ import annotations

import pytest

from testpilot import config
from testpilot.api import schemas
from testpilot.api.routes import cases as route
from testpilot.api.services import generation_service, run_service
from testpilot.generation import correction_agent
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools.write import write_feature_file
from testpilot.generation.variables_de_test import ALORS_IDENTIQUE
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo, ensure_default_module
from testpilot.verdict import review_gate

FEATURE = '# language: fr\nFonctionnalité: F\n  Scénario: S\n    Quand je valide\n    Alors truc\n'
V0 = ('from behave import then\n\n\n@then("le titre")\ndef a(context):\n'
      '    assert context.page.title() == "Commande enregistree"\n\n\n'
      '@then("truc")\ndef s(context):\n    assert True\n')
AFFAIBLI = ('from behave import then\n\n\n@then("le titre")\ndef a(context):\n'
            '    assert "Commande" in context.page.title()\n\n\n'
            '@then("truc")\ndef s(context):\n    assert context.page.url != ""\n')
RENFORCE = V0.replace('    assert True\n', '    assert context.page.locator("h1").inner_text() == "Merci"\n')


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    c = get_initialized_db(tmp_path / "a.db")
    yield c
    c.close()


def _cas(conn, *, steps: str = V0) -> tuple[int, int]:
    cid = CaseRepo(conn).create(title="C", module_id=ensure_default_module(conn, "m"), feature_slug="c")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h", feature_content=FEATURE,
                                   steps_content=steps, title="C", expected_result="Commande enregistrée")
    CaseRepo(conn).set_current_version(cid, vid)
    return cid, vid


def _proposer(monkeypatch, sorties, *, fin: str = "done", cout: float = 0.01, appels: list | None = None):
    it = iter(sorties)

    def propose(**kw):
        if appels is not None:
            appels.append(kw)
        return correction_agent.CorrectionProposal(changed=True, feature_content=kw["feature_content"],
                                                   steps_content=next(it), summary="x", cost_usd=cout,
                                                   stopped_reason=fin)
    monkeypatch.setattr(correction_agent, "propose_correction", propose)


def _finaliser(conn, cid, vid):
    generation_service._finaliser_version_generee(conn, cid, vid, module_name="c", connector=None, dry_runner=object())


def _courante(conn, cid) -> dict:
    return VersionRepo(conn).get(CaseRepo(conn).get(cid)["current_version_id"])


def _approuvee(conn, vid) -> bool:
    return review_gate.evaluate_gate(ReviewRepo(conn), vid).allowed


def test_falsifiable_la_seconde_proposition_se_juge_contre_la_version_de_depart(conn, monkeypatch):
    """Revue : la 2e proposition, identique à la 1re (écartée) à un commentaire près, passait pour propre."""
    cid, vid = _cas(conn)
    _proposer(monkeypatch, [AFFAIBLI, "# même proposition, à un commentaire près\n" + AFFAIBLI])

    _finaliser(conn, cid, vid)

    assert not any(_approuvee(conn, v["id"]) for v in VersionRepo(conn).list_for_case(cid)
                   if "in context.page.title()" in (v.get("steps_content") or ""))
    assert not (_courante(conn, cid).get("feature_content") or "").strip()   # test non livré


@pytest.mark.parametrize("fin", ["cost_exceeded", "refusal", "max_tokens_truncated", "incomplete"])
def test_falsifiable_une_proposition_coupee_n_est_jamais_gardee(conn, monkeypatch, fin):
    """Une proposition coupée peut être à moitié écrite et n'a pas passé l'essai à blanc — même propre, jamais gardée."""
    cid, vid = _cas(conn)
    _proposer(monkeypatch, [RENFORCE, RENFORCE], fin=fin)

    _finaliser(conn, cid, vid)

    assert not any(_approuvee(conn, v["id"]) for v in VersionRepo(conn).list_for_case(cid))
    assert not (_courante(conn, cid).get("feature_content") or "").strip()


def test_la_meme_proposition_aboutie_est_approuvee(conn, monkeypatch):
    """Témoin du test précédent : sans coupure, le renforcement est bien livré (le refus ne vient pas d'ailleurs)."""
    cid, vid = _cas(conn)
    _proposer(monkeypatch, [RENFORCE])

    _finaliser(conn, cid, vid)

    assert _courante(conn, cid)["steps_content"] == RENFORCE and _approuvee(conn, _courante(conn, cid)["id"])


def test_chaque_appel_ne_recoit_que_le_reste_du_budget(conn, monkeypatch):
    cid, vid = _cas(conn)
    appels: list = []
    _proposer(monkeypatch, [AFFAIBLI, AFFAIBLI], cout=0.12, appels=appels)

    _finaliser(conn, cid, vid)

    plafonds = [kw["cost_tracker"].limit_usd for kw in appels]
    assert plafonds == pytest.approx([generation_service.BUDGET_REPARATION_USD,
                                      generation_service.BUDGET_REPARATION_USD - 0.12])


def test_falsifiable_un_point_a_juger_arrete_la_reparation(conn, monkeypatch):
    """A65 : un « Alors » identique au cas voisin se juge par une personne — la réparation s'arrête, rien n'est approuvé,
    et retoucher ensuite le titre ne rend pas le test lançable."""
    cid, vid = _cas(conn)
    appels: list = []
    _proposer(monkeypatch, [RENFORCE, RENFORCE], appels=appels)
    vrai = generation_service.lint_warnings_for_version

    def avis(conn_, case, rows, version_id):
        if version_id == vid:
            return vrai(conn_, case, rows, version_id)
        return [{"step": "", "line": 0, "kind": ALORS_IDENTIQUE, "message": "même Alors que le cas voisin"}]
    monkeypatch.setattr(generation_service, "lint_warnings_for_version", avis)

    _finaliser(conn, cid, vid)

    courante = _courante(conn, cid)
    assert len(appels) == 1 and courante["steps_content"] == RENFORCE and not _approuvee(conn, courante["id"])
    v_titre = route.update_case_metier(cid, schemas.CaseMetierIn(title="C (coquille)"), conn=conn).version_id
    assert not _approuvee(conn, v_titre)
    with pytest.raises(run_service.RunError):
        run_service.trigger_run(conn, cid)


@pytest.mark.parametrize("module", ["c", "autre_nom"])
def test_falsifiable_un_test_non_livre_n_est_jamais_joue(conn, monkeypatch, module):
    """Le runner lit le test SUR DISQUE : le fichier jugé non sûr est supprimé, et la version sans test refuse de jouer
    même quand le fichier reste (nom de module différent) et qu'une retouche du titre l'a approuvée d'office."""
    cid, vid = _cas(conn)
    config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    (config.GENERATED_DIR / "c.feature").write_text(FEATURE, encoding="utf-8")
    (config.GENERATED_DIR / "c_steps.py").write_text(V0, encoding="utf-8")
    monkeypatch.setattr(correction_agent, "propose_correction", lambda **kw: correction_agent.CorrectionProposal(
        changed=False, stopped_reason="incomplete", cost_usd=0.0))
    generation_service._finaliser_version_generee(conn, cid, vid, module_name=module, connector=None,
                                                  dry_runner=object())

    if module == "c":
        assert not (config.GENERATED_DIR / "c_steps.py").exists()
    v = route.update_case_metier(cid, schemas.CaseMetierIn(title="C (coquille)"), conn=conn).version_id
    with pytest.raises(run_service.RunError) as err:
        run_service.trigger_run(conn, cid)
    assert err.value.code == "no_test"
    assert run_service._assurer_script_sur_disque(conn, v, "c", execution_id=1, case_id=cid).blocage


BASE = '# language: fr\nFonctionnalité: Commande\n'
ALORS_DETOURNES = {
    "plan": BASE + ('  Plan du scénario: Passer une commande\n'
                    '    Quand je renseigne le champ "Client" avec la valeur "{{client}}"\n'
                    '    Alors la page affiche le texte "<v>"\n'
                    '    Exemples:\n      | v |\n      | {{ville}} |\n'),
    "bloc de texte": BASE + ('  Scénario: Passer une commande\n'
                             '    Quand je renseigne le champ "Client" avec la valeur "{{client}}"\n'
                             '    Alors la page affiche le texte :\n      """\n      {{ville}}\n      """\n'),
    "tableau": BASE + ('  Scénario: Passer une commande\n'
                       '    Quand je renseigne le champ "Client" avec la valeur "{{client}}"\n'
                       '    Alors la page affiche les lignes :\n      | {{ville}} |\n'),
}


def _ctx_preparation(tmp_path) -> ToolContext:
    return ToolContext(module_name="commande", generated_dir=tmp_path, variables_de_test=frozenset({"client", "ville"}),
                       variables_du_cas=frozenset({"client"}), controle_du_cas=True,
                       variables_de_preparation=frozenset({"ville"}))


@pytest.mark.parametrize("nom", list(ALORS_DETOURNES))
def test_falsifiable_une_variable_de_preparation_detournee_dans_un_alors_est_refusee(tmp_path, nom):
    sortie = write_feature_file(_ctx_preparation(tmp_path), ALORS_DETOURNES[nom])

    assert not sortie.ok and "{{ville}}" in sortie.observation


def test_une_variable_de_preparation_dans_un_soit_reste_acceptee(tmp_path):
    feature = BASE + ('  Scénario: Passer une commande\n'
                      '    Soit je renseigne le champ "Ville" avec la valeur "{{ville}}"\n'
                      '    Quand je renseigne le champ "Client" avec la valeur "{{client}}"\n'
                      '    Alors la page affiche le texte "{{client}}"\n')

    sortie = write_feature_file(_ctx_preparation(tmp_path), feature)

    assert "{{ville}}" not in sortie.observation


# ── Porteur, 2026-10-22 : « garder l'ancien test » ───────────────────────────────────────────────────────


def _regeneration_qui_echoue(conn, monkeypatch, cid, *, expected_result: str = "Commande enregistrée",
                             compte_id: int | None = None) -> int:
    v2 = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h2", feature_content=FEATURE,
                                  steps_content=V0, title="C", expected_result=expected_result, compte_id=compte_id)
    CaseRepo(conn).set_current_version(cid, v2)
    monkeypatch.setattr(correction_agent, "propose_correction", lambda **kw: correction_agent.CorrectionProposal(
        changed=False, stopped_reason="incomplete", cost_usd=0.0))
    _finaliser(conn, cid, v2)
    return v2


def test_falsifiable_une_regeneration_qui_echoue_garde_l_ancien_test_approuve(conn, monkeypatch):
    cid, v1 = _cas(conn, steps=RENFORCE)
    ReviewRepo(conn).create(test_case_id=cid, version_id=v1, decision="approved", reviewer="humain", repair_budget=2)

    v2 = _regeneration_qui_echoue(conn, monkeypatch, cid)

    assert _courante(conn, cid)["id"] == v1 and _approuvee(conn, v1)
    message = max(VersionRepo(conn).list_for_case(cid), key=lambda v: v["id"])
    assert message["id"] > v2 and message["change_summary"].startswith(generation_service.GENERATION_NON_ABOUTIE)


def test_falsifiable_un_metier_change_ne_garde_pas_l_ancien_test(conn, monkeypatch):
    """L'ancien test vérifie l'ancien résultat attendu : le garder rendrait « Passé » ce que le cas ne dit plus."""
    cid, v1 = _cas(conn, steps=RENFORCE)
    ReviewRepo(conn).create(test_case_id=cid, version_id=v1, decision="approved", reviewer="humain", repair_budget=2)

    _regeneration_qui_echoue(conn, monkeypatch, cid, expected_result="Commande refusée")

    courante = _courante(conn, cid)
    assert courante["id"] != v1 and not (courante.get("feature_content") or "").strip()
    assert courante["change_summary"].startswith(generation_service.TEST_NON_LIVRE)


def test_falsifiable_un_compte_change_ne_garde_pas_l_ancien_test(conn, monkeypatch):
    """Revue, 3e passe (A70, A86) : l'ancien test, joué en compte principal, remis en place sur un cas passé en compte
    restreint, sortait « conforme » pour un utilisateur qui ne voit peut-être rien."""
    from testpilot.store.repositories import ProjectAccountRepo
    cid, v1 = _cas(conn, steps=RENFORCE)
    ReviewRepo(conn).create(test_case_id=cid, version_id=v1, decision="approved", reviewer="humain", repair_budget=2)
    compte = ProjectAccountRepo(conn).create(CaseRepo(conn).get(cid)["project_id"], label="Restreint", username="r")

    _regeneration_qui_echoue(conn, monkeypatch, cid, compte_id=compte)

    courante = _courante(conn, cid)
    assert courante["id"] != v1 and not (courante.get("feature_content") or "").strip()
    assert courante["compte_id"] == compte


def test_un_ancien_test_non_approuve_n_est_pas_garde(conn, monkeypatch):
    cid, _ = _cas(conn, steps=RENFORCE)

    _regeneration_qui_echoue(conn, monkeypatch, cid)

    assert _courante(conn, cid)["change_summary"].startswith(generation_service.TEST_NON_LIVRE)
