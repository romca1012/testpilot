"""§F7 (2026-09-23) — un clic qui ne SOUMET rien ne doit jamais déclencher le diagnostic de refus.

Défaut mesuré en campagne réelle de validation du lot 01 (cas 95, projet Sapian portail,
23/09/2026, `docs/mesures/campagne-lot01-2026-09-23.md`) : `click_button` appelait
`verifier_soumission_non_bloquee` après N'IMPORTE QUEL clic — y compris un `<a href="/en/mutation
/67">` de navigation vers l'étape suivante d'un formulaire multi-écrans. Sur la page de
DESTINATION, tous les champs sont encore vides et donc « invalides » au sens HTML5 : le contrôle
accusait à tort le jeu de données du test alors qu'aucune soumission n'avait été tentée.

⚠️ **Pourquoi le CHEMIN d'URL, pas le type d'élément cliqué** (sondé en direct sur 3 cas réels
avant de choisir ce signal, jamais deviné) :
- le lien fautif du cas 95 est un `<a href="/en/mutation/67">` SANS rôle ARIA, HORS de tout
  `<form>` — change de chemin ;
- le vrai bouton « Envoyer » d'un formulaire portail Sapian (cas 97) est lui-même un
  `<a href="#" role="button">`, PAS un `<button type=submit>` — mais il ne change JAMAIS le
  chemin (seul le fragment `#` existe) ;
- le bouton d'enregistrement du back-office Odoo (OWL, cas 127/128 du lot 01) est un
  `<button type="button">` HORS de tout `<form>` — le back-office Odoo n'utilise AUCUN formulaire
  natif. Aucune règle basée sur la balise/le type/le rôle ARIA ne sépare proprement ces trois cas ;
  seul le changement de CHEMIN (hors fragment `#`, où le back-office Odoo route tout son état)
  les distingue correctement.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

from _base_helpers import (  # noqa: E402
    DonneeRefuseeError,
    _chemin_sans_fragment,
    _est_navigation,
    click_button,
)


# ── La fonction pure, isolée ───────────────────────────────────────────────────

@pytest.mark.parametrize("url,attendu", [
    ("https://x/en/servicemetiers", "https://x/en/servicemetiers"),
    ("https://x/en/mutation/67#section2", "https://x/en/mutation/67"),
    ("https://x/web#action=206&model=helpdesk.team&view_type=kanban", "https://x/web"),
])
def test_chemin_sans_fragment(url, attendu):
    assert _chemin_sans_fragment(url) == attendu


# ── `click_button` bout en bout, avec un faux Playwright minimal ─────────────

class _FauxLocator:
    def __init__(self, page):
        self._page = page

    @property
    def first(self):
        return self

    def click(self, timeout=None):
        self._page._au_clic()


class _FauxPage:
    """`url` change au clic si `url_apres` diffère de `url` initial — simule une VRAIE navigation
    (cas 95) ou son absence (cas 97, cas 127/128 : seul le fragment `#…` bouge, ou rien du tout)."""

    def __init__(self, url_avant: str, url_apres: str, invalides: list):
        self.url = url_avant
        self._url_apres = url_apres
        self._invalides = invalides

    def get_by_role(self, *_a, **_kw):
        return _FauxLocator(self)

    def locator(self, *_a, **_kw):
        return _FauxLocator(self)

    def _au_clic(self):
        self.url = self._url_apres

    def evaluate(self, *_a, **_kw):
        return self._invalides


def _champ_invalide_manquant(nom):
    return {"nom": nom, "valeur": "", "msg": "Please fill out this field.", "manquant": True}


def test_GARDE_un_clic_de_navigation_ne_declenche_pas_le_controle_de_soumission():
    """Reproduit exactement le cas 95 : le clic change de CHEMIN → aucune vérification sur la
    page de destination, quel que soit l'état de ses champs (tous vides, donc invalides)."""
    page = _FauxPage(url_avant="https://x/en/servicemetiers",
                     url_apres="https://x/en/mutation/67",
                     invalides=[_champ_invalide_manquant("partner_email"),
                               _champ_invalide_manquant("name")])

    click_button(page, "Demande de mutation")  # ne lève PAS


def test_un_clic_qui_reste_sur_la_meme_page_declenche_toujours_le_controle():
    """La borne, dans l'autre sens : un vrai refus sur la MÊME page (soumission AJAX d'un
    formulaire portail, ou sauvegarde back-office Odoo — aucun des deux ne change le chemin
    d'URL) doit continuer à lever `DonneeRefuseeError` exactement comme avant ce lot."""
    page = _FauxPage(url_avant="https://x/en/mutation/67", url_apres="https://x/en/mutation/67",
                     invalides=[{"nom": "code_client1", "msg": "format invalide", "valeur": "abc",
                                "manquant": False}])

    with pytest.raises(DonneeRefuseeError):
        click_button(page, "Envoyer")


# ── Odoo 16 / 17.0 : la navigation ne change QUE le fragment (angle mort levé le 2026-09-24) ──

_BASE = "https://x/web"


@pytest.mark.parametrize("avant,apres,navigation", [
    # chemin différent : navigation (cas 95)
    ("https://x/en/servicemetiers", "https://x/en/mutation/67", True),
    # chemin /odoo/… (≥ 17.2) : comportement conservé (le chemin change)
    ("https://x/odoo/action-180", "https://x/odoo/action-206", True),
    # clic de menu Odoo 16/17.0 : /web#action=A → /web#action=B
    (f"{_BASE}#action=206&model=helpdesk.team&view_type=kanban",
     f"{_BASE}#action=180&model=helpdesk.ticket&view_type=list", True),
    # changement de vue seul
    (f"{_BASE}#action=180&model=helpdesk.ticket&view_type=list",
     f"{_BASE}#action=180&model=helpdesk.ticket&view_type=form", True),
    # changement de menu seul
    (f"{_BASE}#menu_id=1&action=180&model=m&view_type=form",
     f"{_BASE}#menu_id=2&action=180&model=m&view_type=form", True),
    # SAUVEGARDE : même vue, seule la clé id apparaît → le contrôle DOIT s'exécuter
    (f"{_BASE}#model=x&view_type=form", f"{_BASE}#model=x&view_type=form&id=42", False),
    # SAUVEGARDE : `id` change (même model) → contrôle
    (f"{_BASE}#model=x&view_type=form&id=41", f"{_BASE}#model=x&view_type=form&id=42", False),
    # URL strictement identique (dialogue, AJAX portail) → contrôle
    (f"{_BASE}#action=1&model=x", f"{_BASE}#action=1&model=x", False),
    # `href="#"` portail : fragment vide → contrôle
    ("https://x/en/mutation/67", "https://x/en/mutation/67#", False),
    # ordre des clés sans importance
    (f"{_BASE}#model=x&action=1&cids=1", f"{_BASE}#action=1&cids=1&model=x", False),
])
def test_table_transition_url_controle(avant, apres, navigation):
    assert _est_navigation(avant, apres) is navigation


def test_clic_de_menu_odoo_par_fragment_ne_declenche_pas_le_controle():
    page = _FauxPage(url_avant=f"{_BASE}#action=206&model=helpdesk.team&view_type=kanban",
                     url_apres=f"{_BASE}#action=180&model=helpdesk.ticket&view_type=list",
                     invalides=[_champ_invalide_manquant("name")])

    click_button(page, "Tickets")  # ne lève PAS


def test_sauvegarde_odoo_par_fragment_declenche_le_controle():
    page = _FauxPage(url_avant=f"{_BASE}#model=helpdesk.ticket&view_type=form",
                     url_apres=f"{_BASE}#model=helpdesk.ticket&view_type=form&id=42",
                     invalides=[{"nom": "name", "msg": "requis", "valeur": "", "manquant": True}])

    with pytest.raises(DonneeRefuseeError):
        click_button(page, "Enregistrer")


def test_un_dialogue_sans_changement_d_url_ne_produit_pas_de_faux_refus():
    """Le clic ouvre une boîte de dialogue : l'URL ne bouge pas, le contrôle s'exécute, mais aucun
    `<form>` natif n'est invalide (le back-office n'en a pas) → rien à accuser."""
    page = _FauxPage(url_avant=f"{_BASE}#model=x&view_type=form&id=7",
                     url_apres=f"{_BASE}#model=x&view_type=form&id=7", invalides=[])

    click_button(page, "Confirmer")  # ne lève PAS
