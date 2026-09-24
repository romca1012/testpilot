"""Lot 04 — mode génération et projet du banc : les parties SANS LLM ni Odoo (résultats simulés, doublures).

Le mode génération n'est PAS exécuté pour de vrai dans le lot (coût LLM) : ces tests fixent ce qui peut l'être —
la lecture déterministe des specs, la réduction de `campagne.json` en indicateurs, l'idempotence du projet.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent


def _charger(nom):
    spec = importlib.util.spec_from_file_location(nom, RACINE / "scripts" / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


gen = _charger("banc_generation")
projet = _charger("banc_projet")


# ── Les specs → document métier, sans LLM ────────────────────────────────────────────────────

@pytest.mark.parametrize("chemin", sorted((RACINE / "specs" / "banc").glob("*.md")), ids=lambda p: p.stem)
def test_chaque_spec_du_banc_donne_un_document_metier_complet(chemin):
    metier = gen.metier_depuis_spec(chemin.read_text(encoding="utf-8"))

    assert metier["title"] and not metier["title"].startswith("Spécification")
    assert metier["steps"], "au moins une étape numérotée"
    assert all(not e[0].isdigit() for e in metier["steps"]), "la numérotation est retirée"
    assert metier["expected_result"]


def test_metier_depuis_spec_lit_le_titre_les_etapes_et_le_critere():
    texte = ("# Spécification — Confirmer un devis (banc de mesure Odoo)\n\n## Contexte technique\n\nInstance.\n\n"
             "## Besoin\n\nX\n\n## Parcours\n\n1. Créer.\n2. Confirmer.\n\n## Critère de réussite\n\nUn bon existe.\n")

    assert gen.metier_depuis_spec(texte) == {
        "title": "Confirmer un devis", "preconditions": "Instance.", "steps": ["Créer.", "Confirmer."],
        "expected_result": "Un bon existe."}


def test_une_spec_sans_parcours_ou_sans_critere_est_refusee():
    with pytest.raises(ValueError, match="parcours ou critère"):
        gen.metier_depuis_spec("# Spécification — T (banc de mesure Odoo)\n\n## Besoin\n\nX\n")
    with pytest.raises(ValueError, match="titre"):
        gen.metier_depuis_spec("rien")


# ── campagne.json → indicateurs ──────────────────────────────────────────────────────────────

def _essai(case_id, execution=None, functional=None, cout=0.4, erreur=None):
    r = {"case_id": case_id, "iteration": 1, "generation": {"success": True, "cost_usd": cout}}
    if execution:
        r["execution"] = {"execution_status": execution, "functional_status": functional}
    if erreur:
        r["generation_error"] = erreur
    return r


def test_les_statistiques_comptent_les_essais_lances_meme_ceux_dont_la_generation_echoue():
    rapports = [_essai(1, "success", "conforme"), _essai(2, "success", "non_conforme"),
                _essai(3, "technical_error", "indetermine"), _essai(4, "success", "indetermine"),
                _essai(5, erreur="LLM refusé", cout=0.0)]

    s = gen.statistiques_depuis_campagne(rapports)

    assert s["generes"] == 5
    assert s["sans_erreur_technique"] == 3      # 1, 2, 4 (le 5 n'a jamais été exécuté)
    assert s["verdict_exploitable"] == 2        # conforme + non_conforme seulement
    assert s["cout_total"] == pytest.approx(1.6) and s["nouveaux_cas"] == 5


def test_une_campagne_vide_donne_zero_essai_pas_un_indicateur_parfait():
    s = gen.statistiques_depuis_campagne([])

    assert s["generes"] == 0
    banc = _charger("banc_mesure")
    i = banc.calculer_indicateurs([], {"sain": {}}, s)
    assert i["I3"]["valeur"] is None and i["I4"]["valeur"] is None and i["I6"]["valeur"] is None


def test_les_observations_de_generation_portent_le_statut_de_lecture_ou_non_mesure():
    rapports = [_essai(1, "success", "conforme"), _essai(2, erreur="boom"),
                _essai(3, "success", "non_conforme")]

    obs = gen.observations_depuis_campagne(rapports, {1: "vente_livraison", 2: "vente_total", 3: "projet_tache"})

    assert [(o["cas"], o["statut"]) for o in obs] == [
        ("vente_livraison", "passed"), ("vente_total", None), ("projet_tache", "failed")]
    assert obs[1]["raison"] == "boom"


def test_le_mode_generation_exige_un_plafond_de_cout():
    banc = _charger("banc_mesure")

    with pytest.raises(SystemExit):
        banc.main(["--mode", "génération"])


# ── Le projet du banc ────────────────────────────────────────────────────────────────────────

@pytest.fixture
def conn(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet

    sys.path.insert(0, str(RACINE / "src"))
    from testpilot import config
    from testpilot.store.db import get_initialized_db

    # `config.SECRET_KEY` est lu à l'import : l'isoler ici, sinon la clé serait CRÉÉE dans le vrai `data/`.
    monkeypatch.setattr(config, "SECRET_KEY", Fernet.generate_key().decode())

    connexion = get_initialized_db(tmp_path / "t.db")
    yield connexion
    connexion.close()


def test_le_projet_du_banc_est_cree_une_seule_fois(conn):
    a = projet.assurer_le_projet(conn, "17.0", "http://127.0.0.1:18069")
    b = projet.assurer_le_projet(conn, "17.0", "http://127.0.0.1:18070")  # même projet, nouveau port

    assert a == b
    ligne = conn.execute("SELECT name, base_url, connector_type, database FROM project WHERE id=?", (a,)).fetchone()
    assert (ligne["name"], ligne["base_url"], ligne["connector_type"], ligne["database"]) == (
        "Banc Odoo 17.0", "http://127.0.0.1:18070", "odoo", "banc")
    assert conn.execute("SELECT COUNT(*) FROM project WHERE name='Banc Odoo 17.0'").fetchone()[0] == 1


def test_un_projet_par_version(conn):
    a = projet.assurer_le_projet(conn, "16.0", "http://127.0.0.1:18069")
    b = projet.assurer_le_projet(conn, "17.0", "http://127.0.0.1:18069")

    assert a != b


@pytest.mark.parametrize("url", ["https://client.example.com", "http://192.168.1.10:8069"])
def test_le_projet_du_banc_refuse_une_instance_non_locale(conn, url):
    with pytest.raises(SystemExit, match="LOCALE"):
        projet.assurer_le_projet(conn, "17.0", url)
    assert conn.execute("SELECT COUNT(*) FROM project").fetchone()[0] == 0


def test_le_mot_de_passe_du_projet_est_chiffre_en_base(conn):
    pid = projet.assurer_le_projet(conn, "17.0", "http://127.0.0.1:18069", mot_de_passe="admin")

    brut = conn.execute("SELECT password FROM project WHERE id=?", (pid,)).fetchone()["password"]

    assert brut and brut != "admin"
