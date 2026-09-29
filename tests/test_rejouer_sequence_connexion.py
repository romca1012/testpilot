"""`rejouer_sequence_connexion` — sous-lot D du lot « Enregistrement assisté du chemin de
connexion » (étape 8) : rejoue la séquence confirmée (sous-lot C) pour franchir un écran
intercalé avant le formulaire de connexion. Pages factices (jamais un site réel dans une suite
pytest unitaire) — la preuve avec un vrai Chromium est dans `test_login_recording_rejeu_reel.py`.
"""

from __future__ import annotations

import pytest

from testpilot.connectors._web_helpers import (
    SequenceConnexionObsoleteError,
    rejouer_sequence_connexion,
)


class _FakeLocator:
    def __init__(self, *, existe: bool = True, ambigu: bool = False):
        self._existe = existe
        self._ambigu = ambigu
        self.clique = False

    def click(self, timeout=None):
        if not self._existe:
            raise TimeoutError("élément introuvable dans le délai imparti")
        if self._ambigu:
            raise Exception("strict mode violation: locator resolved to 2 elements")
        self.clique = True


class _FakePage:
    """`get_by_role(role, name, exact=True)` rend le locator préparé pour ce couple, ou un locator
    absent. Exige `exact=True` (comme le code réel) — un appel sans, ou avec `exact=False`, est
    une erreur de PROGRAMMATION à faire échouer bruyamment ici, pas une divergence silencieuse.

    ⚠️ Un lookup par tuple exact, comme ici, ne reproduit PAS la sémantique réelle de Playwright
    (qui, même avec `exact=True`, ne matche l'ACCESSIBLE NAME complet qu'au caractère près, mais
    reste par ailleurs un moteur DOM réel) — c'est un choix délibéré pour tester l'ORDRE et le
    GARDE-FOU de cette fonction, pas le comportement de matching lui-même : la preuve que
    `exact=True` rejette bien un nom approchant-mais-différent est apportée par un vrai Chromium,
    voir `test_login_recording_rejeu_reel.py` (revue verdict-reviewer, 2026-09-29 : un test sur ce
    doublon exact n'aurait jamais pu détecter le bug corrigé ce jour-là)."""

    def __init__(self, resultats: dict[tuple[str, str], _FakeLocator]):
        self._resultats = resultats
        self.url = "https://exemple.test/pre-connexion"
        self.attente_reseau_appelee = False

    def get_by_role(self, role, name=None, exact=False):
        assert exact is True, "rejouer_sequence_connexion doit toujours appeler exact=True"
        return self._resultats.get((role, name), _FakeLocator(existe=False))

    def wait_for_load_state(self, state):
        self.attente_reseau_appelee = True


def test_sequence_vide_ne_fait_rien_et_rend_false():
    page = _FakePage({})

    assert rejouer_sequence_connexion(page, []) is False
    assert page.attente_reseau_appelee is False


def test_rejoue_chaque_etape_dans_l_ordre_et_rend_true():
    pays = _FakeLocator()
    continuer = _FakeLocator()
    page = _FakePage({("combobox", "Pays"): pays, ("button", "Continuer"): continuer})

    resultat = rejouer_sequence_connexion(
        page, [{"role": "combobox", "name": "Pays"}, {"role": "button", "name": "Continuer"}])

    assert resultat is True
    assert pays.clique is True and continuer.clique is True
    assert page.attente_reseau_appelee is True


def test_falsifiable_une_etape_introuvable_leve_avec_message_clair():
    """Preuve que le garde-fou mord : une étape enregistrée qui ne se retrouve plus arrête net,
    avec le rôle et le nom dans le message — jamais une tentative silencieuse de deviner autre
    chose (étape 8 de la consigne)."""
    page = _FakePage({("button", "Continuer"): _FakeLocator(existe=False)})

    with pytest.raises(SequenceConnexionObsoleteError, match="button.*Continuer"):
        rejouer_sequence_connexion(page, [{"role": "button", "name": "Continuer"}])


def test_falsifiable_une_etape_ambigue_leve_aussi():
    """Un élément qui matcherait maintenant PLUSIEURS correspondances (Playwright lève en mode
    strict par défaut) est traité comme obsolète, pas comme un choix silencieux du premier trouvé
    — même principe que l'ambiguïté déjà gérée par `accname.calculer` (sous-lot A)."""
    page = _FakePage({("button", "Continuer"): _FakeLocator(ambigu=True)})

    with pytest.raises(SequenceConnexionObsoleteError):
        rejouer_sequence_connexion(page, [{"role": "button", "name": "Continuer"}])


def test_falsifiable_une_etape_ulterieure_n_est_jamais_tentee_apres_un_echec():
    """Arrêt NET à la première étape en échec — ne tente jamais l'étape suivante (jamais un
    résultat partiel qui continuerait sur un état déjà incohérent)."""
    jamais_atteinte = _FakeLocator()
    page = _FakePage({
        ("button", "Continuer"): _FakeLocator(existe=False),
        ("button", "Suivant"): jamais_atteinte,
    })

    with pytest.raises(SequenceConnexionObsoleteError):
        rejouer_sequence_connexion(
            page, [{"role": "button", "name": "Continuer"}, {"role": "button", "name": "Suivant"}])

    assert jamais_atteinte.clique is False
