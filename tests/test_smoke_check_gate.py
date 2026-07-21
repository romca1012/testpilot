"""Le smoke-check remonte-t-il jusqu'au GATE, et sans jamais bloquer ? (étape 4, branchement).

Tests d'INTÉGRATION par la vraie route HTTP (`GET /api/cases/{id}`) : le module pur est déjà testé
(`test_smoke_check.py`), ce qui reste à prouver c'est le **câblage** — celui que le fix P0 a montré
qu'on peut oublier pendant des jours (`propose_fix` recevait `dry_runner=None`, et la promesse
était fausse sur tous les chemins).

Deux propriétés, indissociables :
  1. l'avertissement **arrive** au relecteur ;
  2. `allowed` n'est **jamais** touché — §6 du brief (l'agent a le droit d'explorer) et borne du
     principe 2 (une garde qui peut refuser un test légitime est détective).
"""

import json

import pytest
from fastapi.testclient import TestClient

from testpilot import config
from testpilot.api.app import app
from testpilot.api.deps import get_conn
from testpilot.generation import domain_model
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ModuleRepo, ProjectRepo, ReviewRepo, VersionRepo

# Extrait du modèle RÉEL (crawl du 2026-07-17, `scripts/crawl_domaine.py`).
MODELE = {
    "connector_type": "odoo",
    "mesure_le": "2026-07-17",
    "pages": {
        "/formulaire/{id}": {"champs": [
            {"name": "name", "tag": "input", "type": "text"},
            {"name": "types_demandes", "tag": "select", "options": [
                ["nouvel_entrant", "Demande de nouvel entrant"],
                ["remplacement_materiel", "Remplacement de matériel existant"]]},
        ]},
    },
}

_FEATURE_FAUTIF = (
    'Fonctionnalité: Demande\n'
    '  Scénario: [NOMINAL] Demande\n'
    '    Et le champ demande "types_demandes" est rempli avec "new"\n')
_FEATURE_PROPRE = _FEATURE_FAUTIF.replace('"new"', '"nouvel_entrant"')
_STEPS = 'from behave import when\n\n\n@when("je fais l\'action")\ndef step(context):\n    pass\n'


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gate.db")
    c = get_initialized_db(config.DB_PATH)
    app.dependency_overrides[get_conn] = lambda: c
    yield c
    app.dependency_overrides.clear()
    c.close()


@pytest.fixture
def modele_en_place(tmp_path, monkeypatch):
    """Le modèle vit dans `data/domain/{connecteur}.json` — on isole le dépôt réel."""
    dossier = tmp_path / "domain"
    dossier.mkdir()
    (dossier / "odoo.json").write_text(json.dumps(MODELE, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", dossier)
    domain_model._charger.cache_clear()
    yield dossier
    domain_model._charger.cache_clear()


def _cas(conn, *, feature, approuve=True):
    pid = ProjectRepo(conn).create(name="Portail Sapian", connector_type="odoo")
    mid = ModuleRepo(conn).create(project_id=pid, name="Demande", description="")
    cid = CaseRepo(conn).create(title="Cas", feature_slug="cas", module_id=mid)
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="s", spec_hash="h",
                                   feature_content=feature, steps_content=_STEPS)
    CaseRepo(conn).set_current_version(cid, vid)
    if approuve:
        ReviewRepo(conn).create(test_case_id=cid, version_id=vid, decision="approved",
                                reviewer="qa", repair_budget=2)
    return cid


# ── L'avertissement arrive au relecteur ───────────────────────────────────────

def test_la_valeur_inventee_remonte_jusqu_au_gate(conn, modele_en_place):
    """🔴 LE test du câblage : `0019` visible à l'écran, avant tout run.

    Échoue sur le code d'avant : `_smoke_check_domaine` n'était pas appelé, et le module pur —
    pourtant testé et vert — ne servait à personne. C'est exactement la forme du fix P0.
    """
    cid = _cas(conn, feature=_FEATURE_FAUTIF)

    gate = TestClient(app).get(f"/api/cases/{cid}").json()["gate"]
    kinds = [w["kind"] for w in gate["lint_warnings"]]

    assert "valeur_option_inexistante" in kinds, (
        f"le smoke-check ne remonte pas au gate : {gate['lint_warnings']}")
    avis = next(w for w in gate["lint_warnings"] if w["kind"] == "valeur_option_inexistante")
    assert avis["step"] == "types_demandes"
    # Il doit donner DE QUOI corriger, et dire d'où il tient l'information (le modèle vieillit).
    assert "nouvel_entrant" in avis["message"]
    assert "2026-07-17" in avis["message"]


def test_le_smoke_check_ne_BLOQUE_JAMAIS(conn, modele_en_place):
    """§6 du brief + borne du principe 2 : détectif, jamais bloquant.

    Le cas est approuvé et son Gherkin est fautif : `allowed` doit rester **vrai**. Un humain
    tranche — le faux positif est réel (champ dynamique, select peuplé en JS, scénario `[ERREUR]`
    qui vise volontairement un id invalide).
    """
    cid = _cas(conn, feature=_FEATURE_FAUTIF, approuve=True)

    gate = TestClient(app).get(f"/api/cases/{cid}").json()["gate"]

    assert gate["lint_warnings"], "mise en scène : il DOIT y avoir un avertissement"
    assert gate["allowed"] is True, (
        "le smoke-check a bloqué le gate : il retire à l'agent un droit que le §6 lui accorde")
    assert gate["needs_review"] is False


def test_un_gherkin_propre_ne_declenche_rien(conn, modele_en_place):
    """Anti-faux-positif de bout en bout : le bandeau doit rester muet sur un cas correct."""
    cid = _cas(conn, feature=_FEATURE_PROPRE)

    gate = TestClient(app).get(f"/api/cases/{cid}").json()["gate"]

    assert [w for w in gate["lint_warnings"] if w["kind"].startswith(("valeur_", "champ_"))] == []


# ── Le contrat de sortie, et l'absence de modèle ──────────────────────────────

def test_le_contrat_LintWarning_est_respecte(conn, modele_en_place):
    """Le gate fait `LintWarning(**w)` : une clé en trop casserait l'affichage du CAS ENTIER.

    Un module dont tout l'objet est d'informer sans nuire ne peut pas se permettre un 500 —
    d'où ce test plutôt qu'une confiance dans la relecture.
    """
    cid = _cas(conn, feature=_FEATURE_FAUTIF)

    reponse = TestClient(app).get(f"/api/cases/{cid}")

    assert reponse.status_code == 200
    for w in reponse.json()["gate"]["lint_warnings"]:
        assert set(w) == {"step", "line", "kind", "message"}


def test_sans_modele_le_gate_repond_quand_meme(conn, tmp_path, monkeypatch):
    """⚠️ Pas de modèle ⇒ le gate fonctionne, muet. Et son silence ne vaut PAS validation.

    Le modèle est optionnel par construction : un connecteur neuf n'en a pas encore. L'écran ne
    doit pas en souffrir — mais personne ne doit lire « aucun avertissement » comme « vérifié ».
    """
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", tmp_path / "vide")
    domain_model._charger.cache_clear()
    cid = _cas(conn, feature=_FEATURE_FAUTIF)

    reponse = TestClient(app).get(f"/api/cases/{cid}")

    assert reponse.status_code == 200
    gate = reponse.json()["gate"]
    assert [w for w in gate["lint_warnings"] if w["kind"] == "valeur_option_inexistante"] == []
    assert gate["allowed"] is True


def test_un_modele_illisible_ne_casse_pas_l_ecran(conn, tmp_path, monkeypatch):
    """Best-effort : un JSON corrompu se journalise, il ne fait pas tomber le cas."""
    dossier = tmp_path / "domain"
    dossier.mkdir()
    (dossier / "odoo.json").write_text("{ ceci n'est pas du JSON", encoding="utf-8")
    monkeypatch.setattr(domain_model, "DOMAIN_DIR", dossier)
    domain_model._charger.cache_clear()
    cid = _cas(conn, feature=_FEATURE_FAUTIF)

    assert TestClient(app).get(f"/api/cases/{cid}").status_code == 200


# ── Le modèle versionné ───────────────────────────────────────────────────────

def test_le_modele_odoo_est_bien_en_depot_et_lisible():
    """La source de vérité doit être VERSIONNÉE — sinon « revue par diff git » ne veut rien dire.

    ⚠️ Ce test a une raison d'être concrète : `.gitignore` contient `/data/*`, donc le modèle
    aurait été **ignoré** par défaut. L'exception (`!/data/domain/*.json`) est ce qui fait exister
    la revue humaine du graphe. Ce test garde le fichier ; un test ne peut pas garder la règle
    gitignore elle-même, mais son absence sauterait ici au prochain clone.
    """
    # ⚠️ Lu par son chemin LEGACY : depuis le rangement par projet, `charger_modele` prend un
    # projet et cherche `projet-{id}.json`. Le fichier de référence en dépôt reste `odoo.json`
    # tant que le projet réel n'a pas été ré-exploré — et c'est LUI que ce test garde
    # (la règle `.gitignore` qui le rend versionnable). Le rangement par projet a ses propres
    # tests dans `test_annuaire_par_projet.py`.
    import json as _json
    chemin = domain_model.chemin_legacy("odoo")
    modele = _json.loads(chemin.read_text(encoding="utf-8")) if chemin.exists() else None

    assert modele is not None, (
        "data/domain/odoo.json est absent : le smoke-check est muet en production")
    assert modele["mesure_le"], "un modèle sans date est une photo sans date — inexploitable"
    assert len(modele["pages"]) >= 30, "le modèle réel compte 38 routes (crawl du 2026-07-17)"
    # La provenance doit être dans le fichier : personne ne doit avoir à deviner d'où il sort.
    assert "crawl_domaine" in modele.get("methode", "")
    assert "back-office" in modele.get("perimetre", ""), (
        "le périmètre exclut le back-office : un lecteur doit le savoir sans lire la note 0021")
