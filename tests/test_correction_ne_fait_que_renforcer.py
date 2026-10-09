"""D30 (validée par le porteur le 2026-10-09) — une correction automatique n'est approuvée d'office que si elle RENFORCE.

Avant : la correction (un agent relit le test juste après la génération) était approuvée d'office dès qu'elle ne laissait plus
de point de vigilance (décision du 2026-09-16). Rien ne l'empêchait de supprimer une vérification réelle ou de changer une
valeur attendue d'un `Alors` : un faux `conforme` fabriqué sans qu'aucun humain le voie. Ici :
- réécrire une vérification CREUSE (constante, tautologie, rien de lu) en vraie vérification reste approuvé d'office ;
- toucher une vérification qui lisait déjà l'application, un `Alors`, un exemple, ou ajouter une nouvelle vérification
  laisse la version corrigée à relire, avec un point de vigilance qui le dit.
"""

from __future__ import annotations

import ast

import pytest

from testpilot import config
from testpilot.api.services import generation_service
from testpilot.generation import correction_agent
from testpilot.generation import gel_verifications as gel
from testpilot.generation.repair_diff import VERIFICATION_AFFAIBLIE
from testpilot.generation.tools.write import verifications_creuses
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, ReviewRepo, VersionRepo, ensure_default_module
from testpilot.verdict import review_gate

ENTETE = "from behave import then\nfrom _base_helpers import constater\n"


def _creuses(code: str) -> set[str]:
    arbre = ast.parse(code)
    ids = verifications_creuses(arbre)
    return {f.name for f in ast.walk(arbre) if isinstance(f, ast.FunctionDef) and id(f) in ids}


# ── Classement creuse / réelle ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("corps", [
    "    assert True\n",
    "    constater(True, 'x')\n",
    "    constater(montant == montant, 'x')\n",
    "    constater(montant == '12', 'x')\n",
    "    pass\n",
    "    try:\n        constater(context.page.title() == 'A', 'x')\n    except Exception:\n        pass\n",
])
def test_une_verification_qui_ne_prouve_rien_est_creuse(corps):
    code = ENTETE + "@then('v \"{montant}\"')\ndef v(context, montant):\n" + corps

    assert _creuses(code) == {"v"}


@pytest.mark.parametrize("corps", [
    "    constater(context.page.title() == montant, 'x')\n",
    "    assert context.page.locator('#t').inner_text() == montant\n",
    "    expect(context.page.locator('#t')).to_have_text(montant)\n",
    "    _verifier(context, montant)\n",
    "    constater(*args)\n",
])
def test_dans_le_doute_une_verification_est_reelle(corps):
    """Sens prudent : ce qu'on ne sait pas juger (expect, helper du fichier, arguments déballés) est réputé réel, donc gelé."""
    code = (ENTETE + "def _verifier(context, m):\n    constater(context.page.title() == m, 'x')\n\n"
            "@then('v \"{montant}\"')\ndef v(context, montant, *args):\n" + corps)

    assert _creuses(code) == set()


# ── Gel de la correction ──────────────────────────────────────────────────────────────────────────────────

STEPS = ENTETE + """
def _lire_total(page):
    return page.locator('#total').inner_text(timeout=5000)

@then('le total vaut "{montant}"')
def total(context, montant):
    constater(_lire_total(context.page) == montant, 'total')

@then('la page est prête')
def prete(context):
    assert True
"""


def _ecarts(apres: str) -> list[str]:
    return gel.steps_modifies(STEPS, apres, creuses=verifications_creuses)


def test_reecrire_une_verification_creuse_en_vraie_est_permis():
    assert _ecarts(STEPS.replace("    assert True\n", "    constater(context.page.locator('h1').is_visible(), 'prête')\n")) == []


@pytest.mark.parametrize("avant, apres", [
    ("constater(_lire_total(context.page) == montant, 'total')", "constater(_lire_total(context.page) != '', 'total')"),
    ("return page.locator('#total').inner_text(timeout=5000)", "return '129,51'"),
])
def test_falsifiable_affaiblir_une_verification_reelle_est_detecte(avant, apres):
    assert _ecarts(STEPS.replace(avant, apres))


def test_falsifiable_supprimer_une_verification_reelle_est_detecte():
    sans = STEPS.replace("@then('le total vaut \"{montant}\"')\ndef total(context, montant):\n"
                         "    constater(_lire_total(context.page) == montant, 'total')\n", "")

    assert any("disparu" in e for e in _ecarts(sans))


def test_falsifiable_ajouter_une_nouvelle_verification_est_detecte():
    """Une nouvelle définition placée avant l'ancienne l'emporterait dans Behave : jamais approuvée d'office."""
    ajout = STEPS.replace("@then('le total vaut", "@then('le total vaut \"{m}\" TTC')\ndef autre(context, m):\n"
                          "    constater(context.page.title() != '', 'x')\n\n@then('le total vaut", 1)

    assert any("nouvelle vérification" in e for e in _ecarts(ajout))


def test_sans_classement_le_gel_reste_total():
    """La réparation (sans `creuses`) garde le gel total du lot VH-03 : même une vérification creuse est gelée."""
    assert gel.steps_modifies(STEPS, STEPS.replace("assert True", "assert context.page.title()"))


# ── Bout en bout : l'approbation d'office ─────────────────────────────────────────────────────────────────

FEATURE = """# language: fr
Fonctionnalité: Panier
  Scénario: Total
    Quand je valide le panier
    Alors le total vaut "129,51"
"""


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    c = get_initialized_db(tmp_path / "d30.db")
    yield c
    c.close()


def _corriger(conn, monkeypatch, *, feature: str, steps: str) -> tuple[int, dict]:
    mid = ensure_default_module(conn, "m")
    cid = CaseRepo(conn).create(title="C", module_id=mid, feature_slug="c")
    vid = VersionRepo(conn).create(test_case_id=cid, spec_content="", spec_hash="h", feature_content=FEATURE,
                                   steps_content=STEPS)
    CaseRepo(conn).set_current_version(cid, vid)
    monkeypatch.setattr(correction_agent, "propose_correction", lambda **kw: correction_agent.CorrectionProposal(
        changed=True, feature_content=feature, steps_content=steps, summary="ok", cost_usd=0.0, stopped_reason="done"))

    generation_service._finaliser_version_generee(conn, cid, vid, module_name="c", dry_runner=object())

    courante = VersionRepo(conn).get(CaseRepo(conn).get(cid)["current_version_id"])
    assert courante["created_by"] == "correction-agent"
    return cid, courante


def _approuvee(conn, version) -> bool:
    return review_gate.evaluate_gate(ReviewRepo(conn), version["id"]).allowed


def test_une_correction_qui_renforce_est_approuvee_d_office(conn, monkeypatch):
    renforce = STEPS.replace("    assert True\n", "    constater(context.page.locator('h1').is_visible(), 'prête')\n")

    _, courante = _corriger(conn, monkeypatch, feature=FEATURE, steps=renforce)

    assert _approuvee(conn, courante)


def test_falsifiable_une_correction_qui_affaiblit_un_constat_reel_reste_a_relire(conn, monkeypatch):
    """Elle répare la vérification creuse (le point de vigilance d'origine disparaît) ET affaiblit le total au passage."""
    affaiblie = (STEPS.replace("    assert True\n", "    constater(context.page.locator('h1').is_visible(), 'prête')\n")
                 .replace("_lire_total(context.page) == montant", "_lire_total(context.page) != ''"))

    cid, courante = _corriger(conn, monkeypatch, feature=FEATURE, steps=affaiblie)

    assert not _approuvee(conn, courante)
    points = generation_service.lint_warnings_for_version(conn, CaseRepo(conn).get(cid),
                                                          VersionRepo(conn).list_for_case(cid), courante["id"])
    assert VERIFICATION_AFFAIBLIE in {p["kind"] for p in points}


def test_falsifiable_une_correction_qui_change_une_valeur_attendue_reste_a_relire(conn, monkeypatch):
    renforce = STEPS.replace("    assert True\n", "    constater(context.page.locator('h1').is_visible(), 'prête')\n")

    _, courante = _corriger(conn, monkeypatch, feature=FEATURE.replace("129,51", "130,81"), steps=renforce)

    assert not _approuvee(conn, courante)
