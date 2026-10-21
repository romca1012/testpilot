"""Étape 4, morceau 7, partie B (A90-A93, porteur 2026-10-21) : le compte avec lequel CHAQUE LIGNE du cas est jouée.

Ce que ces tests gardent :
1. le dépôt et l'API : seul un compte de CE projet (ou le principal) ; l'écran dit avec quel compte chaque ligne SERA jouée ;
2. deux lignes qui ne diffèrent que par leur compte sont deux itérations — sinon la ligne « Lecteur » ne serait jamais jouée
   et l'écran l'annoncerait jouée ; chaque itération porte son compte dans une colonne réservée des Exemples ;
3. une case vide reprend « Joué en tant que » du cas (A91) ; un compte supprimé bloque le test, ligne nommée (A92) ;
4. le harnais connecte le compte de l'itération ; un « Alors » joué avec un autre compte est bloqué ;
5. vrai Behave + vrai Chromium sur l'application du banc : chaque ligne est réellement jouée avec son compte.
"""

from __future__ import annotations

import json
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from behave.parser import parse_feature
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api import app as app_mod
from testpilot.api.services import donnees_de_test_service as service
from testpilot.parametres import iterations as iterations_mod
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseDataRepo, CaseRepo, DonneeDeTestInvalide, ExecutionRepo, ModuleRepo, ProjectAccountRepo, ProjectRepo, TestDataRepo,
    VersionRepo,
)

_STEPS_LIB = Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"

QUI = """# language: fr
Fonctionnalité: Qui est connecté
  Scénario: la page dit qui est connecté
    Soit j'ouvre la page "/produits"
    Alors la page affiche le texte "{{resultat}}"
"""


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "db.sqlite")
    conn = get_initialized_db(config.DB_PATH)
    yield conn
    conn.close()


def _projet(conn, *, lignes, compte_du_cas=False, feature=QUI, base_url="http://app"):
    """`lignes` : [(nom, resultat, compte)] — compte : None (case vide), "principal", "Lecteur"."""
    pid = ProjectRepo(conn).create(name="Droits", connector_type="web", base_url=base_url)
    lecteur = ProjectAccountRepo(conn).create(pid, label="Lecteur", username="lecteur", password="motdepasse-lecteur")
    cid = CaseRepo(conn).create(title="Qui", module_id=ModuleRepo(conn).create(project_id=pid, name="M"), feature_slug="qui")
    # Le test est réputé écrit pour TOUS les comptes du projet (ce que note une génération faite avec ces lignes) : ces tests
    # portent sur l'exécution des lignes ; l'écart « écrit pour » a les siens (`test_generation_par_compte.py`).
    ecrit = {"compte_id": lecteur if compte_du_cas else None, "libelle": "Lecteur" if compte_du_cas else "principal",
             "vue": "principal", "comptes_des_lignes": [0, lecteur]}
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content=feature, steps_content="",
                                   compte_id=lecteur if compte_du_cas else None,
                                   generation_provenance=json.dumps({"ecrit_pour": ecrit}))
    conn.execute("UPDATE test_case SET current_version_id=? WHERE id=?", (vid, cid))
    conn.commit()
    ids = {"resultat": TestDataRepo(conn).creer_variable(pid, nom="resultat")}
    CaseDataRepo(conn).remplacer(cid, pid, [
        {"nom": nom, "valeurs": {ids["resultat"]: resultat}, "compte_choisi": compte is not None,
         "compte_id": lecteur if compte == "Lecteur" else None} for nom, resultat, compte in lignes])
    return pid, cid, vid, lecteur


def _joue(conn, cid, vid):
    eid = ExecutionRepo(conn).create(test_case_id=cid, version_id=vid)
    script = service.preparer_le_script(conn, eid, cid, vid, "qui")
    return script, (script.dossier / "qui.feature").read_text(encoding="utf-8") if script.dossier else ""


def _comptes_des_iterations(texte: str) -> list[tuple[str, str]]:
    modele = parse_feature(texte, language="fr")
    return [(s._row[iterations_mod.COLONNE_COMPTE], s._row["resultat"] if "resultat" in s._row.headings else "")
            for plan in modele.scenarios for s in plan.scenarios]


# ── 1. Dépôt et API ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_seul_un_compte_du_projet_et_rien_n_est_ecrit_a_moitie(base):
    pid, cid, _, lecteur = _projet(base, lignes=[("L1", "a", None), ("L2", "b", "Lecteur")])
    autre = ProjectRepo(base).create(name="Autre", connector_type="web", base_url="http://autre")
    etranger = ProjectAccountRepo(base).create(autre, label="Intrus", username="i", password="p")
    avant = CaseDataRepo(base).comptes_des_lignes(cid)
    with pytest.raises(DonneeDeTestInvalide, match="comptes : principal, Lecteur"):
        CaseDataRepo(base).remplacer(cid, pid, [{"nom": "L1", "valeurs": {}, "compte_choisi": True, "compte_id": etranger}])
    assert CaseDataRepo(base).comptes_des_lignes(cid) == avant == [
        {"nom": "L1", "choisi": False, "compte_id": None}, {"nom": "L2", "choisi": True, "compte_id": lecteur}]


def test_l_ecran_dit_avec_quel_compte_chaque_ligne_sera_jouee(base, monkeypatch):
    pid, cid, _, lecteur = _projet(base, lignes=[("L1", "a", None), ("L2", "b", "Lecteur"), ("L3", "c", "principal")],
                                   compte_du_cas=True)
    client = TestClient(app_mod.app)
    tableau = client.get(f"/api/cases/{cid}/donnees-de-test").json()
    assert [l["compte_joue"] for l in tableau["lignes"]] == ["Lecteur (compte du cas)", "Lecteur", "principal"]
    assert [c["libelle"] for c in tableau["comptes"]] == ["principal", "Lecteur"]
    ProjectAccountRepo(base).supprimer(pid, lecteur)
    tableau = client.get(f"/api/cases/{cid}/donnees-de-test").json()
    # Revue : des lignes ont leur compte — la colonne reste, et dit la vérité (jamais un choix effacé en silence).
    assert [c["libelle"] for c in tableau["comptes"]] == ["principal"]
    assert [l["compte_joue"] for l in tableau["lignes"]] == ["compte supprimé (compte du cas)", "compte supprimé",
                                                            "principal"]


def test_sans_aucun_compte_choisi_ni_autre_compte_rien_n_est_montre(base):
    pid, cid, _, lecteur = _projet(base, lignes=[("L1", "a", None)])
    ProjectAccountRepo(base).supprimer(pid, lecteur)
    tableau = TestClient(app_mod.app).get(f"/api/cases/{cid}/donnees-de-test").json()
    assert tableau["comptes"] == [] and tableau["lignes"][0]["compte_joue"] == ""


def test_l_api_refuse_un_compte_d_un_autre_projet(base):
    pid, cid, _, _ = _projet(base, lignes=[("L1", "a", None)])
    autre = ProjectRepo(base).create(name="Autre", connector_type="web", base_url="http://autre")
    etranger = ProjectAccountRepo(base).create(autre, label="Intrus", username="i", password="p")
    variable = str(TestDataRepo(base).variables(pid)[0]["id"])
    reponse = TestClient(app_mod.app).put(f"/api/cases/{cid}/donnees-de-test", json={"lignes": [
        {"nom": "L1", "valeurs": {variable: "a"}, "compte_choisi": True, "compte_id": etranger}]})
    assert reponse.status_code == 422 and "pas (ou plus) de ce projet" in reponse.json()["detail"]


# ── 2-3. Préparation des itérations ──────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_deux_lignes_qui_ne_different_que_par_le_compte_sont_deux_iterations(base):
    _, cid, vid, _ = _projet(base, lignes=[("Principal", "Connecté", "principal"), ("Lecteur", "Connecté", "Lecteur")])
    script, texte = _joue(base, cid, vid)
    assert script.blocage == ""
    assert _comptes_des_iterations(texte) == [("principal", "Connecté"), ("Lecteur", "Connecté")]
    joues = json.loads(base.execute("SELECT parametres_joues FROM execution ORDER BY id DESC").fetchone()[0])
    assert [(i["jeu"], i["compte"]) for i in joues["iterations"]] == [("Principal", "principal"), ("Lecteur", "Lecteur")]


def test_falsifiable_sans_aucune_variable_le_compte_seul_fait_deux_iterations(base):
    # Des lignes qui ne portent QUE leur compte (aucune valeur) : sans le compte, une seule itération, et « B » jamais jouée.
    _, cid, vid, _ = _projet(base, lignes=[("A", "", "principal"), ("B", "", "Lecteur")],
                             feature=QUI.replace('"{{resultat}}"', '"Connecté"'))
    _, texte = _joue(base, cid, vid)
    assert [c for c, _ in _comptes_des_iterations(texte)] == ["principal", "Lecteur"]


def test_a91_une_case_vide_reprend_le_compte_du_cas(base):
    _, cid, vid, _ = _projet(base, lignes=[("Vide", "a", None), ("Principal", "b", "principal")], compte_du_cas=True)
    _, texte = _joue(base, cid, vid)
    assert [c for c, _ in _comptes_des_iterations(texte)] == ["Lecteur", "principal"]


def test_falsifiable_a92_un_compte_supprime_bloque_le_test_ligne_nommee(base):
    pid, cid, vid, lecteur = _projet(base, lignes=[("L1", "a", None), ("L2", "b", "Lecteur")])
    ProjectAccountRepo(base).supprimer(pid, lecteur)
    script, _ = _joue(base, cid, vid)
    assert script.blocage == ("Données de test : la ligne « L2 » est jouée avec un compte supprimé — choisissez-en un autre. "
                              "Le test n'a pas été joué.")


def test_falsifiable_a92_un_compte_supprime_apres_le_lancement_de_la_campagne_bloque_tout(base):
    """Revue : figé par identifiant au lancement — supprimé ENSUITE, le test entier n'est pas joué, la ligne nommée."""
    from testpilot.store.repositories import RunRepo

    pid, cid, vid, lecteur = _projet(base, lignes=[("L1", "a", "principal"), ("L2", "b", "Lecteur")])
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    ProjectAccountRepo(base).supprimer(pid, lecteur)
    eid = ExecutionRepo(base).create(test_case_id=cid, version_id=vid)
    base.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    base.commit()
    script = service.preparer_le_script(base, eid, cid, vid, "qui")
    assert script.blocage.startswith("Données de test : la ligne « L2 » est jouée avec un compte supprimé")


def test_un_compte_renomme_apres_le_lancement_est_joue_sous_son_nom_d_aujourd_hui(base):
    from testpilot.store.repositories import RunRepo

    pid, cid, vid, lecteur = _projet(base, lignes=[("L1", "a", "principal"), ("L2", "b", "Lecteur")])
    run_id = RunRepo(base).create(project_id=pid, name="Nuit", case_ids=[cid])
    service.figer_pour_la_campagne(base, RunRepo(base).get(run_id))
    ProjectAccountRepo(base).modifier(pid, lecteur, label="Consultant")
    eid = ExecutionRepo(base).create(test_case_id=cid, version_id=vid)
    base.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
    base.commit()
    script = service.preparer_le_script(base, eid, cid, vid, "qui")
    texte = (script.dossier / "qui.feature").read_text(encoding="utf-8")
    assert [c for c, _ in _comptes_des_iterations(texte)] == ["principal", "Consultant"] and script.comptes_par_iteration


def test_tp_est_un_prefixe_reserve():
    from testpilot.parametres import resolution

    with pytest.raises(resolution.NomInvalide, match="réservé à TestPilot"):
        resolution.valider_nom("tp_compte")


def test_des_lignes_sans_compte_se_jouent_comme_avant(base):
    _, cid, vid, _ = _projet(base, lignes=[("L1", "a", None), ("L2", "b", None)])
    _, texte = _joue(base, cid, vid)
    assert iterations_mod.COLONNE_COMPTE not in texte


# ── 4. Le harnais ────────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def H():
    sys.path.insert(0, str(_STEPS_LIB))
    import _base_helpers
    return _base_helpers


class _Ligne:
    def __init__(self, **cellules):
        self.headings, self._c = list(cellules), cellules

    def __getitem__(self, cle):
        return self._c[cle]


def test_falsifiable_le_harnais_connecte_le_compte_de_l_iteration(H, monkeypatch):
    monkeypatch.setenv(H.ENV_COMPTES_PAR_ITERATION, "1")
    connexions = []
    monkeypatch.setattr(H, "se_connecter_en_tant_que", lambda ctx, libelle, connecteur: connexions.append(libelle))
    ctx = SimpleNamespace(compte_courant="principal", active_outline=_Ligne(resultat="x", tp_compte="Lecteur"))
    H.appliquer_compte_de_l_iteration(ctx, "web")
    assert connexions == ["Lecteur"] and ctx.compte_de_l_iteration == "Lecteur"
    ctx = SimpleNamespace(compte_courant="Lecteur", active_outline=_Ligne(tp_compte="lecteur"))
    H.appliquer_compte_de_l_iteration(ctx, "web")
    assert connexions == ["Lecteur"], "déjà connecté avec ce compte : rien à refaire"
    ctx = SimpleNamespace(compte_courant="principal", active_outline=None)
    H.appliquer_compte_de_l_iteration(ctx, "web")
    assert ctx.compte_de_l_iteration is None


def test_falsifiable_une_colonne_tp_compte_que_le_serveur_n_a_pas_ecrite_n_est_jamais_obeie(H, monkeypatch):
    """Revue (décision 0015) : un plan écrit par l'agent avec `| tp_compte |` — sans le signal du serveur, rien n'est fait."""
    monkeypatch.delenv(H.ENV_COMPTES_PAR_ITERATION, raising=False)
    monkeypatch.setattr(H, "se_connecter_en_tant_que", lambda *a, **k: pytest.fail("aucune connexion"))
    ctx = SimpleNamespace(compte_courant="Lecteur", active_outline=_Ligne(tp_compte="principal"))
    H.appliquer_compte_de_l_iteration(ctx, "web")
    assert ctx.compte_de_l_iteration is None


def test_falsifiable_une_ligne_a_compte_ne_change_pas_de_compte_en_route(H):
    """Revue (bloquant) : refusé DANS le step de connexion (Soit/Quand) — « bloqué » avec la raison, jamais « à rejouer » muet."""
    ctx = SimpleNamespace(compte_de_l_iteration="Lecteur", compte_courant="Lecteur")
    with pytest.raises(H.PreconditionNonRemplieError, match="jouée en tant que « Lecteur »"):
        H.se_connecter_en_tant_que(ctx, "principal", connecteur="web")


# ── 5. Vrai Behave, vrai Chromium, application du banc ───────────────────────────────────────────────────────────────────

@contextmanager
def _application():
    from banc.app_web import serveur
    srv = serveur.creer_serveur("127.0.0.1", 0, "")
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        fil.join(timeout=5)


@pytest.mark.conformance
def test_falsifiable_vrai_navigateur_chaque_ligne_est_jouee_avec_son_compte(base):
    """Ligne « Testeur » : la page doit dire « Connecté en tant que testeur » ; ligne « Lecteur » : « … lecteur ». Si le
    harnais ignorait le compte de la ligne, la seconde itération verrait « testeur » et échouerait."""
    from banc.app_web import serveur
    from testpilot.connectors.runtime_env import ENV_COMPTES
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.execution.executor import Executor
    from testpilot.verdict import status as st

    with _application() as url:
        _, cid, vid, _ = _projet(base, base_url=url, lignes=[
            ("Testeur", "Connecté en tant que testeur", "principal"), ("Lecteur", "Connecté en tant que lecteur", "Lecteur")])
        script, texte = _joue(base, cid, vid)
        assert script.blocage == "" and _comptes_des_iterations(texte) == [
            ("principal", "Connecté en tant que testeur"), ("Lecteur", "Connecté en tant que lecteur")]
        (script.dossier / "qui_steps.py").write_text("from behave import given, when, then\n", encoding="utf-8")
        connexion = {"WEB_URL": url, "WEB_USER": serveur.IDENTIFIANT_TEST, "WEB_PASSWORD": serveur.MOT_DE_PASSE_TEST,
                     ENV_COMPTES: json.dumps([{"label": "Lecteur", "username": serveur.IDENTIFIANT_LECTEUR,
                                               "password": serveur.MOT_DE_PASSE_LECTEUR}]),
                     "TESTPILOT_COMPTES_PAR_ITERATION": "1"}
        outcome = Executor(BehaveRunner(connection=connexion, connector_type="web", generated_dir=script.dossier),
                           max_retries=0).execute("qui")
        verdict = st.derive_verdict(outcome, connector_type="web")
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME), \
        outcome.real_run.raw_stderr[-2000:] if outcome.real_run else ""
    assert outcome.real_run.passed == 2



@pytest.mark.conformance
def test_falsifiable_vrai_navigateur_une_ligne_qui_change_de_compte_sort_bloquee(base):
    """Revue (bloquant, mesuré) : levé avant un « Alors », le refus sortait « à rejouer » sans un mot. Levé dans le step de
    connexion lui-même, la ligne « Lecteur » qui se reconnecte en principal sort BLOQUÉE, avec la raison."""
    from banc.app_web import serveur
    from testpilot.connectors.runtime_env import ENV_COMPTES
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.execution.executor import Executor
    from testpilot.verdict import status as st

    change = QUI.replace("    Alors la page affiche", '    Et je me connecte en tant que "principal"\n    Alors la page affiche')
    with _application() as url:
        _, cid, vid, _ = _projet(base, base_url=url, feature=change, lignes=[("Lecteur", "Connecté en tant que testeur",
                                                                              "Lecteur")])
        script, _ = _joue(base, cid, vid)
        (script.dossier / "qui_steps.py").write_text("from behave import given, when, then\n", encoding="utf-8")
        connexion = {"WEB_URL": url, "WEB_USER": serveur.IDENTIFIANT_TEST, "WEB_PASSWORD": serveur.MOT_DE_PASSE_TEST,
                     ENV_COMPTES: json.dumps([{"label": "Lecteur", "username": serveur.IDENTIFIANT_LECTEUR,
                                               "password": serveur.MOT_DE_PASSE_LECTEUR}]),
                     "TESTPILOT_COMPTES_PAR_ITERATION": "1"}
        outcome = Executor(BehaveRunner(connection=connexion, connector_type="web", generated_dir=script.dossier),
                           max_retries=0).execute("qui")
        verdict = st.derive_verdict(outcome, connector_type="web")
    assert (verdict.execution_status, verdict.functional_status) == (st.EXEC_BLOCKED, st.FUNC_INDETERMINE), \
        (verdict, outcome.real_run.raw_stderr[-1500:] if outcome.real_run else "")
    assert outcome.dry_run_passed, "le test est valide : il est bloqué par le refus, pas par une étape inconnue"
    raisons = " ".join(f.raw or "" for f in outcome.real_run.failures)
    assert "jouée en tant que « Lecteur »" in raisons, raisons[-800:]



# ── Revue, seconde passe : les maillons entre le serveur et le harnais ───────────────────────────────────────────────────

def test_falsifiable_l_execution_transmet_le_signal_seulement_quand_le_serveur_a_ecrit_les_comptes(monkeypatch):
    from testpilot.api.services import run_service

    vus = []

    class _Runner:
        def __init__(self, **_kw):
            self.connection, self.remise_a_zero_url, self.remise_a_zero_refus, self.compte_refus = {}, None, "", ""

    monkeypatch.setattr(run_service, "BehaveRunner", _Runner)
    for nom in ("resolve_connection", "resolve_project_id", "resolve_connector_type", "resolve_profil_instance"):
        monkeypatch.setattr(run_service, nom, lambda *a, **k: None)
    monkeypatch.setattr(run_service, "get_initialized_db", lambda *a, **k: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(run_service, "adresse_de_remise_avant_test", lambda conn, cid: (None, ""))
    monkeypatch.setattr(run_service, "compte_du_test", lambda conn, cid, vid: (None, ""))
    monkeypatch.setattr(run_service, "_execute_and_persist",
                        lambda conn, eid, cid, module, runner, **o: vus.append(dict(runner.connection)))
    monkeypatch.setattr(run_service, "_maybe_repair", lambda *a, **k: None)
    for avec in (True, False):
        monkeypatch.setattr(run_service, "_assurer_script_sur_disque",
                            lambda *a, avec=avec, **k: service.Script(comptes_par_iteration=avec))
        run_service.run_execution(1, "m", 1, 1)
    assert vus[0].get("TESTPILOT_COMPTES_PAR_ITERATION") == "1" and "TESTPILOT_COMPTES_PAR_ITERATION" not in vus[1]


def test_falsifiable_le_signal_ne_s_herite_jamais_de_l_environnement_du_serveur(monkeypatch, tmp_path):
    from testpilot.execution.behave_runner import BehaveRunner

    monkeypatch.setenv("TESTPILOT_COMPTES_PAR_ITERATION", "1")
    env = BehaveRunner(connection={"WEB_URL": "http://app"}, generated_dir=tmp_path)._subprocess_env(tmp_path, "m")
    assert env["TESTPILOT_COMPTES_PAR_ITERATION"] == ""


def test_falsifiable_les_observateurs_sont_installes_avant_le_changement_de_compte():
    """Revue (bloquant B2) : installés APRÈS un changement de compte, ils doublaient le gestionnaire des boîtes de dialogue
    (un orphelin refusait toute confirmation : faux « Passé »). L'ordre des crochets de `before_scenario` est la garantie."""
    import inspect
    import importlib.util

    chemin = Path(__file__).resolve().parent.parent / "behave_runtime" / "environment.py"
    texte = chemin.read_text(encoding="utf-8")
    debut = texte.index("def before_scenario(")
    corps = texte[debut:texte.index("\ndef ", debut + 10)]
    assert corps.index("installer_les_observateurs(context)") < corps.index("appliquer_compte_de_l_iteration(context")
    assert corps.index("_capturer_reponse_formulaire(context)") < corps.index("appliquer_compte_de_l_iteration(context")
    assert corps.index("appliquer_compte_de_l_iteration(context") < corps.index("noter_session_ouverte(context)")
    assert inspect and importlib.util


def test_une_ancienne_variable_tp_compte_bloque_les_lignes_a_compte(base):
    pid, cid, vid, _ = _projet(base, lignes=[("L1", "a", "principal"), ("L2", "b", "Lecteur")])
    base.execute("INSERT INTO test_variable (project_id, nom, description, created_at, deleted_at) "
                 "VALUES (?, 'tp_compte', '', 'x', '')", (pid,))
    base.commit()
    script, _ = _joue(base, cid, vid)
    assert "nom réservé à TestPilot" in script.blocage
