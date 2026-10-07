"""`scripts/qualify_campaign_pilot.py::_verification_independante` — deux bugs trouvés lors du
pilote du 23/09/2026, sur les 6 essais réels (projet 12, staging Sapian) :

1. `time.mktime` interprétait `write_date` (déjà en UTC côté Odoo) comme une heure LOCALE — un
   décalage silencieux qui faisait échouer la comparaison même sur l'essai réellement réussi
   (`nouveaux: 0` alors que le Gherkin lui-même avait confirmé la création).
2. `search(model, [], limit=0)` ramenait TOUS les ids du modèle (37 955 tickets mesurés) avant de
   les lire un par un — cause du `TimeoutError` systématique sur `helpdesk.ticket` (3/3 essais).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.qualify_campaign_pilot import (
    _type_de_connecteur,
    _verification_independante,
    _verification_independante_du_connecteur,
)

_RACINE = Path(__file__).resolve().parent.parent


class _ConnecteurEspion:
    def __init__(self, ids_a_rendre):
        self._ids = ids_a_rendre
        self.appels_search = []

    def search(self, model, filters, limit=0):
        self.appels_search.append((model, filters, limit))
        return self._ids

    def read(self, model, ids, fields):
        raise AssertionError("plus jamais appelé : le filtre se fait côté serveur")


def test_le_filtre_est_applique_cote_serveur_jamais_tout_le_modele():
    connecteur = _ConnecteurEspion([101, 102])
    debut = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc).timestamp()

    resultat = _verification_independante(connecteur, "helpdesk.ticket", debut)

    assert resultat == {"ok": True, "nouveaux": 2, "erreur": ""}
    (model, filtres, limit), = connecteur.appels_search
    assert model == "helpdesk.ticket"
    assert filtres == [("write_date", ">=", "2026-09-23 11:59:55")]  # marge de 5s, en UTC
    assert limit == 50


def test_le_seuil_est_construit_en_UTC_explicite():
    """Le cœur du bug : un `write_date` Odoo est TOUJOURS en UTC — le seuil de comparaison doit
    l'être aussi, jamais dérivé d'une heure locale."""
    connecteur = _ConnecteurEspion([])
    debut = datetime(2026, 1, 1, 0, 0, 10, tzinfo=timezone.utc).timestamp()

    _verification_independante(connecteur, "survey.survey", debut)

    (_, filtres, _), = connecteur.appels_search
    _, _, seuil = filtres[0]
    assert seuil == "2026-01-01 00:00:05"


def test_aucun_nouvel_enregistrement_rend_zero_sans_erreur():
    connecteur = _ConnecteurEspion([])

    resultat = _verification_independante(connecteur, "survey.survey", datetime.now(
        tz=timezone.utc).timestamp())

    assert resultat == {"ok": True, "nouveaux": 0, "erreur": ""}


def test_une_erreur_reseau_est_rapportee_jamais_levee():
    class _ConnecteurEnPanne:
        def search(self, *a, **kw):
            raise TimeoutError("The read operation timed out")

    resultat = _verification_independante(_ConnecteurEnPanne(), "helpdesk.ticket",
                                          datetime.now(tz=timezone.utc).timestamp())

    assert resultat["ok"] is False
    assert "TimeoutError" in resultat["erreur"]


# ── Comptes secondaires transmis au run Behave (trouvé le 2026-09-30, mesure de clôture du lot 09) ─
#
# `verifier_connexion(project)` était appelée SANS comptes dans `main()` : les comptes secondaires
# enregistrés en base (D8, `project_account`) n'atteignaient jamais `TESTPILOT_COMPTES`, donc jamais
# le sous-processus Behave — le step « je me connecte en tant que » échouait en PRÉREQUIS MANQUANT
# même quand le compte existait réellement (9 des 15 cas du banc, aux DEUX mesures de clôture, avant
# et après avoir corrigé l'enregistrement en base). `main()` appelle désormais
# `verifier_connexion_du_projet(conn, project)` (runtime_env.py) : seul endroit autorisé à lire
# `pour_runtime` en dehors de `run_service.py` (règle structurelle D8,
# `tests/test_comptes_projet.py::test_structure_pour_runtime_n_est_appele_que_par_le_transport_vers_le_runtime`).

def test_falsifiable_les_comptes_secondaires_atteignent_testpilot_comptes(tmp_path, monkeypatch):
    import sys
    from cryptography.fernet import Fernet

    sys.path.insert(0, str(_RACINE / "src"))
    from testpilot import config
    from testpilot.connectors.runtime_env import verifier_connexion_du_projet
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectAccountRepo, ProjectRepo

    monkeypatch.setattr(config, "SECRET_KEY", Fernet.generate_key().decode())
    conn = get_initialized_db(tmp_path / "t.db")
    project_id = ProjectRepo(conn).create(
        name="Banc test", description="", connector_type="odoo", connector_version="16.0",
        base_url="http://127.0.0.1:18069", database="banc", username="admin", password="admin")
    ProjectAccountRepo(conn).create(project_id, label="banc_manager", username="banc_manager",
                                    password="banc_manager_test_2026", business_role="Stock")
    project = ProjectRepo(conn).get(project_id)

    env = verifier_connexion_du_projet(conn, project)  # l'appel que `main()` fait désormais

    assert "TESTPILOT_COMPTES" in env, "le compte secondaire enregistré doit atteindre l'environnement Behave"
    transmis = json.loads(env["TESTPILOT_COMPTES"])
    assert {c["label"] for c in transmis} == {"banc_manager"}
    assert next(c for c in transmis if c["label"] == "banc_manager")["password"] == "banc_manager_test_2026"


def test_falsifiable_omettre_comptes_reproduit_le_bug_d_origine(tmp_path, monkeypatch):
    """Le contre-essai : c'est exactement l'appel `verifier_connexion(project)` (sans comptes) que
    `main()` faisait avant ce correctif — la précondition manquante est silencieuse, pas une
    exception, d'où le bug passé inaperçu jusqu'à la mesure du 2026-09-30."""
    import sys
    from cryptography.fernet import Fernet

    sys.path.insert(0, str(_RACINE / "src"))
    from testpilot import config
    from testpilot.connectors.runtime_env import verifier_connexion
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import ProjectAccountRepo, ProjectRepo

    monkeypatch.setattr(config, "SECRET_KEY", Fernet.generate_key().decode())
    conn = get_initialized_db(tmp_path / "t.db")
    project_id = ProjectRepo(conn).create(
        name="Banc test", description="", connector_type="odoo", connector_version="16.0",
        base_url="http://127.0.0.1:18069", database="banc", username="admin", password="admin")
    ProjectAccountRepo(conn).create(project_id, label="banc_manager", username="banc_manager",
                                    password="banc_manager_test_2026", business_role="Stock")
    project = ProjectRepo(conn).get(project_id)

    env = verifier_connexion(project)  # bug d'origine : comptes jamais lus ni transmis

    assert "TESTPILOT_COMPTES" not in env


# ── Campagne généralisée au connecteur web (banc web, phase 1) ───────────────────────────────

def test_le_type_de_connecteur_suit_le_projet_et_retombe_sur_odoo_si_absent():
    """Avant : `'odoo'` codé en dur à trois endroits — une campagne sur un projet web aurait généré et
    jugé avec la bibliothèque Odoo, donc mesuré un chemin que ce projet n'emprunte pas."""
    assert _type_de_connecteur({"connector_type": "web"}) == "web"
    assert _type_de_connecteur({"connector_type": "WEB"}) == "web"
    assert _type_de_connecteur({"connector_type": "odoo"}) == "odoo"
    assert _type_de_connecteur({}) == "odoo"  # projet antérieur au multi-connecteurs
    assert _type_de_connecteur(None) == "odoo"


def test_web_la_verification_independante_est_non_applicable_jamais_zero_et_sans_rpc():
    """« Non mesuré » n'est pas « zéro » : un essai web ne doit JAMAIS afficher `nouveaux: 0` (qui
    se lirait « rien créé ») ni tenter un appel RPC Odoo."""
    class _ConnecteurInterdit:
        def search(self, *a, **kw):
            raise AssertionError("aucun appel RPC attendu pour un projet web")

    resultat = _verification_independante_du_connecteur(
        "web", _ConnecteurInterdit(), {"title": "Achat complet"}, 0.0)

    assert resultat["ok"] is None
    assert resultat["nouveaux"] is None
    assert "non applicable" in resultat["erreur"]


def test_odoo_la_verification_independante_reste_celle_d_avant():
    connecteur = _ConnecteurEspion([7])
    debut = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc).timestamp()

    resultat = _verification_independante_du_connecteur(
        "odoo", connecteur, {"title": "Créer un sondage"}, debut)

    assert resultat == {"ok": True, "nouveaux": 1, "erreur": ""}
    (model, _, _), = connecteur.appels_search
    assert model == "survey.survey"  # le choix du modèle selon le titre est inchangé
