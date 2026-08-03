"""La normalisation de route a UN seul propriétaire — `domain_model`.

⚠️ **Pourquoi ces tests existent.** Depuis que le runtime apprend des règles d'un refus, il y a
DEUX producteurs de routes : le crawl (qui écrit l'annuaire) et l'exécution (qui indexe une règle
apprise). S'ils normalisaient différemment, une règle apprise sur `/en/fournisseur/creation` ne
serait jamais retrouvée pour la route `/fournisseur/creation` de l'annuaire — un mécanisme
silencieusement mort, sans rien à l'écran pour le trahir. C'est le motif exact de `PRINCIPES.md`
principe 4 : un seul endroit décide.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from testpilot.generation import domain_model

RACINE = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("url, attendu", [
    ("/en/formulaire/12", "/formulaire/{id}"),
    ("/formulaire/12", "/formulaire/{id}"),
    ("/fr_BE/achat_siege/113", "/achat_siege/{id}"),
    ("/fournisseur/creation", "/fournisseur/creation"),
    ("https://portail.example.com/en/mutation/7", "/mutation/{id}"),
    ("/demande_avoir/29789?debug=1", "/demande_avoir/{id}"),
    ("/en/my/home", "/my/home"),
    ("/", "/"),
    ("", "/"),
])
def test_normaliser_route(url, attendu):
    assert domain_model.normaliser_route(url) == attendu


def test_PIEGE_un_segment_de_deux_lettres_est_pris_pour_une_LANGUE():
    """⚠️ Comportement RÉEL, documenté ici pour qu'il ne surprenne personne.

    `my` est un code ISO 639-1 valide (birman) : aucune heuristique ne le distingue du `/my`
    d'Odoo. Sur le portail mesuré, ça ne se voit pas — il redirige vers `/en/my/home`, le `/en`
    part et la clé stockée est bien `/my/home` (vérifié dans `data/domain/projet-1.json`, présent
    depuis le tout premier crawl).

    **Mais une URL SANS locale donne une clé différente de celle de l'annuaire.** C'est pourquoi
    une règle apprise à l'exécution ne se retrouve JAMAIS par égalité de chaîne : elle passe par
    `domain_model._meme_route`, le rapprochement par segments que l'annuaire utilise déjà.

    Corriger la regex changerait les clés de l'annuaire — une référence versionnée, relue par un
    humain. Hors périmètre : on contient le risque, on ne le déplace pas.
    """
    assert domain_model.normaliser_route("/en/my/home") == "/my/home"
    assert domain_model.normaliser_route("/my/home") == "/home"


def test_le_prefixe_de_langue_seul_garde_l_identifiant_concret():
    """`retirer_prefixe_langue` n'est PAS `normaliser_route` : le crawl a besoin des deux.

    L'URL d'exemple doit rester navigable (`0021` : l'agent inventait `/demande_avoir/29789`),
    donc son identifiant réel est conservé — seule la locale part.
    """
    assert domain_model.retirer_prefixe_langue("/en/achat_siege/113") == "/achat_siege/113"
    assert domain_model.normaliser_route("/en/achat_siege/113") == "/achat_siege/{id}"


def _charger_crawl():
    """Importe le script de crawl sans le lancer (il vit hors du paquet installé)."""
    sys.path.insert(0, str(RACINE / "behave_runtime" / "steps_library"))
    spec = importlib.util.spec_from_file_location(
        "_crawl_domaine_sous_test", RACINE / "scripts" / "crawl_domaine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("url", [
    "/en/formulaire/12", "/fournisseur/creation", "/fr_BE/achat_siege/113",
    "/my/home/", "/demande_avoir/29789?debug=1", "/",
])
def test_GARDE_le_crawl_et_le_runtime_normalisent_IDENTIQUEMENT(url):
    """Le crawl DÉLÈGUE — il ne réimplémente pas.

    ⚠️ Ce test échoue si quelqu'un réintroduit une regex locale dans `crawl_domaine.py` :
    c'est exactement la divergence qui rendrait une règle apprise introuvable.
    """
    pytest.importorskip("playwright.sync_api")
    crawl = _charger_crawl()
    assert crawl.normalise(url) == domain_model.normaliser_route(url)
