"""Lot 07b-2 (C2) — la stratégie de connexion du compte principal.

`connectors/auth_strategie.py` (module pur) : validation de forme. `_base_helpers.authentifier_selon_la_strategie` /
`_verifier_ou_reconnecter_session` (harnais, sur doublures) : chaque échec produit un `PreconditionNonRemplieError`
(→ `blocked`), jamais un défaut applicatif présumé — et la reconnexion ne se tente jamais deux fois.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pyotp
import pytest

from testpilot.connectors import auth_strategie as auth

RACINE = Path(__file__).resolve().parent.parent


# ── Module pur ───────────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_les_quatre_valeurs_ont_un_libelle_francais():
    assert set(auth.LIBELLES) == set(auth.VALEURS)
    for libelle in auth.LIBELLES.values():
        assert libelle and libelle[0].isupper()


def test_une_strategie_inconnue_est_signalee():
    assert auth.erreurs("sso_invente", "", "") == [
        "stratégie de connexion « sso_invente » inconnue (attendu : formulaire, totp, session_injectee, aucune)"]


@pytest.mark.parametrize("secret", ["JBSWY3DPEHPK3PXP", "jbswy3dpehpk3pxp", "AAAA 2222"])
def test_un_secret_totp_base32_valide_ne_produit_aucune_erreur(secret):
    assert auth.erreurs("totp", secret, "") == []


@pytest.mark.parametrize("secret", ["pas-du-base32!", "01234", "café"])
def test_falsifiable_un_secret_totp_mal_forme_est_refuse(secret):
    assert auth.erreurs("totp", secret, "") != []


def test_un_secret_totp_vide_n_est_pas_une_erreur_de_forme():
    """Vide = pas encore renseigné (l'écran l'affiche vide, comme un mot de passe) — l'absence se verra à l'exécution (`blocked`),
    pas à la saisie."""
    assert auth.erreurs("totp", "", "") == []


def test_une_session_injectee_valide_ne_produit_aucune_erreur():
    assert auth.erreurs("session_injectee", "", json.dumps({"cookies": [], "origins": []})) == []


@pytest.mark.parametrize("brut", ["pas du json", "{}", '{"autre_chose": true}', "[1, 2, 3]"])
def test_falsifiable_une_session_injectee_illisible_ou_incoherente_est_refusee(brut):
    assert auth.erreurs("session_injectee", "", brut) != []
