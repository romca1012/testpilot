"""Étape 2 du plan unique (A61, A67, porteur 2026-10-20) — les fausses alertes « champ sans preuve » qui laissaient un cas
« à relire » alors que la preuve d'écran était là. Chaque correction a sa paire : le cas qui ne doit plus être signalé, et
le cas voisin qui doit TOUJOURS l'être (un assouplissement ne vaut que s'il garde la garde).

Pire cas de chaque assouplissement (A64) : le champ manque sur la page atteinte, la saisie échoue — erreur technique, jamais
un « conforme ».
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from testpilot import config
from testpilot.generation import gherkin_mots_cles as mots
from testpilot.generation.evidence import contextual_warnings, page_identity

MAINTENANT = datetime.now(timezone.utc)


def _preuve(resource, *, champ="age", quand=MAINTENANT, cible="c1"):
    return {"source": "ui", "resource": resource, "observed_at": quand.isoformat(), "target_sha256": cible,
            "fields": [{"name": champ, "visible": True}]}


def _kinds(feature, preuves, base="http://127.0.0.1:8095", **kw):
    return [a["line"] for a in contextual_warnings(feature, preuves, target_sha256="c1", base_url=base, **kw)]


def _feature(*etapes, mot="Scénario"):
    return "# language: fr\nFonctionnalité: F\n  " + mot + ": S\n" + "".join(f"    {e}\n" for e in etapes)


SAISIE = 'Quand je renseigne le champ "age" avec la valeur "17"'


# ── 2. Adresse de projet avec un chemin ─────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_une_adresse_de_projet_avec_un_chemin_se_resout_comme_a_l_execution():
    base = "http://h.test/app"
    feature = _feature('Soit j\'ouvre la page "/acces"', SAISIE)
    assert _kinds(feature, [_preuve("http://h.test/app/acces")], base=base) == [], "vue sur la vraie page ouverte"
    assert _kinds(feature, [_preuve("http://h.test/acces")], base=base) == [5], "une AUTRE page : toujours signalée"


def test_la_resolution_est_celle_du_harnais():
    import sys
    sys.path.insert(0, str(config.BEHAVE_RUNTIME_DIR / "steps_library"))
    import _base_helpers as h

    for base in ("http://h.test/app", "http://h.test/app/", "http://h.test"):
        for chemin in ("/acces", "acces", "/acces?x=1"):
            assert page_identity(chemin, base) == page_identity(h.url_dans_l_application(base, chemin)), (base, chemin)


# ── 3. L'âge d'une preuve se mesure à l'écriture du test ────────────────────────────────────────────────────────────────

def test_falsifiable_l_age_d_une_preuve_se_mesure_a_l_ecriture_du_test():
    feature = _feature('Soit j\'ouvre la page "/acces"', SAISIE)
    ecrit_le = MAINTENANT - timedelta(days=3)
    recente = _preuve("http://127.0.0.1:8095/acces", quand=ecrit_le - timedelta(hours=1))
    perimee = _preuve("http://127.0.0.1:8095/acces", quand=ecrit_le - timedelta(hours=30))
    assert _kinds(feature, [recente], reference_time=ecrit_le) == [], "trois jours après : rien n'a changé"
    assert _kinds(feature, [perimee], reference_time=ecrit_le) == [5], "déjà périmée quand le test a été écrit"
    assert _kinds(feature, [recente]) == [5], "sans date d'écriture : mesurée maintenant (ancien comportement)"


def test_falsifiable_la_relecture_du_cas_mesure_l_age_a_l_ecriture(tmp_path, monkeypatch):
    """Câblage : `lint_warnings_for_version` passe la date de la version qui a ÉCRIT le test."""
    from testpilot.api.services import generation_service as gs
    from testpilot.generation.provenance import target_fingerprint

    projet = {"id": 3, "base_url": "http://127.0.0.1:8095", "connector_type": "web"}

    class _Projets:
        def __init__(self, conn):
            pass

        def get(self, _id):
            return projet

    monkeypatch.setattr("testpilot.store.repositories.ProjectRepo", _Projets)
    monkeypatch.setattr("testpilot.generation.domain_model.charger_modele", lambda p: None)
    ecrit_le = MAINTENANT - timedelta(days=3)
    preuve = _preuve("http://127.0.0.1:8095/acces", quand=ecrit_le - timedelta(hours=1), cible=target_fingerprint(projet))
    version = {"id": 1, "title": "Accès", "steps_content": "", "created_by": "ia", "created_at": ecrit_le.isoformat(),
               "feature_content": _feature('Soit j\'ouvre la page "/acces"', SAISIE),
               "observation_evidence": json.dumps([preuve])}
    avis = [w["kind"] for w in gs.lint_warnings_for_version(None, {"project_id": 3, "title": "Accès"}, [version], 1)]
    assert "champ_ui_non_verifie" not in avis


# ── 4. Une page quittée par un clic ─────────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_apres_un_clic_la_page_nommee_avant_n_est_plus_la_page_courante():
    preuve = [_preuve("http://127.0.0.1:8095/acces")]
    clic = _feature('Soit j\'ouvre la page "/"', 'Et je clique sur le bouton "Contrôle d\'accès"', SAISIE)
    sans_clic = _feature('Soit j\'ouvre la page "/"', SAISIE)
    assert _kinds(clic, preuve) == [], "arrivé par un clic : page inconnue, le champ a été vu (A64)"
    assert _kinds(sans_clic, preuve) == [5], "resté sur « / » : le champ n'y a pas été vu"


# ── 5. `Exemple:` est un scénario ───────────────────────────────────────────────────────────────────────────────────────

def test_les_mots_cles_viennent_de_behave():
    assert mots.DEBUT_SCENARIO.match("  Exemple: un cas")
    assert mots.DEBUT_SCENARIO.match("  Plan du scénario: p")
    assert not mots.DEBUT_SCENARIO.match("    Exemples:"), "le tableau d'un plan n'ouvre pas un scénario"
    assert mots.DEBUT_CONTEXTE.match("  Contexte:") and mots.DEBUT_REGLE.match("  Règle: r")


def test_falsifiable_la_page_ne_passe_pas_d_un_exemple_a_l_autre():
    deux = ("# language: fr\nFonctionnalité: F\n  Exemple: S1\n    Soit j'ouvre la page \"/clients\"\n"
            f"    {SAISIE}\n  Exemple: S2\n    {SAISIE}\n")
    assert _kinds(deux, [_preuve("http://127.0.0.1:8095/acces")]) == [5], \
        "S1 (sur /clients) signalé ; S2 ne connaît pas sa page — elle n'est pas celle de S1"


# ── 7a. Une connexion par compte nommé ──────────────────────────────────────────────────────────────────────────────────

def test_falsifiable_une_connexion_quitte_la_page_du_contexte():
    contexte = "# language: fr\nFonctionnalité: F\n  Contexte:\n    Soit j'ouvre la page \"/clients\"\n"
    connecte = contexte + f"  Scénario: S\n    Soit je me connecte en tant que \"gestionnaire\"\n    {SAISIE}\n"
    reste = contexte + f"  Scénario: S\n    {SAISIE}\n"
    preuve = [_preuve("http://127.0.0.1:8095/acces")]
    assert _kinds(connecte, preuve) == [], "un nouveau navigateur : la page du Contexte n'est plus là"
    assert _kinds(reste, preuve) == [6], "resté sur la page du Contexte"
