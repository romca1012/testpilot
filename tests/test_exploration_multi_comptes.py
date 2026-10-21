"""Étape 4, morceau 6 (A69 révisée, A77-A83 — porteur, 2026-10-21) : UNE exploration de l'application, par tous les comptes.

Ce que ces tests gardent :
1. la vue du principal (`projet-N.json`) est EXACTEMENT celle d'avant, qu'il y ait des comptes ou non — tous ses lecteurs
   d'aujourd'hui n'y voient rien de nouveau ;
2. chaque compte est parcouru avec SES identifiants ; un compte en échec n'arrête jamais les autres ; jamais un relevé
   anonyme attribué à un compte ; ni identifiant ni mot de passe dans un fichier ;
3. l'écran sait dire, par compte : exploré, en échec (et pourquoi), à actualiser (ajouté, identifiant changé) ;
4. une exploration arrêtée est dite incomplète, jamais présentée comme complète (A83) ;
5. pendant l'exploration, l'application est occupée : un test n'est pas joué, un essai est refusé (A77) ;
6. la carte (qui voit quoi) existe, mais aucun lecteur d'aujourd'hui ne la lit (morceau 7).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from testpilot import config
from testpilot.api.services import exploration_service as es
from testpilot.generation import domain_model

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isole(tmp_path, monkeypatch):
    d = tmp_path / "domain"
    d.mkdir()
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", d)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "multi.db")
    domain_model._charger.cache_clear()
    es._JOBS.clear()
    from testpilot.guardrails import bac_a_sable
    bac_a_sable.reinitialiser_pour_les_tests()
    yield d
    domain_model._charger.cache_clear()


@pytest.fixture
def conn():
    from testpilot.store.db import get_initialized_db
    c = get_initialized_db()
    yield c
    c.close()


def _page(*champs, liens=()):
    return {"champs": [{"name": n, "identifie_par": "name", "tag": "input", "type": "text", "visible": True, "label": n}
                       for n in champs],
            "actions": [], "liens": [{"href": h, "text": t} for h, t in liens], "formulaires": [], "titre": "",
            "url_exemple": ""}


ECRANS = {
    "admin": {"/commandes": _page("client", "remise"), "/comptabilite": _page()},
    "lecteur": {"/commandes": _page("client", liens=[("/profil", "Connecté : lecteur — motdepasse-lecteur")])},
    "comptable": {"/commandes": _page("client"), "/comptabilite": _page("journal")},
}


def _faux_crawl(appels, *, refuses=(), arreter_apres=None):
    def crawl(connexion, max_pages):
        suivi = connexion.get("_suivi") or {}
        appels.append({"username": connexion["username"], "password": connexion["password"],
                       "compte": connexion.get("compte_libelle"), "max_pages": max_pages})
        if connexion["username"] in refuses:
            raise es.ConnexionDuCompteImpossible("connexion impossible : l'écran de connexion est resté affiché")
        pages = dict(ECRANS[connexion["username"]])
        for n in range(1, len(pages) + 1):
            if suivi.get("progression"):
                suivi["progression"](n)
        arretee = bool(arreter_apres and connexion["username"] == arreter_apres)
        return {"pages": pages, "transitions": {}, "onglets_internes": {}, "modeles_backoffice": [], "familles": {},
                "_arretee": arretee, "_interrompue": False}
    return crawl


def _projet(conn, *, comptes=(("Lecteur", "lecteur", "motdepasse-lecteur"), ("Comptable", "comptable", "pw-comptable")),
            connecteur="odoo", strategie="", nom="P"):
    from testpilot.store.repositories import ProjectAccountRepo, ProjectRepo

    pid = ProjectRepo(conn).create(name=nom, connector_type=connecteur, base_url="http://app.local:8069")
    if strategie:
        conn.execute("UPDATE project SET auth_strategie=? WHERE id=?", (strategie, pid))
        conn.commit()
    ids = [ProjectAccountRepo(conn).create(pid, label=l, username=u, password=p) for l, u, p in comptes]
    return pid, ids


def _explorer(conn, pid, *, strategie="", connecteur="odoo"):
    from testpilot.connectors.runtime_env import comptes_pour_l_exploration

    es._JOBS["J"] = es._nouveau_job(pid)
    es.run_exploration("J", project_id=pid, comptes=comptes_pour_l_exploration(conn, pid), connexion={
        "base_url": "http://app.local:8069", "connector_type": connecteur, "nom": "P", "username": "admin",
        "password": "pw-admin", "auth_strategie": strategie})
    domain_model._charger.cache_clear()
    return es._JOBS["J"]


def _projet_dict(conn, pid):
    from testpilot.store.repositories import ProjectRepo
    return ProjectRepo(conn).get(pid)


# ── 1. La vue du principal ne change pas ─────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_la_vue_du_principal_est_identique_avec_ou_sans_comptes(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(es, "_crawl", _faux_crawl(appels))
    sans, _ = _projet(conn, comptes=(), nom="Sans comptes")
    avec, _ = _projet(conn)
    _explorer(conn, sans)
    _explorer(conn, avec)
    modele = lambda pid: json.loads(domain_model.chemin_du_modele(pid).read_text(encoding="utf-8"))  # noqa: E731
    a, b = modele(sans), modele(avec)
    a.pop("project_id"), b.pop("project_id")
    assert a == b, "les comptes n'ajoutent rien au modèle du principal"
    assert set(b["pages"]) == {"/commandes", "/comptabilite"}, "seulement ce que voit le principal"
    assert not domain_model.chemin_annexe_des_comptes(sans).exists()
    assert domain_model.chemin_annexe_des_comptes(avec).exists()


def test_a81_aucune_limite_de_pages_n_est_transmise_au_crawl(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(es, "_crawl", _faux_crawl(appels))
    pid, _ = _projet(conn)
    _explorer(conn, pid)
    assert {a["max_pages"] for a in appels} == {None}


# ── 2. Chaque compte, avec ses identifiants ──────────────────────────────────────────────────────────────────────────────

def test_falsifiable_chaque_compte_est_parcouru_avec_ses_identifiants_dans_l_ordre(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(es, "_crawl", _faux_crawl(appels))
    pid, _ = _projet(conn)
    job = _explorer(conn, pid)
    assert [(a["username"], a["password"], a["compte"]) for a in appels] == [
        ("admin", "pw-admin", None), ("lecteur", "motdepasse-lecteur", "Lecteur"), ("comptable", "pw-comptable", "Comptable")]
    assert job["status"] == "done" and "2 compte(s) sur 2" in job["resume"]
    assert job["progression"]["rang"] == 3 and job["progression"]["total"] == 3


def test_falsifiable_un_compte_en_echec_n_arrete_pas_les_autres_et_le_dit(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(es, "_crawl", _faux_crawl(appels, refuses=("lecteur",)))
    pid, (lecteur, comptable) = _projet(conn)
    job = _explorer(conn, pid)
    assert job["status"] == "done"
    etat = es.etat_des_comptes(conn, _projet_dict(conn, pid))["par_compte"]
    assert etat[lecteur]["statut"] == "connexion_impossible" and "connexion impossible" in etat[lecteur]["message"]
    assert etat[comptable]["statut"] == "explore"
    carte = es.charger_carte(conn, _projet_dict(conn, pid))
    assert all("Lecteur" not in e["vu_par"] for e in carte["routes"].values()), "jamais un relevé attribué sans connexion"


def test_falsifiable_ni_identifiant_ni_mot_de_passe_dans_l_annexe(conn, monkeypatch):
    monkeypatch.setattr(es, "_crawl", _faux_crawl([]))
    pid, _ = _projet(conn)
    _explorer(conn, pid)
    texte = domain_model.chemin_annexe_des_comptes(pid).read_text(encoding="utf-8")
    assert "motdepasse-lecteur" not in texte and "pw-comptable" not in texte
    assert "lecteur" not in texte.replace("Lecteur", ""), "le lien qui affichait l'identifiant est masqué"


def test_falsifiable_un_projet_web_sans_connexion_n_explore_aucun_compte(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(es, "_crawl", _faux_crawl(appels))
    pid, (lecteur, _) = _projet(conn, connecteur="web", strategie="aucune")
    _explorer(conn, pid, strategie="aucune", connecteur="web")
    assert [a["username"] for a in appels] == ["admin"], "aucun navigateur ouvert pour un compte"
    etat = es.etat_des_comptes(conn, _projet_dict(conn, pid))["par_compte"]
    assert etat[lecteur]["statut"] == "connexion_impossible" and "ne se connecte pas" in etat[lecteur]["message"]


# ── 3. Ce que l'écran dit, par compte ────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_a_actualiser_compte_ajoute_ou_identifiant_change_pas_le_mot_de_passe(conn, monkeypatch):
    from testpilot.store.repositories import ProjectAccountRepo

    monkeypatch.setattr(es, "_crawl", _faux_crawl([]))
    pid, (lecteur, comptable) = _projet(conn)
    _explorer(conn, pid)
    repo = ProjectAccountRepo(conn)
    repo.modifier(pid, comptable, password="nouveau")
    repo.modifier(pid, lecteur, username="lecteur2")
    nouveau = repo.create(pid, label="Stagiaire", username="stagiaire", password="pw-stagiaire")
    etat = es.etat_des_comptes(conn, _projet_dict(conn, pid))["par_compte"]
    assert etat[comptable]["statut"] == "explore", "un mot de passe changé ne change pas la personne"
    assert etat[lecteur] == {"libelle": "Lecteur", "statut": "a_actualiser",
                             "message": "identifiant changé depuis la dernière exploration"}
    assert etat[nouveau]["statut"] == "a_actualiser" and etat[nouveau]["message"] == "pas encore exploré"
    repo.supprimer(pid, comptable)
    assert comptable not in es.etat_des_comptes(conn, _projet_dict(conn, pid))["par_compte"]


def test_falsifiable_un_principal_reexplore_seul_rend_tous_les_comptes_a_actualiser(conn, monkeypatch):
    monkeypatch.setattr(es, "_crawl", _faux_crawl([]))
    pid, (lecteur, _) = _projet(conn)
    _explorer(conn, pid)
    chemin = domain_model.chemin_du_modele(pid)
    modele = json.loads(chemin.read_text(encoding="utf-8"))
    modele["pages"]["/nouvelle"] = _page()
    chemin.write_text(json.dumps(modele), encoding="utf-8")
    domain_model._charger.cache_clear()
    assert es.etat_des_comptes(conn, _projet_dict(conn, pid))["par_compte"][lecteur]["statut"] == "a_actualiser"


def test_l_api_montre_l_etat_des_comptes_et_l_arret(conn, monkeypatch):
    from fastapi.testclient import TestClient

    from testpilot.api import app as app_mod

    monkeypatch.setattr(es, "_crawl", _faux_crawl([], refuses=("comptable",)))
    pid, _ = _projet(conn)
    _explorer(conn, pid)
    client = TestClient(app_mod.app)
    etat = client.get(f"/api/projects/{pid}/exploration").json()
    assert etat["comptes_total"] == 2 and etat["pages"] == 2, "les nombres restent ceux du principal (A79)"
    assert [(c["libelle"], c["statut"]) for c in etat["comptes"]] == [("Lecteur", "explore"), ("Comptable", "connexion_impossible")]
    assert "motdepasse" not in json.dumps(etat) and "pw-" not in json.dumps(etat)
    assert client.post(f"/api/projects/{pid}/exploration/arret").status_code == 409, "rien à arrêter"


# ── 4. Arrêt : incomplète, jamais présentée comme complète ───────────────────────────────────────────────────────────────

def test_falsifiable_une_exploration_arretee_est_dite_incomplete(conn, monkeypatch):
    appels = []
    monkeypatch.setattr(es, "_crawl", _faux_crawl(appels, arreter_apres="admin"))
    pid, (lecteur, _) = _projet(conn)
    job = _explorer(conn, pid)
    assert [a["username"] for a in appels] == ["admin"], "arrêtée au principal : aucun compte parcouru"
    assert "exploration incomplète (arrêtée)" in job["resume"]
    etat = es.etat(pid, _projet_dict(conn, pid), conn=conn)
    assert (etat["incomplete"], etat["incomplete_pages"]) == ("arrêtée", 2)
    assert etat["comptes"][0]["statut"] == "a_actualiser"


def test_demander_l_arret_marque_le_job_en_cours():
    es._JOBS["J"] = es._nouveau_job(5)
    assert es.demander_arret(5) is True and es._JOBS["J"]["arret_demande"] is True
    assert es.demander_arret(6) is False


# ── 5. A77 : l'application est occupée pendant l'exploration ─────────────────────────────────────────────────────────────

def test_falsifiable_pendant_l_exploration_un_test_n_est_pas_joue_et_un_essai_est_refuse(conn, monkeypatch):
    from testpilot.guardrails import bac_a_sable

    vus = {}

    def crawl(connexion, max_pages):
        cle = bac_a_sable.cle_d_application("http://app.local:8069")
        try:
            with bac_a_sable.execution_reelle(cle):
                vus["test"] = "joué"
        except bac_a_sable.ApplicationOccupeeParExploration as exc:
            vus["test"] = str(exc)
        try:
            with bac_a_sable.essai(cle, attente_s=0):
                vus["essai"] = "joué"
        except bac_a_sable.BacASableOccupe as exc:
            vus["essai"] = str(exc)
        return _faux_crawl([])(connexion, max_pages)

    monkeypatch.setattr(es, "_crawl", crawl)
    pid, _ = _projet(conn, comptes=())
    _explorer(conn, pid)
    assert "occupée par l'exploration" in vus["test"] and "occupée par l'exploration" in vus["essai"]
    with bac_a_sable.execution_reelle(bac_a_sable.cle_d_application("http://app.local:8069")):
        pass   # après l'exploration : l'application est libre


# ── 6. La carte existe ; aucun lecteur d'aujourd'hui ne la lit ───────────────────────────────────────────────────────────

def test_la_carte_dit_qui_voit_quoi(conn, monkeypatch):
    monkeypatch.setattr(es, "_crawl", _faux_crawl([]))
    pid, _ = _projet(conn)
    _explorer(conn, pid)
    carte = es.charger_carte(conn, _projet_dict(conn, pid))
    assert carte["routes"]["/comptabilite"]["vu_par"] == ["principal", "Comptable"]
    assert carte["routes"]["/commandes"]["champs"]["remise|name|input"]["vu_par"] == ["principal"]


def test_aucun_lecteur_d_aujourd_hui_ne_lit_la_carte_avant_le_morceau_7():
    lecteurs = ["src/testpilot/api/services/generation_service.py", "src/testpilot/api/services/repair_service.py",
                "src/testpilot/generation/agent.py", "src/testpilot/generation/provenance.py",
                "src/testpilot/generation/prompt.py", "behave_runtime/steps_library/_base_helpers.py"]
    for chemin in lecteurs:
        texte = (RACINE / chemin).read_text(encoding="utf-8")
        for nom in ("charger_carte", "carte_des_comptes", "charger_annexe_des_comptes", "vue_du_compte"):
            assert nom not in texte, f"{chemin} lit {nom} : la génération changerait avant le morceau 7"


# ── 7. Les connecteurs prouvent que le compte est connecté ───────────────────────────────────────────────────────────────

class _Champ:
    def __init__(self, visible=True):
        self._visible = visible

    def is_visible(self):
        return self._visible


class _PageWeb:
    def __init__(self, url, mot_de_passe_visible, *, champs=None):
        self.url, self._mdp = url, mot_de_passe_visible
        self._champs = champs

    def query_selector_all(self, _sel):
        if self._champs is not None:
            return self._champs
        return [_Champ()] if self._mdp else []


def test_falsifiable_web_un_compte_n_est_confirme_que_si_l_ecran_a_quitte_la_connexion():
    from types import SimpleNamespace

    from testpilot.connectors.generic_web import GenericWebConnector

    c = GenericWebConnector("http://app.local")
    resta = SimpleNamespace(page=_PageWeb("http://app.local/login", True), url_avant_connexion="http://app.local/login",
                            connexion_soumise=True)
    assert "resté affiché" in c.crawl_identite_confirmee(resta, "lecteur")
    rien = SimpleNamespace(page=_PageWeb("http://app.local/", False), url_avant_connexion="http://app.local/",
                           connexion_soumise=False)
    assert "aucun formulaire" in c.crawl_identite_confirmee(rien, "lecteur"), "un visiteur anonyme n'est pas ce compte"
    entre = SimpleNamespace(page=_PageWeb("http://app.local/accueil", False), url_avant_connexion="http://app.local/login",
                            connexion_soumise=True)
    assert c.crawl_identite_confirmee(entre, "lecteur") == ""
    # Revue (bloquant) : un refus redirigé vers `/login?error` — l'adresse change, le mot de passe est encore là.
    redirige = SimpleNamespace(page=_PageWeb("http://app.local/login?error", True), url_avant_connexion="http://app.local/login",
                               connexion_soumise=True)
    assert "resté affiché" in c.crawl_identite_confirmee(redirige, "lecteur")
    # Même adresse, mot de passe disparu (formulaire réaffiché ailleurs, ou SPA) : rien n'est prouvé, refusé.
    meme_adresse = SimpleNamespace(page=_PageWeb("http://app.local/login#ok", False), url_avant_connexion="http://app.local/login",
                                   connexion_soumise=True)
    assert "resté affiché" in c.crawl_identite_confirmee(meme_adresse, "lecteur")
    # Seconde revue : un champ caché (inscription) AVANT le vrai mot de passe, encore visible après un refus redirigé.
    cache_devant = SimpleNamespace(page=_PageWeb("http://app.local/login?error", True, champs=[_Champ(False), _Champ(True)]),
                                   url_avant_connexion="http://app.local/login", connexion_soumise=True)
    assert "resté affiché" in c.crawl_identite_confirmee(cache_devant, "lecteur")


class _Reponse:
    def __init__(self, corps):
        self._corps = corps

    def json(self):
        return self._corps


def test_falsifiable_odoo_la_session_ouverte_doit_etre_celle_du_compte():
    """Mesuré sur le banc 17.0 le 2026-10-21 : `get_session_info` rend `result.username` ; sans session, une erreur."""
    from types import SimpleNamespace

    from testpilot.connectors.odoo import OdooConnector

    c = OdooConnector("http://odoo:8069", "banc", "admin", "pw")
    page = lambda corps: SimpleNamespace(page=SimpleNamespace(request=SimpleNamespace(post=lambda *a, **k: _Reponse(corps))))  # noqa: E731
    assert c.crawl_identite_confirmee(page({"result": {"username": "banc_commercial"}}), "BANC_commercial") == ""
    assert "n'a pas ouvert la session" in c.crawl_identite_confirmee(page({"result": {"username": "admin"}}), "banc_commercial")
    assert "n'a pas ouvert la session" in c.crawl_identite_confirmee(
        page({"error": {"message": "Odoo Session Expired"}}), "banc_commercial")


def test_un_connecteur_qui_ne_sait_pas_verifier_refuse():
    from testpilot.connectors.base import Connector

    assert Connector.crawl_identite_confirmee(None, None, "x"), "on n'affirme jamais une identité qu'on ne sait pas vérifier"


def test_falsifiable_odoo_les_menus_visibles_viennent_de_load_menus_et_illisibles_valent_inconnu():
    """Mesuré sur le banc (2026-10-21) : `load_menus` est lisible par tout compte et déjà filtré par ses droits — à la
    différence de `discover_menus`, qui rendait `[]` pour un compte non administrateur."""
    from types import SimpleNamespace

    from testpilot.connectors.odoo import OdooConnector

    menus = {"root": {"id": "root", "name": "root", "children": [1]},
             "1": {"id": 1, "name": "Ventes", "children": [2]},
             "2": {"id": 2, "name": "Commandes", "children": [], "actionModel": "ir.actions.act_window", "actionID": 9}}
    c = OdooConnector("http://odoo:8069", "banc", "admin", "pw")
    page = lambda corps: SimpleNamespace(request=SimpleNamespace(get=lambda *a, **k: _Reponse(corps)))  # noqa: E731
    assert c.menus_visibles(page(menus)) == [{"cle": "chemin:Ventes", "chemin": "Ventes"},
                                             {"cle": "chemin:Ventes / Commandes", "chemin": "Ventes / Commandes"}]
    menus["2"]["xmlid"] = "sale.menu_sale_order"
    assert {"cle": "sale.menu_sale_order", "chemin": "Ventes / Commandes"} in c.menus_visibles(page(menus))
    assert c.menus_visibles(page({"error": {"message": "Session Expired"}})) is None, "illisible : inconnu, jamais « aucun »"


def test_falsifiable_un_compte_arrete_en_route_est_incomplet_jamais_explore(conn, monkeypatch):
    """Revue (bloquant) : « Arrêter » pendant le passage de Lecteur — il sortait compté comme exploré, sans le mot incomplet."""
    appels = []
    monkeypatch.setattr(es, "_crawl", _faux_crawl(appels, arreter_apres="lecteur"))
    pid, (lecteur, _) = _projet(conn)
    job = _explorer(conn, pid)
    etat = es.etat_des_comptes(conn, _projet_dict(conn, pid))["par_compte"]
    assert etat[lecteur] == {"libelle": "Lecteur", "statut": "incomplet", "message": "exploration incomplète (arrêtée)"}
    assert "1 compte(s) sur 2 exploré(s) dont 1 incomplet(s) en plus" in job["resume"]
    carte = es.charger_carte(conn, _projet_dict(conn, pid))
    from testpilot.generation import carte_des_comptes as cdc
    assert cdc.voit(carte, "Lecteur", "/comptabilite") is None, "arrêté : on ne sait pas, jamais « ne voit pas »"


def test_un_echec_en_cours_de_route_est_dit_en_francais_sans_detail_technique(conn, monkeypatch):
    def crawl(connexion, max_pages):
        if connexion["username"] == "lecteur":
            raise TimeoutError("Timeout 20000ms exceeded")
        return _faux_crawl([])(connexion, max_pages)
    monkeypatch.setattr(es, "_crawl", crawl)
    pid, (lecteur, _) = _projet(conn)
    _explorer(conn, pid)
    etat = es.etat_des_comptes(conn, _projet_dict(conn, pid))["par_compte"][lecteur]
    assert etat["statut"] == "echec" and "Timeout" not in etat["message"] and "échoué" in etat["message"]



def test_falsifiable_a77_la_remise_a_zero_avant_un_test_est_refusee_pendant_l_exploration(conn, monkeypatch):
    """Le chemin de tous les projets qui ont une adresse de remise à zéro (A72) : jamais une remise à zéro en pleine
    exploration — le test sort « bloqué » avec la raison."""
    from testpilot.guardrails import bac_a_sable

    vus = {}

    def crawl(connexion, max_pages):
        try:
            with bac_a_sable.execution_remise_a_zero(None, "http://app.local:8069/__reset"):
                vus["remise"] = "faite"
        except bac_a_sable.ApplicationOccupeeParExploration as exc:
            vus["remise"] = str(exc)
        return _faux_crawl([])(connexion, max_pages)

    monkeypatch.setattr(bac_a_sable, "remettre_a_zero_et_demarquer", lambda *a: vus.setdefault("appelee", True))
    monkeypatch.setattr(es, "_crawl", crawl)
    pid, _ = _projet(conn, comptes=())
    _explorer(conn, pid)
    assert "occupée par l'exploration" in vus["remise"] and "appelee" not in vus


def test_falsifiable_a77_une_exploration_qui_attend_bloque_deja_les_nouveaux_tests():
    """Revue : tant qu'elle attendait la fin des tests en cours, de nouveaux tests démarraient — une campagne pouvait la
    faire attendre jusqu'au bout. Dès qu'elle attend, un nouveau test est refusé ; elle démarre quand l'ancien finit."""
    import threading

    from testpilot.guardrails import bac_a_sable

    cle = "http://app.local:8069"
    en_cours, fin = threading.Event(), threading.Event()
    attente, demarree = threading.Event(), threading.Event()

    def test_en_cours():
        with bac_a_sable.execution_reelle(cle):
            en_cours.set()
            fin.wait(5)

    def exploration():
        with bac_a_sable.exploration(cle, en_attente=attente.set):
            demarree.set()

    t1 = threading.Thread(target=test_en_cours)
    t1.start()
    en_cours.wait(5)
    t2 = threading.Thread(target=exploration)
    t2.start()
    assert attente.wait(5) and not demarree.is_set()
    with pytest.raises(bac_a_sable.ApplicationOccupeeParExploration):
        with bac_a_sable.execution_reelle(cle):
            pass
    fin.set()
    t1.join(5)
    t2.join(5)
    assert demarree.is_set()
    with bac_a_sable.execution_reelle(cle):
        pass   # tout est libéré


def test_falsifiable_un_arret_avant_la_premiere_page_garde_la_carte_precedente(conn, monkeypatch):
    monkeypatch.setattr(es, "_crawl", _faux_crawl([]))
    pid, _ = _projet(conn, comptes=())
    _explorer(conn, pid)
    avant = domain_model.chemin_du_modele(pid).read_bytes()

    monkeypatch.setattr(es, "_crawl", lambda connexion, max_pages: {
        "pages": {"/web/login": _page("login")}, "transitions": {}, "onglets_internes": {}, "modeles_backoffice": [],
        "familles": {}, "_arretee": True, "_interrompue": False})
    job = _explorer(conn, pid)
    assert domain_model.chemin_du_modele(pid).read_bytes() == avant, "la carte complète n'est pas remplacée par 1 page"
    assert job["status"] == "done" and "carte précédente est gardée" in job["resume"]


def test_falsifiable_le_masquage_ne_touche_que_des_mots_entiers_cles_comprises():
    masque = es._masquer({"/profil/user": {"champs": [{"name": "username", "label": "Connecté : user"}]}}, ["user"])
    assert masque == {"/profil/•••": {"champs": [{"name": "username", "label": "Connecté : •••"}]}}
    garde = es._masquer({"/admin/users": {"t": "admin"}}, ["admin"], frozenset({"/admin/users"}))
    assert garde == {"/admin/users": {"t": "•••"}}, "une route que le principal voit aussi n'est jamais masquée"



def test_falsifiable_a84_une_exploration_arretee_ne_remplace_pas_une_carte_complete(conn, monkeypatch):
    monkeypatch.setattr(es, "_crawl", _faux_crawl([]))
    pid, _ = _projet(conn, comptes=())
    _explorer(conn, pid)
    avant = domain_model.chemin_du_modele(pid).read_bytes()

    monkeypatch.setattr(es, "_crawl", lambda connexion, max_pages: {
        "pages": {"/commandes": _page("client"), "/autre": _page()}, "transitions": {}, "onglets_internes": {},
        "modeles_backoffice": [], "familles": {}, "_arretee": True, "_interrompue": False})
    job = _explorer(conn, pid)
    assert domain_model.chemin_du_modele(pid).read_bytes() == avant, "la carte complète reste en place"
    assert "la carte du" in job["resume"] and "est gardée" in job["resume"]
    etat = es.etat(pid, _projet_dict(conn, pid), conn=conn)
    assert (etat["derniere_tentative"]["raison"], etat["derniere_tentative"]["pages"]) == ("arrêtée", 2)
    assert etat["incomplete"] == "", "la carte affichée est la complète"

    monkeypatch.setattr(es, "_crawl", _faux_crawl([]))
    _explorer(conn, pid)
    assert es.etat(pid, _projet_dict(conn, pid), conn=conn)["derniere_tentative"] == {}, "une carte réécrite efface l'avis"


def test_a84_sans_carte_precedente_ce_qui_a_ete_vu_est_garde_et_marque_incomplet(conn, monkeypatch):
    monkeypatch.setattr(es, "_crawl", lambda connexion, max_pages: {
        "pages": {"/commandes": _page("client"), "/autre": _page()}, "transitions": {}, "onglets_internes": {},
        "modeles_backoffice": [], "familles": {}, "_arretee": True, "_interrompue": False})
    pid, _ = _projet(conn, comptes=())
    _explorer(conn, pid)
    etat = es.etat(pid, _projet_dict(conn, pid), conn=conn)
    assert (etat["incomplete"], etat["incomplete_pages"], etat["derniere_tentative"]) == ("arrêtée", 2, {})
