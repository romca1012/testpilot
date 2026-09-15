"""Étape 3.1 du plan de consolidation (audit « Le pari Mabl/Testim », 2026-09-15) —
`tenter_connexion_generique` ne supposait qu'un SEUL écran (identifiant + mot de passe ensemble).
De nombreuses applications SaaS modernes (Google, Microsoft…) demandent l'identifiant seul avant
de révéler le mot de passe sur un second écran ; sans ce schéma, la détection générique échouait
silencieusement sur ces applications (retour `False`, exploration/perception poursuivies SANS
connexion, sans le moindre signal disant pourquoi).

Preuve en conditions réelles : `tests/test_conformite_connecteur_web.py` pilote la fixture
« torture » (`tests/fixtures/torture_app/`, connexion à deux écrans) — ce fichier-ci verrouille la
LOGIQUE avec des pages factices (jamais un site réel dans une suite pytest unitaire).
"""

from __future__ import annotations

import pytest

from testpilot.connectors._web_helpers import (
    ConnexionGeneriqueImpossibleError,
    _ressemble_a_un_premier_ecran_de_connexion,
    tenter_connexion_generique,
)


class _FakeChamp:
    def __init__(self):
        self.rempli = None
        self.touche_pressee = None

    def fill(self, value, force=False):
        self.rempli = value

    def press(self, key):
        self.touche_pressee = key


class _PageDeuxEcrans:
    """Simule une connexion à DEUX écrans : le mot de passe n'apparaît qu'APRÈS la soumission de
    l'identifiant — le changement d'écran est déclenché par `wait_for_load_state`, le point où
    `tenter_connexion_generique` s'attend justement à ce que la navigation ait abouti.

    `mdp_sur_ecran_2` : `False` simule un SSO/2FA — l'écran suivant ne porte AUCUN mot de passe.
    """

    def __init__(self, *, mdp_sur_ecran_2: bool = True):
        self.identifiant = _FakeChamp()
        self.mdp = _FakeChamp()
        self._mdp_sur_ecran_2 = mdp_sur_ecran_2
        self._sur_ecran_2 = False
        self.url = "https://exemple.test/connexion"
        self.attentes_reseau = 0

    def query_selector(self, selector):
        if "password" in selector:
            return self.mdp if (self._sur_ecran_2 and self._mdp_sur_ecran_2) else None
        if "email" in selector or "text" in selector:
            return None if self._sur_ecran_2 else self.identifiant
        if "button" in selector or "submit" in selector:
            return object() if not self._sur_ecran_2 else None
        return None

    def query_selector_all(self, selector):
        if ("email" in selector or "text" in selector) and not self._sur_ecran_2:
            return [self.identifiant]
        return []

    def wait_for_load_state(self, *_a, **_kw):
        self.attentes_reseau += 1
        if self.identifiant.touche_pressee == "Enter" and not self._sur_ecran_2:
            self._sur_ecran_2 = True
            self.url = "https://exemple.test/connexion/mot-de-passe"


class _PageUnEcran:
    """Schéma HISTORIQUE (mot de passe et identifiant ensemble, sur la même page) — inchangé."""

    def __init__(self):
        self.identifiant = _FakeChamp()
        self.mdp = _FakeChamp()
        self.attentes_reseau = 0

    def query_selector(self, selector):
        if "password" in selector:
            return self.mdp
        if "email" in selector or "text" in selector:
            return self.identifiant
        return None

    def query_selector_all(self, selector):
        return [self.identifiant] if ("email" in selector or "text" in selector) else []

    def wait_for_load_state(self, *_a, **_kw):
        self.attentes_reseau += 1


# ── Le schéma à UN écran reste exactement celui d'avant cette étape ────────────

def test_le_schema_a_un_ecran_reste_inchange():
    page = _PageUnEcran()
    resultat = tenter_connexion_generique(page, "alice", "s3cret")

    assert resultat is True
    assert page.identifiant.rempli == "alice"
    assert page.mdp.rempli == "s3cret"
    assert page.attentes_reseau == 1  # une seule page, un seul palier réseau


# ── Le garde anti-faux-positif ───────────────────────────────────────────────

def test_une_page_avec_plusieurs_champs_texte_ne_ressemble_pas_a_un_premier_ecran():
    """Une page de contenu ordinaire (recherche + newsletter, disons) ne doit jamais être prise
    pour un premier écran de connexion — le pari serait trop coûteux s'il se trompait."""
    class _PageAvecDeuxChamps:
        def query_selector_all(self, selector):
            return [object(), object()] if "text" in selector else []

        def query_selector(self, selector):
            return object()  # un bouton existe, mais ça ne doit pas suffire

    assert _ressemble_a_un_premier_ecran_de_connexion(_PageAvecDeuxChamps()) is False


def test_un_champ_texte_seul_sans_aucun_bouton_ne_ressemble_pas_a_un_ecran_de_connexion():
    class _PageSansBouton:
        def query_selector_all(self, selector):
            return [object()] if "text" in selector else []

        def query_selector(self, _selector):
            return None

    assert _ressemble_a_un_premier_ecran_de_connexion(_PageSansBouton()) is False


def test_une_page_sans_aucun_champ_ne_tente_rien_comportement_historique():
    class _PageVide:
        def query_selector(self, _selector):
            return None

        def query_selector_all(self, _selector):
            return []

    resultat = tenter_connexion_generique(_PageVide(), "alice", "s3cret")

    assert resultat is False


# ── Le schéma à DEUX écrans (le cœur de l'étape 3.1) ─────────────────────────

def test_le_schema_a_deux_ecrans_aboutit():
    page = _PageDeuxEcrans(mdp_sur_ecran_2=True)

    resultat = tenter_connexion_generique(page, "alice", "s3cret")

    assert resultat is True
    assert page.identifiant.rempli == "alice"
    assert page.identifiant.touche_pressee == "Enter"
    assert page.mdp.rempli == "s3cret"
    assert page.mdp.touche_pressee == "Enter"
    assert page.attentes_reseau == 2  # deux écrans, deux paliers réseau


def test_le_schema_a_deux_ecrans_leve_une_erreur_DISTINCTE_si_ni_l_un_ni_l_autre_ne_matche():
    """SSO/2FA : l'écran suivant ne porte AUCUN mot de passe — ⚠️ LE cas que cette étape corrige.
    Avant ce correctif, `tenter_connexion_generique` rendait silencieusement `False` (ou pire,
    plantait plus loin sur `None.fill(...)`) — ici, une classe DÉDIÉE et un message explicite."""
    page = _PageDeuxEcrans(mdp_sur_ecran_2=False)

    with pytest.raises(ConnexionGeneriqueImpossibleError, match="SSO"):
        tenter_connexion_generique(page, "alice", "s3cret")

    # L'identifiant a bien été soumis (la tentative a eu lieu) — seul l'écran suivant a déçu.
    assert page.identifiant.rempli == "alice"


def test_un_connector_type_sans_identifiant_ni_mot_de_passe_ne_tente_toujours_rien():
    """Comportement HISTORIQUE inchangé, schéma à deux écrans compris : rien à saisir, on
    n'invente jamais une tentative de connexion."""
    page = _PageDeuxEcrans()

    resultat = tenter_connexion_generique(page, "", "")

    assert resultat is False
    assert page.identifiant.rempli is None
