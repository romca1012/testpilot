"""Étape 5 du plan unique (AV-8, V-AV2 validée le 2026-10-16) — l'IA qui RÉDIGE les cas emploie les mots exacts des écrans,
relevés par l'exploration (interrupteur `TESTPILOT_CAS_AUX_TERMES_DES_ECRANS`, éteint).

Gardé ici : éteint, le message est celui d'avant, octet pour octet ; allumé, les mots relevés (jamais un texte à chiffres,
qui porte une valeur) sont dans la partie STABLE du message (en cache, la même pour tous les cas d'une spécification), avec la
consigne que le résultat attendu vient de la spécification. Aucun appel au modèle de langage : des doublures.
"""

from __future__ import annotations

import pytest

from testpilot.generation import interrupteurs, metier_writer, pages_observees

MODELE = {"pages": {
    "/clients": {"titre": "Clients", "titres": ["Liste des clients"], "champs": [],
                 "actions": [{"label": "Nouveau client"}],
                 "liens": [{"text": "Accueil", "href": "/"}, {"text": "Dupont SARL", "href": "/clients/7"}],
                 "tableaux": [{"nom": "", "colonnes": ["Nom", "Ville"]}], "libelles": []},
    "/clients/nouveau": {"titre": "Nouveau client", "champs": [{"name": "nom", "label": "Raison sociale"},
                                                               {"name": "x", "label": "Caché", "visible": False}],
                         "actions": [{"label": "Enregistrer"}, {"label": "Nouveau client"}],
                         "liens": [{"text": "Accueil", "href": "/"}]},
    "/clients/7": {"titre": "Dupont SARL", "titres": ["Dupont SARL"], "champs": [], "actions": [],
                   "liens": [{"text": "Accueil", "href": "/"}], "libelles": ["Numéro de commande"]},
}}


def _plan():
    from testpilot.analysis.plan import TestPlan
    return TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[],
                    raw_spec="Créer un client.")


class _IA:
    def __init__(self):
        self.appels = []

    def call_json(self, **kw):
        self.appels.append(kw)
        return {"title": "Créer un client", "preconditions": "", "steps": ["Cliquer sur « Nouveau client »"],
                "expected_result": "Le client est créé", "depend_dun_autre_cas_du_groupe": False,
                "etat_a_creer_par_ce_cas": ""}


def test_falsifiable_termes_des_ecrans_sans_donnee_ni_element_cache_les_plus_frequents_d_abord():
    termes = pages_observees.termes_des_ecrans(MODELE)
    assert termes[:2] == ["Accueil", "Nouveau client"]   # le menu (3 pages) puis un bouton de deux pages
    assert {"Raison sociale", "Enregistrer", "Nom", "Ville", "Numéro de commande"} <= set(termes)
    # Revue : un lien de ligne et un titre de fiche sont des DONNÉES (« Dupont SARL ») ; ni l'un ni l'autre n'est montré.
    assert "Dupont SARL" not in termes and "Clients" not in termes and "Caché" not in termes
    assert pages_observees.termes_des_ecrans(None) == [] and pages_observees.termes_des_ecrans({}) == []


def test_falsifiable_sans_terme_le_message_est_celui_d_avant_octet_pour_octet():
    ia = _IA()
    metier_writer.propose_metier(_plan(), llm=ia)
    metier_writer.propose_metier(_plan(), llm=ia, termes=[])
    assert ia.appels[0]["cached_prefix"] == ia.appels[1]["cached_prefix"] == metier_writer._build_prompt(_plan())


def test_avec_termes_ils_sont_dans_la_partie_stable_avec_la_consigne():
    ia = _IA()
    metier_writer.propose_metier(_plan(), llm=ia, brief="le cas nominal", termes=["Nouveau client", "Enregistrer"])
    stable = ia.appels[0]["cached_prefix"]
    assert stable.startswith(metier_writer._build_prompt(_plan()))
    assert "« Nouveau client », « Enregistrer »" in stable
    assert "Le résultat attendu vient de la spécification, jamais de cette liste." in stable
    assert "Nouveau client" not in ia.appels[0]["user_content"]


@pytest.mark.parametrize("allume", [False, True])
def test_le_service_ne_les_transmet_que_l_interrupteur_allume(tmp_path, monkeypatch, allume):
    import json

    from testpilot import config
    from testpilot.analysis import spec_analyzer as sa
    from testpilot.api.services import generation_service
    from testpilot.generation import decoupage, domain_model
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ModuleRepo, ProjectRepo

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "t.db")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    # La cartographie a son propre dossier (fixé à l'import) : jamais le vrai `data/domain/` du dépôt.
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", tmp_path / "domain")
    conn = get_initialized_db(tmp_path / "t.db")
    pid = ProjectRepo(conn).create(name="P", connector_type="web", base_url="http://app.test")
    mid = ModuleRepo(conn).create(project_id=pid, name="M")
    chemin = domain_model.chemin_du_modele(pid)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(MODELE), encoding="utf-8")
    monkeypatch.setattr(sa.SpecAnalyzer, "analyze_spec_content", lambda self, slug, content: _plan())
    monkeypatch.setattr(decoupage, "propose_decoupage", lambda plan, **kw: [decoupage.StoryPlan(
        user_story="Clients", cases=[decoupage.CaseBrief(title="Créer un client", brief="b")])])
    vus = []

    def faux_metier(plan, **kw):
        vus.append(kw.get("termes"))
        return metier_writer.MetierDraft(title="Créer", preconditions="", steps=["Étape"], expected_result="Créé")
    monkeypatch.setattr(metier_writer, "propose_metier", faux_metier)
    if allume:
        monkeypatch.setenv(interrupteurs.ENV_CAS_AUX_TERMES_DES_ECRANS, "1")
    else:
        monkeypatch.delenv(interrupteurs.ENV_CAS_AUX_TERMES_DES_ECRANS, raising=False)

    job_id, params = generation_service.start_generation(conn, mid, spec_content="Une spec", title="T")
    generation_service.run_generation(job_id, **params)
    conn.close()

    assert vus == ([pages_observees.termes_des_ecrans(MODELE)] if allume else [None])
