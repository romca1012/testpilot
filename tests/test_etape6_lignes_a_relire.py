"""Étape 6 du plan unique (IT-3d, A58 point 5) — quand le texte du cas change (« moins de 18 ans » → « moins de 21 ans »),
ses lignes sont SIGNALÉES à relire ; l'IA peut proposer les nouvelles (interrupteur `TESTPILOT_LIGNES_PROPOSEES`, éteint),
une personne les relit et les enregistre.

Gardé ici : le signal suit le texte du cas validé (préconditions, étapes, résultat attendu), pas son titre ; enregistrer les
lignes vaut relecture ; des lignes d'avant la migration 75 (sans empreinte) ne sont jamais signalées sans preuve ; la
proposition n'enregistre rien et ne part qu'interrupteur allumé, avec les seuls NOMS des variables (A60). Aucun appel au
modèle de langage : des doublures.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import donnees_de_test_service as service
from testpilot.generation import interrupteurs, metier_writer
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseDataRepo, CaseRepo, ModuleRepo, ProjectRepo, TestDataRepo, VersionRepo


@pytest.fixture
def base(tmp_path, monkeypatch):
    from testpilot.generation import domain_model
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "GENERATED_DIR", tmp_path / "generated")
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", tmp_path / "domain")   # fixé à l'import : jamais le vrai data/domain/
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db.sqlite")
    conn = get_initialized_db(config.DB_PATH)
    yield conn
    conn.close()


def _cas(conn):
    pid = ProjectRepo(conn).create(name="Accès", connector_type="web", base_url="http://app")
    cid = CaseRepo(conn).create(title="Accès selon l'âge", module_id=ModuleRepo(conn).create(project_id=pid, name="M"))
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="Moins de 18 ans : refusé.", spec_hash="",
                                   feature_content="", steps_content="", title="Accès selon l'âge",
                                   test_steps=json.dumps(["Saisir l'âge {{age}}"]),
                                   expected_result="Moins de 18 ans : {{resultat}}")
    CaseRepo(conn).set_current_version(cid, vid)
    depot = TestDataRepo(conn)
    ids = {n: depot.creer_variable(pid, nom=n, description=f"la donnée {n}") for n in ("age", "resultat")}
    CaseDataRepo(conn).remplacer(cid, pid, [{"nom": "Majeur", "valeurs": {ids["age"]: "18", ids["resultat"]: "Bienvenue"}}])
    return pid, cid, ids


def test_falsifiable_un_cas_dont_le_texte_change_signale_ses_lignes_et_les_enregistrer_vaut_relecture(base):
    pid, cid, ids = _cas(base)
    assert service.lignes_a_relire(base, cid) == ""

    CaseRepo(base).update_metier(cid, title="Accès selon l'âge", preconditions="", test_steps=json.dumps(["Saisir l'âge {{age}}"]),
                                 expected_result="Moins de 21 ans : {{resultat}}")
    assert service.lignes_a_relire(base, cid) == service.LIGNES_A_RELIRE

    CaseDataRepo(base).remplacer(cid, pid, [{"nom": "Majeur", "valeurs": {ids["age"]: "21", ids["resultat"]: "Bienvenue"}}])
    assert service.lignes_a_relire(base, cid) == ""


def test_le_titre_seul_ne_rend_pas_les_lignes_fausses(base):
    _pid, cid, _ids = _cas(base)
    CaseRepo(base).update_metier(cid, title="Accès des majeurs", preconditions="", test_steps=json.dumps(["Saisir l'âge {{age}}"]),
                                 expected_result="Moins de 18 ans : {{resultat}}")
    assert service.lignes_a_relire(base, cid) == ""


def test_des_lignes_d_avant_sans_empreinte_ne_sont_jamais_signalees(base):
    _pid, cid, _ids = _cas(base)
    base.execute("UPDATE test_case SET lignes_ecrites_pour='' WHERE id=?", (cid,))
    base.commit()
    CaseRepo(base).update_metier(cid, title="X", preconditions="", test_steps=json.dumps(["Autre"]), expected_result="Autre")
    assert service.lignes_a_relire(base, cid) == ""


def test_api_la_fiche_des_lignes_porte_le_signal(base):
    _pid, cid, _ids = _cas(base)
    CaseRepo(base).update_metier(cid, title="Accès selon l'âge", preconditions="", test_steps=json.dumps(["Saisir l'âge {{age}}"]),
                                 expected_result="Moins de 21 ans : {{resultat}}")
    assert TestClient(app_mod.app).get(f"/api/cases/{cid}/donnees-de-test").json()["lignes_a_relire"] == service.LIGNES_A_RELIRE


# ── Proposer les nouvelles lignes ───────────────────────────────────────────────────────────────────────────────────────

class _IA:
    def __init__(self):
        self.appels = []

    def call_json(self, **kw):
        self.appels.append(kw)
        return {"title": "Accès selon l'âge", "preconditions": "", "steps": ["Saisir l'âge"],
                "expected_result": "Moins de 21 ans : refusé", "depend_dun_autre_cas_du_groupe": False,
                "etat_a_creer_par_ce_cas": "",
                "lignes": [{"nom": "Limite", "valeurs": [{"variable": "age", "valeur": "20"},
                                                         {"variable": "resultat", "valeur": "Accès refusé"}]},
                           {"nom": "Majeur", "valeurs": [{"variable": "age", "valeur": "21"},
                                                         {"variable": "resultat", "valeur": "Bienvenue"}]}]}


def test_falsifiable_eteint_la_proposition_est_refusee_sans_appel(base, monkeypatch):
    monkeypatch.delenv(interrupteurs.ENV_LIGNES_PROPOSEES, raising=False)
    _pid, cid, _ids = _cas(base)
    ia = _IA()
    with pytest.raises(service.PropositionImpossible):
        service.proposer_les_lignes(base, cid, llm=ia)
    assert ia.appels == []
    assert TestClient(app_mod.app).post(f"/api/cases/{cid}/donnees-de-test/proposition").status_code == 409


def test_allume_l_ia_propose_pour_le_texte_d_aujourd_hui_rien_n_est_enregistre(base, monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_LIGNES_PROPOSEES, "1")
    _pid, cid, _ids = _cas(base)
    CaseRepo(base).update_metier(cid, title="Accès selon l'âge", preconditions="", test_steps=json.dumps(["Saisir l'âge {{age}}"]),
                                 expected_result="Moins de 21 ans : {{resultat}}")
    ia = _IA()
    lignes = service.proposer_les_lignes(base, cid, llm=ia)

    assert [l["nom"] for l in lignes] == ["Limite", "Majeur"]
    envoye = ia.appels[0]["cached_prefix"] + ia.appels[0]["user_content"]
    assert "Moins de 21 ans" in envoye, "le texte du cas d'AUJOURD'HUI"
    assert "{{age}}" in envoye and "18" not in ia.appels[0]["user_content"], "des noms, jamais les valeurs enregistrées"
    assert [l["nom"] for l in CaseDataRepo(base).lignes(cid)] == ["Majeur"], "rien n'est enregistré"
    assert ia.appels[0]["schema"] is metier_writer._METIER_AVEC_LIGNES_SCHEMA


def test_falsifiable_une_copie_garde_le_signal_de_ses_lignes(base):
    """Revue (C4) : copier un cas aux lignes signalées ne vaut pas relecture."""
    from testpilot.store.repositories import CaseGroupRepo

    _pid, cid, _ids = _cas(base)
    CaseRepo(base).update_metier(cid, title="Accès selon l'âge", preconditions="", test_steps=json.dumps(["Saisir l'âge {{age}}"]),
                                 expected_result="Moins de 21 ans : {{resultat}}")
    module = CaseRepo(base).get(cid)["module_id"]
    groupe = CaseGroupRepo(base).create(module_id=module, title="Copies")
    copie = CaseRepo(base).copier(cid, group_id=groupe)
    assert service.lignes_a_relire(base, copie) == service.LIGNES_A_RELIRE


def test_une_proposition_vide_est_dite_jamais_un_tableau_vide(base, monkeypatch):
    monkeypatch.setenv(interrupteurs.ENV_LIGNES_PROPOSEES, "1")
    _pid, cid, _ids = _cas(base)

    class _IAVide(_IA):
        def call_json(self, **kw):
            return {**super().call_json(**kw), "lignes": []}
    with pytest.raises(service.PropositionImpossible, match="aucune ligne"):
        service.proposer_les_lignes(base, cid, llm=_IAVide())


def test_le_plafond_de_cout_atteint_est_dit_jamais_une_erreur_500(base, monkeypatch):
    """Revue : `CostLimitExceeded` pendant la proposition → 409 avec la raison (aucun appel réel : la passe est remplacée)."""
    from testpilot.guardrails.cost_tracker import CostLimitExceeded

    _pid, cid, _ids = _cas(base)

    def _plafond(*_a, **_kw):
        raise CostLimitExceeded("0.50 USD")
    monkeypatch.setattr(service, "proposer_les_lignes", _plafond)
    reponse = TestClient(app_mod.app).post(f"/api/cases/{cid}/donnees-de-test/proposition")
    assert reponse.status_code == 409 and "plafond" in reponse.json()["detail"]
