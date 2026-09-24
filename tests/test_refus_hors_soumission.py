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


def test_un_clic_qui_ne_change_que_le_fragment_declenche_toujours_le_controle():
    """Le back-office Odoo route tout son état applicatif par fragment (`/web#action=…`) — un
    changement de fragment seul n'est PAS une navigation vers une autre page."""
    page = _FauxPage(url_avant="https://x/web#action=206&view_type=kanban",
                     url_apres="https://x/web#action=180&view_type=form",
                     invalides=[{"nom": "name", "msg": "requis", "valeur": "", "manquant": True}])

    with pytest.raises(DonneeRefuseeError):
        click_button(page, "Nouveau")
