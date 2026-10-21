"""Étape 4 du plan unique (A70, A73 — porteur, 2026-10-20) : le compte avec lequel un cas est joué.

Ce que ces tests gardent :
1. le compte fait partie de la VERSION : hérité par toute nouvelle version (édition, correction, réparation, régénération),
   changé seulement par l'édition du cas ; copié dans un autre projet, il revient au principal ;
2. on ne choisit qu'un compte du projet ; la fiche liste les comptes par leur libellé, jamais leurs identifiants ;
3. l'exécution transmet le LIBELLÉ ; un compte disparu bloque le cas — jamais un repli silencieux sur le principal ;
4. le harnais joue les écrans avec ce compte pour tout le run, et la session RPC des vérifications reste au principal (A73).
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from testpilot import config


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "a70.db")
    from testpilot.store.db import get_initialized_db
    c = get_initialized_db()
    yield c
    c.close()


def _projet_et_cas(conn, nom="P"):
    from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectAccountRepo, ProjectRepo, VersionRepo

    pid = ProjectRepo(conn).create(name=nom, connector_type="web", base_url="http://app")
    lecteur = ProjectAccountRepo(conn).create(pid, label="Lecteur", username="lecteur", password="motdepasse-lecteur")
    mid = ModuleRepo(conn).create(project_id=pid, name="m")
    cid = CaseRepo(conn).create(title="Devis", module_id=mid, feature_slug=f"devis_{nom}")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="F", steps_content="",
                                   title="Devis", test_steps=json.dumps(["x"]), expected_result="Refusé")
    CaseRepo(conn).set_current_version(cid, vid)
    return pid, lecteur, cid, vid


# ── 1. Le compte vit sur la version ───────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_le_compte_se_change_a_l_edition_et_suit_toute_nouvelle_version(conn):
    from testpilot.store.repositories import CaseRepo, VersionRepo

    pid, lecteur, cid, vid = _projet_et_cas(conn)
    assert VersionRepo(conn).get(vid)["compte_id"] is None, "toute version d'avant : le principal"
    v2 = CaseRepo(conn).update_metier(cid, compte_id=lecteur)
    assert v2 and VersionRepo(conn).get(v2)["compte_id"] == lecteur, "changer le compte crée une version"
    v3 = CaseRepo(conn).update_metier(cid, title="Devis (retouché)")
    assert VersionRepo(conn).get(v3)["compte_id"] == lecteur, "une édition sans compte le garde"
    v4 = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="", feature_content="F2", steps_content="")
    assert VersionRepo(conn).get(v4)["compte_id"] == lecteur, "une version créée ailleurs (correction, réparation…) le garde"
    assert CaseRepo(conn).update_metier(cid, compte_id=lecteur) is None, "rien n'a changé : pas de version fantôme"


def test_le_compte_ne_suit_pas_une_copie_dans_un_autre_projet(conn):
    from testpilot.store.repositories import CaseGroupRepo, CaseRepo, ModuleRepo, ProjectRepo, VersionRepo

    pid, lecteur, cid, _ = _projet_et_cas(conn)
    CaseRepo(conn).update_metier(cid, compte_id=lecteur)
    autre = ProjectRepo(conn).create(name="Autre", connector_type="web", base_url="http://autre")
    mid = ModuleRepo(conn).create(project_id=autre, name="m2")
    gid = CaseGroupRepo(conn).create(module_id=mid, title="Section")
    copie_id = CaseRepo(conn).copier(cid, gid)
    assert VersionRepo(conn).get(CaseRepo(conn).get(copie_id)["current_version_id"])["compte_id"] is None,         "un compte appartient à SON projet"
    mid_meme = CaseRepo(conn).get(cid)["module_id"]
    gid_meme = CaseGroupRepo(conn).create(module_id=mid_meme, title="Même projet")
    copie_meme = CaseRepo(conn).copier(cid, gid_meme)
    assert VersionRepo(conn).get(CaseRepo(conn).get(copie_meme)["current_version_id"])["compte_id"] == lecteur


# ── 3. L'exécution ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_l_execution_transmet_le_libelle_et_bloque_un_compte_disparu(conn):
    from testpilot.api.services import run_service
    from testpilot.store.repositories import CaseRepo, ProjectAccountRepo

    pid, lecteur, cid, vid = _projet_et_cas(conn)
    assert run_service.compte_du_test(conn, cid, vid) == (None, ""), "principal : comportement d'avant"
    v2 = CaseRepo(conn).update_metier(cid, compte_id=lecteur)
    assert run_service.compte_du_test(conn, cid, v2) == ("Lecteur", "")
    ProjectAccountRepo(conn).supprimer(pid, lecteur) if hasattr(ProjectAccountRepo, "supprimer") else \
        conn.execute("DELETE FROM project_account WHERE id=?", (lecteur,))
    conn.commit()
    libelle, refus = run_service.compte_du_test(conn, cid, v2)
    assert libelle is None and "n'existe plus" in refus, "jamais rejoué avec le principal en silence"


def test_falsifiable_un_compte_disparu_ne_lance_pas_behave(tmp_path, monkeypatch):
    from testpilot.execution import behave_runner as br

    lances = []
    monkeypatch.setattr(br.subprocess, "run", lambda *a, **k: lances.append(a))
    (tmp_path / "gen").mkdir()
    (tmp_path / "gen" / "m.feature").write_text("# language: fr\nFonctionnalité: F\n", encoding="utf-8")
    (tmp_path / "gen" / "m_steps.py").write_text("", encoding="utf-8")
    runner = br.BehaveRunner(generated_dir=tmp_path / "gen", connection={"WEB_URL": "http://app"})
    runner.compte_refus = "le compte choisi pour ce cas n'existe plus"
    resultat = runner.real_run("m")
    assert lances == [] and resultat.returncode == -3 and resultat.prerequis_manquant


def test_falsifiable_l_execution_reelle_pose_le_compte_sur_le_lanceur(monkeypatch):
    from testpilot.api.services import run_service
    from testpilot.connectors.runtime_env import ENV_COMPTE_DU_TEST

    vus = {}

    class _Runner:
        def __init__(self, **_kw):
            self.connection, self.remise_a_zero_url, self.remise_a_zero_refus, self.compte_refus = {}, None, "", ""

    monkeypatch.setattr(run_service, "BehaveRunner", _Runner)
    for nom in ("resolve_connection", "resolve_project_id", "resolve_connector_type", "resolve_profil_instance"):
        monkeypatch.setattr(run_service, nom, lambda *a, **k: None)
    monkeypatch.setattr(run_service, "_assurer_script_sur_disque", lambda *a, **k: None)
    monkeypatch.setattr(run_service, "get_initialized_db", lambda *a, **k: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(run_service, "adresse_de_remise_avant_test", lambda conn, cid: (None, ""))
    monkeypatch.setattr(run_service, "compte_du_test", lambda conn, cid, vid: ("Lecteur", ""))
    monkeypatch.setattr(run_service, "_execute_and_persist",
                        lambda conn, eid, cid, module, runner, **o: vus.setdefault("env", dict(runner.connection)))
    monkeypatch.setattr(run_service, "_maybe_repair", lambda *a, **k: None)

    run_service.run_execution(1, "m", 1, 1)
    assert vus["env"].get(ENV_COMPTE_DU_TEST) == "Lecteur"


# ── 4. Le harnais ────────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def H():
    sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
    import _base_helpers
    return _base_helpers


def _ctx(H, connecteur="web"):
    comptes, erreur = H.construire_comptes(connecteur, {
        "WEB_USER": "admin", "WEB_PASSWORD": "pw-admin", "ODOO_USER": "admin", "ODOO_PASSWORD": "pw-admin",
        "TESTPILOT_COMPTES": json.dumps([{"label": "Lecteur", "username": "lecteur", "password": "pw-lecteur"}])})
    return SimpleNamespace(comptes=comptes, comptes_erreur=erreur, compte_courant="principal", web_user="admin",
                           web_password="pw-admin", odoo_user="admin", odoo_password="pw-admin")


@pytest.mark.parametrize("connecteur, champ", [("web", "web_user"), ("odoo", "odoo_user")])
def test_falsifiable_le_harnais_joue_les_ecrans_avec_le_compte_du_cas(H, connecteur, champ):
    ctx = _ctx(H, connecteur)
    assert H.appliquer_compte_du_test(ctx, connecteur, "lecteur") == ""
    assert getattr(ctx, champ) == "lecteur" and ctx.compte_courant == ctx.compte_du_test == "Lecteur"


def test_falsifiable_un_compte_inconnu_bloque_sans_repli_sur_le_principal(H):
    ctx = _ctx(H)
    erreur = H.appliquer_compte_du_test(ctx, "web", "Gestionnaire")
    assert "n'existe pas" in erreur and ctx.web_user == "admin" and ctx.compte_du_test == "principal"


def test_le_principal_ou_rien_ne_change_rien(H):
    for libelle in ("", "principal", "  Principal "):
        ctx = _ctx(H)
        assert H.appliquer_compte_du_test(ctx, "web", libelle) == "" and ctx.web_user == "admin"


def test_falsifiable_la_fin_d_un_scenario_revient_au_compte_du_run_pas_au_principal(H):
    ctx = _ctx(H)
    H.appliquer_compte_du_test(ctx, "web", "Lecteur")
    ctx.compte_courant, ctx.web_user = "principal", "admin"   # un scénario s'est connecté en principal
    H.retablir_le_compte_principal(ctx)
    assert ctx.compte_courant == "Lecteur" and ctx.web_user == "lecteur", "le scénario suivant se joue avec le compte du cas"


# ── 2. L'API ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_on_ne_choisit_qu_un_compte_du_projet_et_la_fiche_ne_montre_que_des_libelles(conn):
    from fastapi.testclient import TestClient

    from testpilot.api import app as app_mod

    pid, lecteur, cid, _ = _projet_et_cas(conn)
    _, etranger, _, _ = _projet_et_cas(conn, nom="Autre")
    client = TestClient(app_mod.app)

    refus = client.patch(f"/api/cases/{cid}/metier", json={"compte_id": etranger})
    assert refus.status_code == 422, refus.text
    assert client.patch(f"/api/cases/{cid}/metier", json={"compte_id": lecteur}).status_code == 200

    fiche = client.get(f"/api/cases/{cid}").json()
    # Étape 4, morceau 6 (A80, porteur 2026-10-21) : chaque compte porte aussi l'état de sa dernière exploration.
    assert [(c["id"], c["libelle"]) for c in fiche["comptes"]] == [(None, "principal"), (lecteur, "Lecteur")]
    assert fiche["comptes"][1]["exploration"] == "jamais", "jamais exploré : la fiche du cas le dira"
    assert "motdepasse-lecteur" not in json.dumps(fiche), "jamais un mot de passe"
    assert all(set(c) == {"id", "libelle", "exploration", "exploration_message"} for c in fiche["comptes"]),         "jamais un identifiant de connexion (D8)"
    assert "lecteur" not in json.dumps(fiche["comptes"]).replace("Lecteur", ""), "l'identifiant « lecteur » n'apparaît nulle part"
    courante = next(v for v in fiche["versions"] if v["id"] == fiche["current_version_id"])
    assert courante["compte_id"] == lecteur
    assert client.patch(f"/api/cases/{cid}/metier", json={"compte_id": None}).status_code == 200, "retour au principal"


def test_falsifiable_web_la_fin_d_un_scenario_rend_les_ecrans_au_principal(H):
    """Revue de l'étape 4 (2026-10-21) : en web il n'y a pas de session RPC. Avant, le retour au principal s'arrêtait là — le
    scénario suivant gardait les identifiants du lecteur, et une reconnexion l'aurait joué avec le mauvais compte."""
    ctx = _ctx(H)
    ctx.odoo = None
    ctx.compte_courant, ctx.web_user, ctx.web_password = "Lecteur", "lecteur", "pw-lecteur"   # step « je me connecte en tant que »
    H.retablir_le_compte_principal(ctx)
    assert (ctx.compte_courant, ctx.web_user, ctx.web_password) == ("principal", "admin", "pw-admin")


def test_falsifiable_sans_connexion_un_cas_joue_en_tant_que_bloque(H):
    """Revue de l'étape 4 (bloquant) : stratégie « aucune » + compte du cas = un run ANONYME qui sortait conforme."""
    assert "joué en tant que « Lecteur »" in H.refus_du_compte_sans_connexion("web", "aucune", "Lecteur")
    assert H.refus_du_compte_sans_connexion("web", "aucune", "principal") == ""
    assert H.refus_du_compte_sans_connexion("web", "formulaire", "Lecteur") == ""
    assert H.refus_du_compte_sans_connexion("odoo", "aucune", "Lecteur") == "", "Odoo se connecte toujours par l'écran"


def test_falsifiable_une_connexion_ratee_rend_les_identifiants_d_avant(H, monkeypatch):
    """Revue de l'étape 4 : un `goto` qui expire laissait les identifiants du compte refusé, `compte_courant` inchangé — le
    retour de fin de scénario sortait alors tôt et le scénario suivant se jouait avec le mauvais compte."""
    ctx = _ctx(H)
    ctx.web_url, ctx._reouvrir_contexte = "http://app", lambda: None

    def _expire(*a, **k):
        raise TimeoutError("goto")
    ctx.page = SimpleNamespace(goto=_expire)
    with pytest.raises(TimeoutError):
        H.se_connecter_en_tant_que(ctx, "Lecteur", connecteur="web")
    assert (ctx.web_user, ctx.web_password, ctx.compte_courant) == ("admin", "pw-admin", "principal")


def test_falsifiable_odoo_une_connexion_ratee_rend_les_identifiants_d_avant(H, monkeypatch):
    ctx = _ctx(H, "odoo")
    ctx.odoo_url, ctx._reouvrir_contexte = "http://odoo:8069", lambda: None

    def _refuse(c):
        raise RuntimeError("écran de connexion")
    monkeypatch.setattr(H, "playwright_login", _refuse)
    with pytest.raises(H.PreconditionNonRemplieError):
        H.se_connecter_en_tant_que(ctx, "Lecteur", connecteur="odoo")
    assert (ctx.odoo_user, ctx.odoo_password, ctx.compte_courant) == ("admin", "pw-admin", "principal")
