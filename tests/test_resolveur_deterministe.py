"""Étape 2b du §2bis — le RÉSOLVEUR remplit le formulaire nominal avec des valeurs valides.

Preuve d'intégration SANS navigateur : un faux `context`/`page` (juste `.url` + `.project_id`),
`fill_field` mocké pour capturer ce qui est saisi, et l'annuaire RÉEL du projet 1. On vérifie la
propriété qui compte : le résolveur remplit TOUS les champs requis visibles — et EUX SEULS — avec
des valeurs que le navigateur accepterait (chaque motif satisfait). C'est « le déterministe
garantit la forme » démontré de bout en bout, là où le LLM échouait (re-mesure 2026-07-22).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from behave_runtime.steps_library import _base_helpers as bh
from testpilot.generation import domain_model

ANNUAIRE_REEL = Path("data/domain/projet-1.json")
ROUTE = "/desistement"                                   # trois champs à motif : bon stress
URL = "http://localhost:10017/desistement/123"           # URL concrète appariée à `/desistement/{id}`


class _FakePage:
    def __init__(self, url):
        self.url = url


class _FakeContext:
    def __init__(self, project_id, url):
        self.project_id = project_id
        self.page = _FakePage(url)


def _skip_sans_annuaire():
    if not ANNUAIRE_REEL.exists():
        pytest.skip("annuaire réel absent")


def _form_reel():
    modele = domain_model.charger_par_projet_id(1)
    formulaires = domain_model.formulaires_requis(modele, [URL])
    if not formulaires:
        pytest.skip(f"route {ROUTE} absente de l'annuaire réel")
    return formulaires[0]


def test_le_resolveur_remplit_tous_les_requis_visibles_avec_des_valeurs_valides(monkeypatch):
    _skip_sans_annuaire()
    saisi: dict[str, str] = {}
    monkeypatch.setattr(bh, "fill_field",
                        lambda page, name, value: saisi.__setitem__(name, value))

    ctx = _FakeContext(project_id=1, url=URL)
    bh.remplir_formulaire_valide(ctx, ROUTE)

    form = _form_reel()
    visibles = {c["name"] for c in form["requis"] if c.get("visible", True)}
    assert set(saisi) == visibles, "tous les champs requis VISIBLES, et eux seuls"

    for champ in form["requis"]:
        motif = (champ.get("contraintes") or {}).get("pattern")
        if motif and champ.get("visible", True):
            assert re.fullmatch(motif, saisi[champ["name"]]), (
                f"{champ['name']}={saisi[champ['name']]!r} viole son motif {motif}")

    assert ctx.saisie_resolveur == saisi, "la saisie est mémorisée pour la vérification par l'état"


def test_le_resolveur_n_ecrit_JAMAIS_dans_un_champ_cache(monkeypatch):
    """5ᵉ cause : un champ requis caché est injecté par le serveur — le remplir par l'interface
    est impossible (`TimeoutError`). Le résolveur doit les ignorer, pas les deviner."""
    _skip_sans_annuaire()
    caches = {c["name"] for c in _form_reel()["requis"] if not c.get("visible", True)}
    if not caches:
        pytest.skip("aucun champ caché sur cette route")

    saisi: dict[str, str] = {}
    monkeypatch.setattr(bh, "fill_field",
                        lambda page, name, value: saisi.__setitem__(name, value))
    bh.remplir_formulaire_valide(_FakeContext(1, URL), ROUTE)

    assert not (set(saisi) & caches), f"champs cachés remplis à tort : {set(saisi) & caches}"


def test_un_projet_sans_annuaire_echoue_clairement(monkeypatch):
    """Pas d'annuaire = pas de résolveur. On le DIT (message actionnable), on ne devine pas.
    ⚠️ `ResolveurIncompletError` (pas `AssertionError`) → verdict `indetermine`, jamais
    `non_conforme` : sans annuaire, le test n'a rien pu juger de l'application."""
    monkeypatch.setattr(domain_model, "charger_par_projet_id", lambda pid: None)
    with pytest.raises(bh.ResolveurIncompletError, match="aucun annuaire"):
        bh.remplir_formulaire_valide(_FakeContext(999, URL), ROUTE)
