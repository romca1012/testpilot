"""Couche 2 — le navigateur a refusé d'envoyer : le dire, au lieu d'accuser (2026-07-22).

⚠️ **La correction d'une erreur d'analyse.** J'avais proposé de vérifier la validité **avant** le
clic. Une sonde sur le portail réel l'a réfutée : sur `/fournisseur/creation`, le champ
`tva_intracommunautaire` est **valide avant le clic** — aucun `pattern`, aucun `title`, aucune
trace. Après le clic il devient invalide : *« Le numéro de TVA doit contenir uniquement des
chiffres. »* La règle est posée par `setCustomValidity()` **dans le gestionnaire de soumission** :
elle n'existe littéralement pas avant. Vérifier avant ne l'aurait jamais vue.

Après le clic, le navigateur a tout évalué et **nomme** ce qui cloche — les trois familles :

| Famille | Origine | Exemple mesuré |
|---|---|---|
| `valueMissing` | champ devenu obligatoire par un choix précédent | `/remboursement` : `motif = "avoir"` rend 4 champs requis |
| `patternMismatch` | format non respecté | `code_client1` attend `\\d{7}` |
| `customError` | règle métier en JavaScript — **seule trace existante** | TVA « uniquement des chiffres » |

⚠️ **Ce que ça change pour le verdict, et c'est tout l'objet.** Sans ce contrôle : la soumission
n'a pas lieu, rien n'est créé, l'assertion de comptage échoue, et le test conclut *« l'application
est non conforme »*. Avec : le scénario échoue **immédiatement**, en disant l'inverse — **c'est
notre jeu de données qui est refusé**. L'accusation injuste devient impossible.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "behave_runtime" / "steps_library"))

from _base_helpers import verifier_soumission_non_bloquee  # noqa: E402


class _Page:
    """`evaluate` rend la liste des champs invalides, comme le vrai script JS."""

    def __init__(self, invalides): self.invalides = invalides

    def evaluate(self, script, *a): return self.invalides


def _champ(nom, msg, valeur="", manquant=False):
    return {"nom": nom, "valeur": valeur, "msg": msg, "manquant": manquant}


# ── Le refus est signalé, et il DISCULPE l'application ───────────────────────

def test_un_refus_du_navigateur_fait_echouer_le_scenario():
    page = _Page([_champ("tva_intracommunautaire",
                         "Le numéro de TVA doit contenir uniquement des chiffres.",
                         "FR12345678901")])

    with pytest.raises(AssertionError, match="LE NAVIGATEUR A REFUSÉ"):
        verifier_soumission_non_bloquee(page)


def test_le_message_DISCULPE_explicitement_l_application():
    """⚠️ L'invariant central du produit. Un outil de test qui accuse à tort est pire qu'un outil
    qui ne teste rien : il détruit la confiance dans ses verdicts justes."""
    page = _Page([_champ("tva_intracommunautaire", "uniquement des chiffres", "FR123")])

    with pytest.raises(AssertionError) as err:
        verifier_soumission_non_bloquee(page)

    message = str(err.value)
    assert "L'APPLICATION N'EST PAS EN CAUSE" in message
    assert "ne conclus pas à un défaut applicatif" in message


def test_le_message_NOMME_le_champ_sa_valeur_et_la_raison():
    """Un diagnostic qui ne dit pas quoi corriger oblige à rouvrir la page à la main."""
    page = _Page([_champ("code_client1", "Veuillez respecter le format demandé.", "TEST_CLI")])

    with pytest.raises(AssertionError) as err:
        verifier_soumission_non_bloquee(page)

    message = str(err.value)
    assert "code_client1" in message
    assert "'TEST_CLI'" in message
    assert "Veuillez respecter le format demandé." in message


# ── Les champs CONDITIONNELS, expliqués ──────────────────────────────────────

def test_les_champs_devenus_obligatoires_sont_EXPLIQUES():
    """⚠️ Mesuré sur `/remboursement` : choisir `motif = "avoir"` rend obligatoires 4 champs que
    l'annuaire donnait « non requis, non visibles » — et que le prompt disait de **ne pas
    remplir**. Notre propre correctif « champs cachés » se retourne ici contre nous. Sans cette
    explication, on cherche le défaut du mauvais côté."""
    page = _Page([
        _champ("numero_avoir", "Please fill out this field.", manquant=True),
        _champ("date_avoir", "Please fill out this field.", manquant=True),
    ])

    with pytest.raises(AssertionError) as err:
        verifier_soumission_non_bloquee(page)

    message = str(err.value)
    assert "2 champ(s) OBLIGATOIRE(S) non renseigné(s)" in message
    assert "numero_avoir" in message and "date_avoir" in message
    assert "a pu les rendre obligatoires" in message, (
        "le message doit pointer la CAUSE — un choix fait plus haut — sinon on cherche le défaut "
        "du mauvais côté")


def test_sans_champ_manquant_aucune_explication_hors_sujet():
    """Un format invalide n'est pas un champ oublié : mélanger les deux égare."""
    page = _Page([_champ("code_client1", "format invalide", "abc")])

    with pytest.raises(AssertionError) as err:
        verifier_soumission_non_bloquee(page)

    assert "OBLIGATOIRE(S) non renseigné" not in str(err.value)


# ── Les bornes : ne pas casser ce qui marche ─────────────────────────────────

def test_un_clic_SANS_formulaire_bloque_ne_declenche_rien():
    """`click_button` sert aussi à naviguer, ouvrir un onglet, dérouler une section. Un contrôle
    trop large ferait échouer des scénarios parfaitement valides."""
    verifier_soumission_non_bloquee(_Page([]))


class _PageQuiPlante:
    def evaluate(self, *a, **kw): raise RuntimeError("navigateur mort")


def test_un_controle_qui_plante_ne_fait_pas_tomber_le_scenario():
    """Invariant partagé par tous les mécanismes de sûreté ajoutés : ils ne doivent jamais devenir
    eux-mêmes une cause d'échec technique."""
    verifier_soumission_non_bloquee(_PageQuiPlante())


def test_click_button_APPELLE_le_controle():
    """Le contrôle ne sert à rien s'il n'est pas branché. On vérifie le câblage, pas la mécanique
    (déjà testée ci-dessus) — c'est exactement le genre d'oubli qu'un test unitaire attrape."""
    source = Path("behave_runtime/steps_library/_base_helpers.py").read_text(encoding="utf-8")
    bloc = source.split("def click_button(")[1].split("\ndef ")[0]

    assert "verifier_soumission_non_bloquee(page)" in bloc


def test_le_script_JS_ne_regarde_QUE_les_formulaires_en_echec():
    """La borne, dans le code lui-même : on part des `form` invalides, pas de tous les champs de
    la page. Sans ça, un champ invalide sans rapport ferait échouer un clic de navigation."""
    source = Path("behave_runtime/steps_library/_base_helpers.py").read_text(encoding="utf-8")
    bloc = source.split("def verifier_soumission_non_bloquee(")[1].split("\ndef ")[0]

    assert "querySelectorAll('form')" in bloc
    assert "f.checkValidity && !f.checkValidity()" in bloc
