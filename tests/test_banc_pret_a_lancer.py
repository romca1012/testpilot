"""Étape 3 du plan unique : le banc mesure si le produit aurait livré chaque test PRÊT À LANCER — avec le calcul du produit
(`lint_warnings_for_version`), dans la base jetable du banc seulement, sans appel à l'IA."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from testpilot import config

# Même chargement que `test_banc_agents.py` : le script n'est pas un paquet.
RACINE = Path(__file__).resolve().parent.parent
if "banc_agents" in sys.modules:
    banc_agents = sys.modules["banc_agents"]
else:
    _spec = importlib.util.spec_from_file_location("banc_agents", RACINE / "scripts" / "banc_agents.py")
    banc_agents = importlib.util.module_from_spec(_spec)
    sys.modules["banc_agents"] = banc_agents
    _spec.loader.exec_module(banc_agents)

FEATURE = ('# language: fr\nFonctionnalité: F\n  Scénario: S\n    Soit j\'ouvre la page "/acces"\n'
           '    Quand je renseigne le champ "age" avec la valeur "17"\n')
SANS_SAISIE = "# language: fr\nFonctionnalité: F\n  Scénario: S\n    Soit j'ouvre la page \"/acces\"\n"


@pytest.fixture
def cas(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "testpilot.db")
    from testpilot.store.db import get_initialized_db
    from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo

    conn = get_initialized_db()
    pid = ProjectRepo(conn).create(name="Banc", connector_type="web", base_url="http://127.0.0.1:9")
    mid = ModuleRepo(conn).create(project_id=pid, name="banc")
    cid = CaseRepo(conn).create_manual(module_id=mid, title="Accès", preconditions="", test_steps=json.dumps(["x"]),
                                       expected_result="Refusé", author="banc-agents")
    conn.close()
    return cid, tmp_path


def _gen(feature, preuves=()):
    return {"feature_content": feature, "steps_content": "", "observation_evidence": list(preuves),
            "verified_fields": {}, "generation_provenance": {}}


def test_falsifiable_un_champ_sans_preuve_n_est_pas_pret_a_lancer(cas):
    cid, dossier = cas
    pret, avis = banc_agents.evaluer_pret_a_lancer(cid, _gen(FEATURE), dossier)
    assert pret is False and "champ_ui_non_verifie" in avis


def test_un_test_sans_point_de_vigilance_est_pret_a_lancer(cas):
    cid, dossier = cas
    assert banc_agents.evaluer_pret_a_lancer(cid, _gen(SANS_SAISIE), dossier) == (True, [])


def test_falsifiable_la_mesure_n_ouvre_jamais_une_base_hors_des_donnees_jetables(cas, tmp_path_factory):
    cid, _ = cas
    with pytest.raises(banc_agents.ConfigurationInvalide):
        banc_agents.evaluer_pret_a_lancer(cid, _gen(SANS_SAISIE), tmp_path_factory.mktemp("ailleurs"))


def test_falsifiable_la_garde_passe_avant_toute_ouverture_de_la_base(tmp_path, monkeypatch):
    """Revue (4) : reproduit l'incident — la base visée n'existe pas encore et se trouve hors du dossier jetable. La garde
    doit lever AVANT `get_initialized_db`, qui l'aurait créée."""
    hors = tmp_path / "hors" / "testpilot.db"
    hors.parent.mkdir()
    monkeypatch.setattr(config, "DB_PATH", hors)
    with pytest.raises(banc_agents.ConfigurationInvalide):
        banc_agents.evaluer_pret_a_lancer(1, _gen(SANS_SAISIE), tmp_path / "jetable")
    assert not hors.exists(), "la base n'a pas été créée"


def _campagne(essais, observations):
    camp = banc_agents.Campagne(k=1, cas=sorted({e.cas for e in essais}), essais=essais, observations=observations,
                                essais_prevus=len(essais))
    return banc_agents._section_prets_a_lancer(camp, {"interrupteurs": {"TESTPILOT_CONTROLE_FIN_ECRITURE": False}})


def _essai(cas, *, genere=True, pret=None, avis=()):
    return banc_agents.EssaiConsigne(cas, 1, genere, "", 0.1, {}, pret_a_lancer=pret, avis_restants=list(avis))


def _obs(cas, variante, obtenu):
    attendu = "conforme" if variante == banc_agents.VARIANTE_SAINE else "non_conforme"
    return banc_agents.Observation(cas, variante, 1, attendu, obtenu)


def test_falsifiable_un_test_pret_qui_laisse_passer_un_defaut_est_compte():
    texte = "\n".join(_campagne([_essai("a", pret=True)], [_obs("a", "total_faux", "conforme")]))
    assert "faux verts parmi les prêts : **1**" in texte
    texte = "\n".join(_campagne([_essai("a", pret=False, avis=["champ_inconnu"])], [_obs("a", "total_faux", "conforme")]))
    assert "faux verts parmi les prêts : **0**" in texte, "un test bloqué n'aurait pas été lancé"


def test_falsifiable_le_taux_compte_les_generations_echouees_et_les_mesures_impossibles():
    texte = "\n".join(_campagne([_essai("a", pret=True), _essai("b", genere=False),
                                 _essai("c", pret=None, avis=["mesure impossible : OperationalError"])], []))
    assert "1/3" in texte, "18/18 au lieu de 18/22 : jamais"
    assert "générations échouées : 1" in texte and "mesures impossibles : 1" in texte
    assert "borne BASSE" in texte, "contrôle éteint : le biais est dit"


def test_sans_cette_mesure_le_rapport_ne_change_pas():
    assert _campagne([_essai("a")], []) == []


def test_falsifiable_une_isolation_cassee_arrete_la_campagne(tmp_path, monkeypatch):
    """Revue (2) : la garde lève dans la génération réelle — la campagne s'arrête, elle ne continue pas en payant avec un
    « non mesuré »."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "hors" / "testpilot.db")

    class _App:
        def reinitialiser(self, defauts):
            pass

    class _Processus:
        returncode = 0

    def lancer(commande, **kw):
        sortie = commande[commande.index("--out") + 1]
        dossier = tmp_path / ".local-preview" / "qualification" / sortie
        dossier.mkdir(parents=True)
        (dossier / "campagne.json").write_text(json.dumps([{"generation": {
            "module_name": "m", "feature_content": SANS_SAISIE, "steps_content": "x = 1", "success": True,
            "dry_run_passed": True, "cost_usd": 0.1}}]), encoding="utf-8")
        return _Processus()

    generateur = banc_agents.GenerateurReel(_App(), {"a": 1}, 1, "http://127.0.0.1:1", tmp_path / "jetable", "cle",
                                            lambda: 1.0, lancer=lancer, racine=tmp_path)
    with pytest.raises(banc_agents.ConfigurationInvalide):
        generateur("a", 1)
