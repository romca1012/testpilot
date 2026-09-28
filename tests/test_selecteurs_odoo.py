"""Lot 08a (C7) — détection de version, table de sélecteurs par version, helpers d'attente/URL.

⚠️ Les CANDIDATS de la table ne sont PAS vérifiés sur un banc Odoo réel dans ce cloud (aucun
démon Docker disponible) — voir la docstring de `_selecteurs.py`. Ces tests verrouillent le
MÉCANISME (résolution par clé/version, repli, gabarits, formes d'URL) et l'accord d'acceptation du
lot (« chaque clé a une entrée pour chaque version de D9 »), pas l'exactitude des sélecteurs eux-mêmes.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_STEPS_LIB = RACINE / "behave_runtime" / "steps_library"


def _charger_selecteurs():
    sys.path.insert(0, str(_STEPS_LIB))
    sys.path.insert(0, str(_STEPS_LIB / "odoo"))
    import _selecteurs as mod
    return mod


# ── Détection de version ───────────────────────────────────────────────────────

def test_parser_version_lit_majeur_mineur():
    S = _charger_selecteurs()
    assert S.parser_version("17.0") == (17, 0)
    assert S.parser_version("16.0e") == (16, 0)
    assert S.parser_version("saas~17.4") == (17, 4)
    assert S.parser_version("18.0+e") == (18, 0)


def test_parser_version_illisible_rend_none_jamais_une_exception():
    S = _charger_selecteurs()
    assert S.parser_version("") is None
    assert S.parser_version(None) is None
    assert S.parser_version("version inconnue") is None


# ── Table de sélecteurs : accord d'acceptation du lot ─────────────────────────
#
# « Table de sélecteurs : un test vérifie que chaque clé a une entrée pour chaque version de D9 »
# (critère d'acceptation du lot 08a).

_CLES_ATTENDUES = (
    "bouton_action", "barre_etat_courante", "ligne_x2many_ajout", "ligne_x2many_cellule",
    "dialogue", "dialogue_bouton_principal", "notification_erreur", "indicateur_chargement",
    "fil_ariane", "recherche_facette", "enregistrer", "ignorer",
)


def test_chaque_cle_du_lot_a_une_entree_pour_chaque_version_de_d9():
    S = _charger_selecteurs()
    for cle in _CLES_ATTENDUES:
        assert cle in S._TABLE, f"clé manquante : {cle}"
        for version in S._VERSIONS_D9:
            candidats = S._TABLE[cle].get(version)
            assert candidats, f"{cle} n'a aucun candidat pour la version {version}"


def test_aucune_cle_n_a_de_candidat_vide():
    """Une entrée sans candidat casserait `click_first_actionable` en silence (liste vide)."""
    S = _charger_selecteurs()
    for cle, par_version in S._TABLE.items():
        for version, candidats in par_version.items():
            assert candidats, f"{cle}/{version} : liste de candidats vide"
            assert all(isinstance(c, str) and c.strip() for c in candidats)


# ── Résolution par clé/version ─────────────────────────────────────────────────

def test_selecteurs_rend_les_candidats_de_la_version_demandee():
    S = _charger_selecteurs()
    assert S.selecteurs("enregistrer", (17, 0)) == [".o_form_button_save"]


def test_selecteurs_gabarit_parametre_par_methode():
    S = _charger_selecteurs()
    assert S.selecteurs("bouton_action", (18, 0), methode="action_confirm") == [
        '.o_form_view button[name="action_confirm"]']


def test_selecteurs_repli_sur_la_version_la_plus_recente_si_version_inconnue():
    """`version=None` (détection indisponible) ne doit jamais planter — repli explicite, documenté,
    sur la version D9 la plus récente."""
    S = _charger_selecteurs()
    assert S.selecteurs("enregistrer", None) == S.selecteurs("enregistrer", (18, 0))


def test_selecteurs_repli_aussi_sur_une_version_hors_d9():
    S = _charger_selecteurs()
    assert S.selecteurs("enregistrer", (19, 0)) == S.selecteurs("enregistrer", (18, 0))


def test_falsifiable_une_cle_inconnue_leve_plutot_que_de_rendre_une_liste_vide():
    """Preuve négative : sans la garde explicite, une clé mal orthographiée rendrait une liste
    vide silencieuse — `click_first_actionable` échouerait avec un message trompeur (« aucun
    élément actionnable ») au lieu de nommer la vraie cause (clé inconnue)."""
    S = _charger_selecteurs()
    with pytest.raises(S.CleSelecteurInconnueError):
        S.selecteurs("cle_qui_n_existe_pas", (17, 0))


# ── odoo_attendre_inactif ──────────────────────────────────────────────────────

class _FakeLocator:
    def __init__(self, comportement):
        self._comportement = comportement

    def wait_for(self, state=None, timeout=None):
        self._comportement(state, timeout)


class _FakePage:
    def __init__(self, comportement):
        self._comportement = comportement

    def locator(self, selecteur):
        assert selecteur == ".o_loading_indicator"
        return _FakeLocator(self._comportement)


def test_odoo_attendre_inactif_attend_le_masquage():
    S = _charger_selecteurs()
    appels = []
    page = _FakePage(lambda state, timeout: appels.append((state, timeout)))

    S.odoo_attendre_inactif(page, timeout=5000)

    assert appels == [("hidden", 5000)]


def test_odoo_attendre_inactif_ne_leve_jamais_meme_si_l_indicateur_est_absent():
    S = _charger_selecteurs()

    def _leve(state, timeout):
        raise TimeoutError("jamais affiché")

    page = _FakePage(_leve)
    S.odoo_attendre_inactif(page)  # ne doit pas lever


# ── odoo_url_action ─────────────────────────────────────────────────────────────

def test_url_action_forme_historique_sous_17_2():
    S = _charger_selecteurs()
    ctx = types.SimpleNamespace(odoo_url="https://x.example.com", odoo_version=(17, 0))

    url = S.odoo_url_action(ctx, action=808, menu_id=566, model="knowledge.article",
                            view_type="form")

    assert url == ("https://x.example.com/web#action=808&menu_id=566"
                   "&model=knowledge.article&view_type=form")


def test_url_action_forme_recente_a_partir_de_17_2():
    S = _charger_selecteurs()
    ctx = types.SimpleNamespace(odoo_url="https://x.example.com", odoo_version=(18, 0))

    assert S.odoo_url_action(ctx, action=808) == "https://x.example.com/odoo/action-808"


def test_url_action_forme_recente_pile_a_17_2():
    S = _charger_selecteurs()
    ctx = types.SimpleNamespace(odoo_url="https://x.example.com", odoo_version=(17, 2))

    assert S.odoo_url_action(ctx, action=1) == "https://x.example.com/odoo/action-1"


def test_url_action_version_indisponible_retombe_sur_la_forme_historique():
    """`context.odoo_version` absent (détection non tentée, ex. connecteur `web`) : forme
    historique par défaut — celle en vigueur sur D9 16.0/17.0, jamais une supposition optimiste."""
    S = _charger_selecteurs()
    ctx = types.SimpleNamespace(odoo_url="https://x.example.com")  # pas d'attribut odoo_version

    assert S.odoo_url_action(ctx, action=5) == "https://x.example.com/web#action=5"


def test_url_action_tolere_un_slash_final_sur_odoo_url():
    S = _charger_selecteurs()
    ctx = types.SimpleNamespace(odoo_url="https://x.example.com/", odoo_version=(16, 0))

    assert S.odoo_url_action(ctx, action=1) == "https://x.example.com/web#action=1"


def test_url_action_recente_exige_une_action():
    S = _charger_selecteurs()
    ctx = types.SimpleNamespace(odoo_url="https://x.example.com", odoo_version=(18, 0))

    with pytest.raises(ValueError):
        S.odoo_url_action(ctx)
