"""`scripts/qualify_campaign_pilot.py::_verification_independante` — deux bugs trouvés lors du
pilote du 23/09/2026, sur les 6 essais réels (projet 12, staging Sapian) :

1. `time.mktime` interprétait `write_date` (déjà en UTC côté Odoo) comme une heure LOCALE — un
   décalage silencieux qui faisait échouer la comparaison même sur l'essai réellement réussi
   (`nouveaux: 0` alors que le Gherkin lui-même avait confirmé la création).
2. `search(model, [], limit=0)` ramenait TOUS les ids du modèle (37 955 tickets mesurés) avant de
   les lire un par un — cause du `TimeoutError` systématique sur `helpdesk.ticket` (3/3 essais).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.qualify_campaign_pilot import _verification_independante


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
