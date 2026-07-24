"""Le récapitulatif de fin de banc — couvert **sans lancer le banc** (2026-07-24).

⚠️ **Pourquoi ces tests existent.** Ce code a planté une fois en fin de mesure, le 2026-07-23 :
une clé de dictionnaire renommée sans toucher l'incrément, un `KeyError`, et le récapitulatif
perdu **après** avoir payé la génération de huit cas et exécuté huit runs réels contre
l'application. Inline dans `main()`, il n'était atteignable qu'en relançant un banc complet —
c'est-à-dire en repayant. Extrait en fonction pure, il se couvre pour rien.

Les deux mesures ajoutées au brief le 2026-07-24 (§9) sont vérifiées ici : le **taux de verdicts
concluants** et le **temps par cas**.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_CHEMIN = Path(__file__).resolve().parent.parent / "scripts" / "mesure_taux_erreur_technique.py"


@pytest.fixture(scope="module")
def banc():
    """Charge le script de mesure comme un module — il n'est pas dans un paquet importable."""
    spec = importlib.util.spec_from_file_location("banc_mesure", _CHEMIN)
    module = importlib.util.module_from_spec(spec)
    sys.modules["banc_mesure"] = module
    spec.loader.exec_module(module)
    return module


def _resultats():
    """Un banc plausible : deux verdicts tranchés, une donnée invalide, une erreur technique."""
    return [
        ("achat_siege", "success", "conforme", ""),
        ("demande_avoir", "success", "non_conforme", "L'APPLICATION A REFUSÉ : champ manquant"),
        ("fournisseur", "success", "donnee_invalide", "TVA refusée par le navigateur"),
        ("mutation", "technical_error", "indetermine", "TimeoutError"),
    ]


def test_le_taux_de_verdicts_CONCLUANTS_ne_compte_que_les_tranches(banc, capsys):
    """⚠️ La distinction qui compte : « le test a tourné » n'est pas « l'outil a tranché ».

    Une erreur technique et une donnée de test invalide laissent l'utilisateur **sans réponse sur
    son application**. Les compter comme des succès rendrait la mesure flatteuse et fausse — le
    contraire de ce que le §5bis demande de suivre.
    """
    chiffres = banc.recapituler(_resultats(), {})
    assert chiffres["concluants"] == 2          # conforme + non_conforme, rien d'autre
    assert chiffres["total"] == 4
    assert "VERDICTS CONCLUANTS" in capsys.readouterr().out


def test_le_taux_technique_reste_DISTINCT_du_taux_concluant(banc):
    """Trois cas ont techniquement tourné, deux seulement ont produit un verdict exploitable.
    Confondre les deux axes ferait croire le produit meilleur qu'il n'est."""
    chiffres = banc.recapituler(_resultats(), {})
    assert chiffres["tourne"] == 3
    assert chiffres["concluants"] == 2


def test_le_temps_par_cas_est_RESTITUE(banc, capsys):
    """Le critère « moins de 5 minutes » du §9 n'avait jamais été mesuré : le banc chronométrait
    et jetait le chiffre. Un critère de succès jamais mesuré est un statut déclaratif."""
    banc.recapituler(_resultats(), {"achat_siege": 120.0, "demande_avoir": 360.0})
    sortie = capsys.readouterr().out
    assert "TEMPS PAR CAS" in sortie
    assert "cible tenue sur 1/2 cas" in sortie      # 360 s dépasse les 5 minutes


def test_un_banc_VIDE_ne_plante_pas_et_n_invente_aucun_taux(banc, capsys):
    """Zéro cas mesuré n'est pas « 0 % de réussite » : aucun pourcentage ne doit s'afficher.
    (Même principe que `ran_rate = None` de l'onglet Qualité.)"""
    chiffres = banc.recapituler([], {})
    assert chiffres["total"] == 0
    sortie = capsys.readouterr().out
    assert "taux de réussite technique" not in sortie
    assert "VERDICTS CONCLUANTS" not in sortie


def test_le_recap_ne_plante_pas_sur_un_cas_ABANDONNE(banc):
    """Un job échoué produit un résultat à 3 éléments, pas 4 : c'est exactement la forme qui a
    déjà fait tomber ce code. Le récapitulatif doit la traverser."""
    chiffres = banc.recapituler([("spec_ko", None, "demarrage_ko")], {"spec_ko": 12.0})
    assert chiffres["autre"] == 1
    assert chiffres["concluants"] == 0


def test_la_repartition_distingue_le_refus_EXPLIQUE_du_silence(banc, capsys):
    """Le cœur de la doctrine du verdict : un `non_conforme` expliqué par l'application n'est pas
    un silence indécidable. Les mélanger ferait disparaître le problème à instruire."""
    banc.recapituler([
        ("a", "success", "non_conforme", "L'APPLICATION A REFUSÉ : montant invalide"),
        ("b", "success", "non_conforme", ""),
    ], {})
    sortie = capsys.readouterr().out
    assert "1 × refus applicatif EXPLIQUÉ" in sortie
    assert "1 × refus SILENCIEUX" in sortie
