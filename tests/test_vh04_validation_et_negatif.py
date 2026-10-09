"""Lot VH-04, étape 4 (audit V7) — « une erreur de validation est affichée » et « … n'a pas augmenté » prouvent quelque chose.

- Erreur de validation : un lien « Supprimer » stylé en rouge, l'astérisque rouge d'un champ obligatoire ou un menu ne sont pas
  un message d'erreur (avant : « n'importe quel élément rouge ou `role=alert` » suffisait). Prouvé sur un vrai Chromium.
- Scénario négatif : « rien n'a été créé » n'est un refus que si quelque chose a été SOUMIS (requête d'envoi après le relevé,
  ou refus du navigateur). Sinon `RefusNonExpliqueError` → `indetermine`, jamais `conforme`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))
import _base_helpers as H  # noqa: E402

# ── Erreur de validation, sur un vrai Chromium ───────────────────────────────────────────────────────────

_FORMULAIRE = """<form><label>Nom <span class="text-red-600">*</span></label><input name="nom">
<a href="#" class="text-red-600">Supprimer</a> <button class="bg-red-600">Annuler</button></form>
<nav><span class="text-red-500">3 alertes</span></nav>{erreur}"""


@pytest.fixture(scope="module")
def navigateur():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        nav = p.chromium.launch()
        yield nav
        nav.close()


def _page(navigateur, erreur: str):
    page = navigateur.new_page()
    page.set_content(_FORMULAIRE.format(erreur=erreur))
    return page


@pytest.fixture(autouse=True)
def _delai_court(monkeypatch):
    monkeypatch.setattr(H, "COUNT_SETTLE_TIMEOUT", 0.5)


@pytest.mark.conformance
def test_falsifiable_un_element_rouge_qui_n_est_pas_une_erreur_ne_suffit_pas(navigateur):
    page = _page(navigateur, "")
    try:
        with pytest.raises(AssertionError, match="Aucune erreur de validation"):
            H.validation_error_inline(page)
    finally:
        page.close()


@pytest.mark.conformance
@pytest.mark.parametrize("erreur", [
    '<p class="text-red-600">Le nom est obligatoire</p>',
    '<div role="alert">Identifiants invalides</div>',
    '<div class="flash error">Your username is invalid!<a class="close">×</a></div>',
])
def test_un_vrai_message_d_erreur_est_reconnu(navigateur, erreur):
    page = _page(navigateur, erreur)
    try:
        H.validation_error_inline(page)
    finally:
        page.close()


@pytest.mark.conformance
def test_un_champ_marque_invalide_est_reconnu(navigateur):
    page = _page(navigateur, '<input name="email" class="is-invalid">')
    try:
        H.validation_error_inline(page)
    finally:
        page.close()


# ── Scénario négatif : la soumission doit être observée ──────────────────────────────────────────────────


class _Modele:
    def search_count(self, _domaine):
        return 10

    def with_context(self, **_kw):
        return self

    def search(self, domaine=(), order=None, limit=None, **_kw):
        return [] if any(c[0] == "id" for c in domaine) else [42]


def _contexte(reponses):
    return SimpleNamespace(odoo=SimpleNamespace(env={"res.partner": _Modele()}), reponses_reseau=reponses,
                           page=SimpleNamespace(), _tp_sequence=5)


def test_falsifiable_rien_cree_sans_rien_soumis_n_est_pas_un_refus():
    ctx = _contexte([{"n": 3, "methode": "POST", "url": "/avant", "statut": 200}])  # avant le relevé : ne compte pas
    H.memorize_record_count(ctx, "res.partner")

    with pytest.raises(H.RefusNonExpliqueError, match="aucune soumission"):
        H.check_count_not_increased(ctx, "res.partner")


def test_rien_cree_apres_une_soumission_est_un_refus():
    ctx = _contexte([])
    H.memorize_record_count(ctx, "res.partner")
    ctx.reponses_reseau.append({"n": 6, "methode": "POST", "url": "/contact", "statut": 200})

    H.check_count_not_increased(ctx, "res.partner")


def test_un_refus_du_navigateur_vaut_soumission_tentee():
    ctx = _contexte([])
    H.memorize_record_count(ctx, "res.partner")
    ctx.page._tp_refus_navigateur = True

    H.check_count_not_increased(ctx, "res.partner")


def test_une_lecture_seule_n_est_pas_une_soumission():
    ctx = _contexte([])
    H.memorize_record_count(ctx, "res.partner")
    ctx.reponses_reseau.append({"n": 6, "methode": "GET", "url": "/contact", "statut": 200})

    with pytest.raises(H.RefusNonExpliqueError):
        H.check_count_not_increased(ctx, "res.partner")
