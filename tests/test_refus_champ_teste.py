"""Un scénario NÉGATIF ne doit plus jamais être accusé de « donnée fautive » sur le champ qu'IL
teste lui-même — bug réel mesuré le 2026-08-07 sur `/retenue_garantie` (cas 124 et 125, run 20).

Avant ce correctif, `verifier_soumission_non_bloquee` traitait TOUT champ invalide après un clic
comme une preuve que le jeu de données du test était fautif — y compris le champ que le scénario
laisse vide EXPRÈS (`je laisse le champ … vide`) pour vérifier que le formulaire le refuse. Aucun
scénario de ce type (une vingtaine dans `behave_runtime/generated/`) ne pouvait donc jamais
conclure « conforme » : le contrôle levait `DonneeRefuseeError` avant même que l'assertion
`Alors une erreur de validation est affichée` ait sa chance de se prononcer.

Deuxième défaut, sur le MÊME run : `copy_invoice_part` (un champ « ajouter des fichiers ») portait
un fichier valide juste avant le clic sur Envoyer — c'est le clic LUI-MÊME (JS du portail) qui l'a
vidé, mesuré en direct (`filesCount` passe de 1 à 0 entre l'attache et la lecture post-clic). Ce
n'est pas notre donnée qui est en cause : on l'avait bien remplie.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

import _base_helpers as H  # noqa: E402
from _base_helpers import DonneeRefuseeError, verifier_soumission_non_bloquee  # noqa: E402


class _Page:
    """`evaluate` rend la liste des champs invalides, comme le vrai script JS — même patron que
    `test_soumission_bloquee.py`. Les attributs de marquage sont posés directement, comme le
    ferait `attach_file`/`leave_field_empty` sur une vraie page Playwright."""

    def __init__(self, invalides): self.invalides = invalides

    def evaluate(self, script, *a): return self.invalides


def _champ(nom, msg, valeur="", manquant=False):
    return {"nom": nom, "valeur": valeur, "msg": msg, "manquant": manquant}


# ── Le champ que LE SCÉNARIO teste lui-même n'accuse plus le jeu de données ────

def test_le_champ_laisse_vide_par_le_scenario_lui_meme_ne_leve_RIEN():
    page = _Page([_champ("rib_original", "Please select a file.", manquant=True)])
    page._tp_champs_vides_intentionnels = {"rib_original"}

    verifier_soumission_non_bloquee(page)  # ne lève PAS


def test_un_AUTRE_champ_invalide_non_couvert_est_toujours_signale():
    """La protection ne doit couvrir QUE ce qu'on a explicitement marqué — un vrai souci de
    donnée ailleurs doit continuer à être signalé, sinon le contrôle perd tout son sens."""
    page = _Page([
        _champ("rib_original", "Please select a file.", manquant=True),
        _champ("code_client1", "format invalide", "abc"),
    ])
    page._tp_champs_vides_intentionnels = {"rib_original"}

    with pytest.raises(DonneeRefuseeError) as err:
        verifier_soumission_non_bloquee(page)

    message = str(err.value)
    assert "code_client1" in message
    assert "rib_original" not in message, "le champ testé ne doit plus apparaître dans le refus"


# ── Un champ fichier déjà rempli, vidé par le CLIC lui-même ────────────────────

def test_un_champ_fichier_deja_rempli_avant_le_clic_n_est_pas_accuse():
    """`copy_invoice_part` — 2026-08-07 : rempli avant le clic, vidé PAR le clic (JS du portail).
    Ce n'est pas notre jeu de données qui est en cause."""
    page = _Page([_champ("copy_invoice_part", "Please select one or more files.", manquant=True)])
    page._tp_champs_fichiers_remplis = {"copy_invoice_part"}

    verifier_soumission_non_bloquee(page)  # ne lève PAS


def test_combinaison_reelle_du_run_20_ne_leve_RIEN():
    """Rejoue EXACTEMENT ce qui a été mesuré sur le cas 125 : un champ testé (`rib_original`) +
    un champ fichier vidé par le clic (`copy_invoice_part`). Les deux couverts → aucun refus."""
    page = _Page([
        _champ("rib_original", "Please select a file.", manquant=True),
        _champ("copy_invoice_part", "Please select one or more files.", manquant=True),
    ])
    page._tp_champs_vides_intentionnels = {"rib_original"}
    page._tp_champs_fichiers_remplis = {"copy_invoice_part"}

    verifier_soumission_non_bloquee(page)  # ne lève PAS


# ── Isolation par page (jamais de fuite d'un scénario à l'autre) ──────────────

def test_le_marquage_est_isole_PAR_PAGE():
    """Chaque scénario a sa PROPRE page Playwright (`environment.py`) — un ensemble module-level
    aurait fait fuiter l'intention d'un scénario vers le suivant si un champ porte le même nom."""
    page_a = _Page([_champ("piece_jointe_facture", "Please select a file.", manquant=True)])
    page_a._tp_champs_vides_intentionnels = {"piece_jointe_facture"}
    page_b = _Page([_champ("piece_jointe_facture", "Please select a file.", manquant=True)])
    # page_b ne marque RIEN — un scénario différent, sans lien avec l'intention de page_a.

    verifier_soumission_non_bloquee(page_a)  # ne lève PAS (couvert)
    with pytest.raises(DonneeRefuseeError):
        verifier_soumission_non_bloquee(page_b)  # lève (non couvert sur CETTE page)


# ── `attach_file` / `leave_field_empty` posent bien le marquage ───────────────

class _FauxLocatorFichier:
    def __init__(self): self.first = self
    def set_input_files(self, chemin): pass
    def evaluate(self, script, *a): return "file" if "type" in script else "input"


class _FauxPageFichier:
    def __init__(self): self._marques = {}
    def wait_for_selector(self, *a, **kw): pass
    def locator(self, sel): return _FauxLocatorFichier()


def test_attach_file_MARQUE_le_champ_comme_rempli():
    page = _FauxPageFichier()

    H.attach_file(page, "copy_invoice_part")

    assert page._tp_champs_fichiers_remplis == {"copy_invoice_part"}


class _FauxLocatorTexte:
    def __init__(self): self.first = self
    def evaluate(self, script, *a): return "input" if "tagName" in script else "text"
    def fill(self, *a, **kw): pass


class _FauxPageTexte:
    def wait_for_selector(self, *a, **kw): pass
    def locator(self, sel): return _FauxLocatorTexte()


def test_leave_field_empty_MARQUE_le_champ_comme_intentionnellement_vide():
    page = _FauxPageTexte()
    original = H.resolve_field_name
    H.resolve_field_name = lambda p, n: n
    try:
        H.leave_field_empty(page, "rib_original")
    finally:
        H.resolve_field_name = original

    assert page._tp_champs_vides_intentionnels == {"rib_original"}
