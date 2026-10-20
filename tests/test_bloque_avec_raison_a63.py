"""Étape 2 du plan unique (A63, A67, A68 — porteur, 2026-10-20) : un test que l'IA n'a pas rendu propre est LIVRÉ BLOQUÉ,
avec sa raison ; « bloqué » n'est pas enregistré, il se recalcule.

Ce que ces tests gardent :
1. « bloqué » vaut toujours `not allowed` — les raisons disent pourquoi, elles n'autorisent jamais un lancement ;
2. un test bloqué a toujours au moins une raison, en français (aucune valeur brute) ;
3. seule une approbation débloque ; une version non approuvée n'est jamais lancée, même sans point de vigilance ;
4. une version approuvée ne montre pas ses anciens points de vigilance, mais un écart cas/test (A42) la bloque encore.
"""

from __future__ import annotations

import itertools
import json

import pytest

from testpilot import config
from testpilot.api.services import run_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo, ensure_default_module
from testpilot.verdict import review_gate
from testpilot.verdict.review_gate import GateDecision, raisons_du_blocage


@pytest.mark.parametrize("approuvee, rejetee, ecarts, avis", itertools.product(
    (True, False), (True, False), ([], ["age"]), ([], [{"kind": "champ_inconnu"}], [{"kind": "sorte_inconnue"}])))
def test_falsifiable_bloque_vaut_toujours_non_autorise(approuvee, rejetee, ecarts, avis):
    if approuvee and rejetee:
        pytest.skip("la dernière décision est l'une ou l'autre")
    autorise = approuvee and not ecarts
    decision = GateDecision(allowed=autorise, needs_review=not autorise, reason="r")
    raisons = raisons_du_blocage(decision, approuvee=approuvee, rejetee=rejetee, ecarts=ecarts, avis=avis)
    assert bool(raisons) == (not autorise), "bloqué ⇔ non autorisé, et jamais bloqué sans raison"
    assert all(r and not r.isidentifier() for r in raisons), "des phrases, jamais une valeur brute"
    if approuvee:
        assert review_gate.RAISONS_DES_AVIS["champ_inconnu"] not in raisons, "approuvée : ses avis ont été jugés"


def test_chaque_sorte_d_avis_a_sa_phrase():
    from testpilot.api.services.generation_service import ATTENTE_METIER_CHANGEE, VALEUR_VUE_A_L_ESSAI, \
        VERIFICATION_CHANGEE_APRES_DEFAUT
    from testpilot.generation.enregistrement_lint import KIND_ENREGISTREMENT_NON_CREE
    from testpilot.generation.variables_de_test import ALORS_IDENTIQUE

    connues = {ATTENTE_METIER_CHANGEE, VALEUR_VUE_A_L_ESSAI, VERIFICATION_CHANGEE_APRES_DEFAUT, KIND_ENREGISTREMENT_NON_CREE,
               ALORS_IDENTIQUE, "champ_ui_non_verifie", "champs_requis_manquants", "soumission_absente", "menu_non_observe",
               "champ_inconnu", "valeur_option_inexistante", "message_non_observe", "produit_non_observe",
               "connexion_non_testee", "then_without_assertion", "assertion_dans_contexte", "always_true_constant",
               "tautology_negation_in_else", "verification_affaiblie_par_correction", "step_modifie", "step_supprime",
               "assertion_code_modifiee", "scenario_supprime", "assertion_modifiee", "exemple_modifie"}
    assert connues <= set(review_gate.RAISONS_DES_AVIS), connues - set(review_gate.RAISONS_DES_AVIS)


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "bloque.db")
    c = get_initialized_db()
    yield c
    c.close()


def _cas(conn):
    cid = CaseRepo(conn).create(title="Accès", module_id=ensure_default_module(conn, "acces"), feature_slug="acces")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", title="Accès",
                                   feature_content="# language: fr\nFonctionnalité: F\n  Scénario: S\n    Alors x\n",
                                   steps_content="", test_steps=json.dumps(["Ouvrir"]), expected_result="Refusé")
    CaseRepo(conn).set_current_version(cid, vid)
    return CaseRepo(conn).get(cid), vid


def test_falsifiable_une_version_non_approuvee_n_est_jamais_lancee_meme_sans_avis(conn):
    cas, vid = _cas(conn)
    decision, raisons, _ = run_service.blocage_du_cas(conn, cas, vid, avis=[])
    assert not decision.allowed and raisons == [review_gate.RAISON_NON_APPROUVE]
    with pytest.raises(run_service.RunError) as refus:
        run_service.trigger_run(conn, cas["id"])
    assert refus.value.code == "needs_review"


def test_la_raison_vient_des_points_de_vigilance_et_seule_une_approbation_debloque(conn):
    cas, vid = _cas(conn)
    avis = [{"kind": "verification_changee_apres_defaut"}, {"kind": "champ_inconnu"}, {"kind": "champ_inconnu"}]
    _, raisons, _ = run_service.blocage_du_cas(conn, cas, vid, avis=avis)
    assert raisons == [review_gate.RAISONS_DES_AVIS["verification_changee_apres_defaut"],
                       review_gate.RAISONS_DES_AVIS["champ_inconnu"]], "dédoublonnées, dans l'ordre"
    ReviewRepo(conn).create(test_case_id=cas["id"], version_id=vid, decision="approved", reviewer="porteur")
    decision, raisons, _ = run_service.blocage_du_cas(conn, cas, vid, avis=avis)
    assert decision.allowed and raisons == []


def test_un_rejet_se_dit(conn):
    cas, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cas["id"], version_id=vid, decision="rejected", reviewer="porteur")
    _, raisons, _ = run_service.blocage_du_cas(conn, cas, vid, avis=[])
    assert raisons == [review_gate.RAISON_REJETE]


def test_falsifiable_un_ecart_cas_test_bloque_une_version_approuvee(conn, monkeypatch):
    cas, vid = _cas(conn)
    ReviewRepo(conn).create(test_case_id=cas["id"], version_id=vid, decision="approved", reviewer="porteur")
    monkeypatch.setattr(run_service, "ecarts_cas_test", lambda *a, **k: ["age"])
    decision, raisons, _ = run_service.blocage_du_cas(conn, cas, vid, avis=[{"kind": "champ_inconnu"}])
    assert not decision.allowed
    assert len(raisons) == 1 and "age" in raisons[0], "l'écart seulement : les avis ont été jugés à l'approbation"
