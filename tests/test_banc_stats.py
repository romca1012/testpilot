"""Lot Q2-a — `scripts/banc_stats.py` : les statistiques du banc d'évaluation d'agents.

Ce que ces tests fixent (et qui échouerait si la formule ou la règle était fausse) :
- l'intervalle de Wilson est comparé à une référence INDÉPENDANTE de la formule fermée (résolution
  numérique par dichotomie, plus valeurs publiées) ;
- pass^k <= pass@1 <= pass@k, et les trois DIVERGENT sur un jeu construit (75 % par essai → ~42 %
  sur trois essais de suite, l'exemple de l'article d'Anthropic « Demystifying evals ») ;
- « non mesuré » n'est JAMAIS zéro : dénominateur nul → `None` partout ;
- un `technical_error` / `blocked` / `indetermine` n'est ni faux vert ni faux rouge, mais il ne
  disparaît pas : il est compté dans `non_concluants` et ne masque jamais un faux vert.
"""

from __future__ import annotations

import importlib.util
import itertools
import math
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("banc_stats", RACINE / "scripts" / "banc_stats.py")
stats = importlib.util.module_from_spec(_spec)
sys.modules["banc_stats"] = stats
_spec.loader.exec_module(stats)


def _wilson_par_dichotomie(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Référence INDÉPENDANTE : les bornes de Wilson sont les p qui vérifient
    (p̂ − p)² = z²·p(1−p)/n. On les trouve par dichotomie, sans jamais utiliser la formule fermée
    du module (centre ± demi-largeur) : si celle-ci était fausse, cette référence ne le serait pas."""
    p_hat = k / n

    def dedans(p: float) -> bool:
        return (p_hat - p) ** 2 <= z * z * p * (1 - p) / n

    bas_lo, bas_hi = 0.0, p_hat  # la borne basse est entre 0 et p̂ (0 inclus : dedans(0) si k == 0)
    for _ in range(200):
        milieu = (bas_lo + bas_hi) / 2
        if dedans(milieu):
            bas_hi = milieu
        else:
            bas_lo = milieu
    haut_lo, haut_hi = p_hat, 1.0
    for _ in range(200):
        milieu = (haut_lo + haut_hi) / 2
        if dedans(milieu):
            haut_lo = milieu
        else:
            haut_hi = milieu
    return bas_hi, haut_lo


def _enr(cas, variante, attendu, obtenu):
    return {"cas": cas, "variante": variante, "attendu": attendu, "obtenu": obtenu}


# ── Intervalle de Wilson ─────────────────────────────────────────────────────────────────────


def test_wilson_11_sur_15_est_la_valeur_publiee_de_la_mesure_odoo():
    bas, haut = stats.intervalle_wilson(11, 15)
    # Même valeur de référence que `tests/test_banc_web.py` (branche feat-banc-web-phase1).
    assert bas == pytest.approx(0.4805, abs=1e-3)
    assert haut == pytest.approx(0.8910, abs=1e-3)


@pytest.mark.parametrize(
    "k, n", [(0, 1), (1, 1), (0, 5), (5, 5), (3, 8), (11, 15), (1, 20), (19, 20), (50, 100)]
)
def test_wilson_concorde_avec_la_resolution_numerique_independante(k, n):
    bas, haut = stats.intervalle_wilson(k, n)
    ref_bas, ref_haut = _wilson_par_dichotomie(k, n)
    assert bas == pytest.approx(ref_bas, abs=1e-9)
    assert haut == pytest.approx(ref_haut, abs=1e-9)


def test_wilson_valeurs_de_la_litterature():
    # 0/10 : borne haute 0,2775 ; 10/10 : borne basse 0,7225 (Wilson 95 %, valeurs classiques).
    assert stats.intervalle_wilson(0, 10)[1] == pytest.approx(0.2775, abs=5e-4)
    assert stats.intervalle_wilson(10, 10)[0] == pytest.approx(0.7225, abs=5e-4)
    # 3/8 : [0,1368 ; 0,6943] (l'exemple du formatage).
    bas, haut = stats.intervalle_wilson(3, 8)
    assert (bas, haut) == (pytest.approx(0.1368, abs=5e-4), pytest.approx(0.6943, abs=5e-4))


def test_wilson_sans_observation_ne_fabrique_aucun_intervalle():
    assert stats.intervalle_wilson(0, 0) is None


@pytest.mark.parametrize("k, n", [(2, 1), (-1, 5), (1, -3)])
def test_wilson_refuse_une_proportion_impossible(k, n):
    with pytest.raises(ValueError):
        stats.intervalle_wilson(k, n)


@pytest.mark.parametrize("k, n", [(0, 10), (10, 10), (1, 1), (0, 1), (7, 9)])
def test_wilson_reste_dans_zero_un_et_contient_la_proportion(k, n):
    bas, haut = stats.intervalle_wilson(k, n)
    assert 0.0 <= bas <= k / n <= haut <= 1.0


def test_wilson_se_resserre_quand_l_echantillon_grandit():
    # Même proportion (3/8 = 30/80 = 37,5 %), dix fois plus de cas : l'intervalle doit rétrécir.
    petit = stats.intervalle_wilson(3, 8)
    grand = stats.intervalle_wilson(30, 80)
    assert (grand[1] - grand[0]) < (petit[1] - petit[0])


# ── pass@1, pass@k, pass^k ───────────────────────────────────────────────────────────────────


def test_pass_at_1_ne_regarde_que_le_premier_essai():
    essais = {
        "a": [True, False, False],  # premier essai réussi -> compte
        "b": [False, True, True],  # premier essai raté -> ne compte pas malgré 2 succès ensuite
        "c": [True],
    }
    r = stats.pass_at_1(essais)
    assert (r["k"], r["n"], r["non_mesures"]) == (2, 3, 0)
    assert r["taux"] == pytest.approx(2 / 3)


def test_pass_at_1_vaut_zero_quand_aucun_premier_essai_ne_reussit():
    r = stats.pass_at_1({"a": [False, True], "b": [False]})
    assert r["k"] == 0 and r["n"] == 2
    assert r["taux"] == 0.0  # mesuré et nul : différent de « non mesuré » (None)


def test_pass_hat_k_exige_tous_les_essais_et_pass_at_k_un_seul():
    essais = {
        "tous": [True, True, True],
        "un_seul": [False, True, False],
        "aucun": [False, False, False],
    }
    assert stats.pass_hat_k(essais, 3)["k"] == 1
    assert stats.pass_at_k(essais, 3)["k"] == 2


def test_pass_k_ne_regarde_que_les_k_premiers_essais():
    essais = {"a": [True, True, False]}  # le 3e essai raté ne compte pas pour k = 2
    assert stats.pass_hat_k(essais, 2)["k"] == 1
    assert stats.pass_hat_k(essais, 3)["k"] == 0


def test_un_cas_avec_moins_de_k_essais_est_non_mesure_pas_un_echec():
    essais = {"complet": [True, True, True], "court": [True, True]}
    r = stats.pass_hat_k(essais, 3)
    # Le cas court sort du dénominateur ET est rapporté ; il n'est pas compté comme raté.
    assert (r["k"], r["n"], r["non_mesures"]) == (1, 1, 1)
    assert r["taux"] == 1.0


def test_k_trop_grand_rend_non_mesure_jamais_zero():
    essais = {"a": [True, True], "b": [True]}
    for fonction in (stats.pass_hat_k, stats.pass_at_k):
        r = fonction(essais, 5)
        assert r["n"] == 0 and r["non_mesures"] == 2
        assert r["taux"] is None and r["ic95"] is None


def test_aucun_cas_rend_none_pour_les_trois_mesures():
    assert stats.pass_at_1({})["taux"] is None
    assert stats.pass_at_k({}, 3)["ic95"] is None
    assert stats.pass_hat_k({}, 3)["taux"] is None


@pytest.mark.parametrize("k", [0, -1, 1.5, True])
def test_k_invalide_est_refuse(k):
    with pytest.raises(ValueError):
        stats.pass_hat_k({"a": [True]}, k)


def test_pass_hat_k_infra_pass_at_1_infra_pass_at_k_et_ils_divergent_a_75_pour_cent():
    """Jeu construit : chaque essai réussit avec la probabilité 3/4, indépendamment, 3 essais par cas.
    On énumère les 2³ suites possibles, chacune répétée 3^(nb succès) fois : 4³ = 64 cas au total,
    et les proportions sont EXACTES (pas d'aléa) : pass@1 = 48/64, pass^3 = 27/64, pass@3 = 63/64."""
    essais = {}
    for suite in itertools.product([True, False], repeat=3):
        for copie in range(3 ** sum(suite)):
            essais[f"{suite}-{copie}"] = list(suite)
    assert len(essais) == 64

    p1 = stats.pass_at_1(essais)["taux"]
    ph3 = stats.pass_hat_k(essais, 3)["taux"]
    pa3 = stats.pass_at_k(essais, 3)["taux"]

    assert p1 == pytest.approx(0.75)
    assert ph3 == pytest.approx(0.75**3)  # ≈ 42 %, l'exemple de l'article
    assert pa3 == pytest.approx(1 - 0.25**3)
    assert ph3 <= p1 <= pa3
    # Divergence stricte : sinon les trois mesures seraient interchangeables et le test ne prouverait rien.
    assert ph3 < p1 < pa3
    assert math.isclose(ph3, 27 / 64)


def test_a_k_egal_un_les_trois_mesures_coincident():
    essais = {"a": [True, False], "b": [False, True], "c": [True, True]}
    assert stats.pass_at_1(essais)["k"] == stats.pass_at_k(essais, 1)["k"]
    assert stats.pass_at_1(essais)["k"] == stats.pass_hat_k(essais, 1)["k"]


# ── Faux verts / faux rouges ─────────────────────────────────────────────────────────────────


def test_faux_verts_comptent_un_conforme_sur_variante_defectueuse():
    enregistrements = [
        _enr("c1", "total_faux", "non_conforme", "conforme"),  # faux vert
        _enr("c2", "total_faux", "non_conforme", "non_conforme"),  # défaut bien détecté
        _enr("c3", "taxe_omise", "non_conforme", "non_conforme"),
        _enr("c4", "taxe_omise", "non_conforme", "non_conforme"),
    ]
    r = stats.faux_verts(enregistrements)
    assert (r["k"], r["n"], r["non_concluants"]) == (1, 4, 0)
    assert r["taux"] == 0.25
    assert r["ic95"] == stats.intervalle_wilson(1, 4)


def test_faux_verts_vaut_zero_quand_tous_les_defauts_sont_detectes():
    r = stats.faux_verts([_enr("c1", "d", "non_conforme", "non_conforme")] * 3)
    assert (r["k"], r["n"]) == (0, 3)
    assert r["taux"] == 0.0  # mesuré et nul, pas « non mesuré »


def test_faux_rouges_comptent_un_non_conforme_sur_variante_saine():
    enregistrements = [
        _enr("c1", "saine", "conforme", "non_conforme"),  # faux rouge
        _enr("c2", "saine", "conforme", "conforme"),
        _enr("c3", "saine", "conforme", "conforme"),
    ]
    r = stats.faux_rouges(enregistrements)
    assert (r["k"], r["n"], r["non_concluants"]) == (1, 3, 0)
    assert r["taux"] == pytest.approx(1 / 3)


def test_faux_rouges_vaut_zero_quand_la_variante_saine_passe_toujours():
    r = stats.faux_rouges([_enr("c1", "saine", "conforme", "conforme")] * 4)
    assert (r["k"], r["n"]) == (0, 4)
    assert r["taux"] == 0.0


def test_les_deux_indicateurs_ne_se_contaminent_pas():
    enregistrements = [
        _enr("c1", "saine", "conforme", "conforme"),  # saine : jamais dans les faux verts
        _enr("c2", "defaut", "non_conforme", "conforme"),  # défectueuse : jamais dans les faux rouges
        _enr("c3", "defaut", "conforme", "non_conforme"),  # attendu incohérent : ignoré des deux
    ]
    assert (stats.faux_verts(enregistrements)["k"], stats.faux_verts(enregistrements)["n"]) == (1, 1)
    assert (stats.faux_rouges(enregistrements)["k"], stats.faux_rouges(enregistrements)["n"]) == (0, 1)


def test_un_technical_error_ne_masque_pas_un_faux_vert():
    avec_erreurs = [
        _enr("c1", "d", "non_conforme", "conforme"),  # faux vert bien réel
        _enr("c2", "d", "non_conforme", "technical_error"),
        _enr("c3", "d", "non_conforme", "blocked"),
        _enr("c4", "d", "non_conforme", "indetermine"),
    ]
    r = stats.faux_verts(avec_erreurs)
    assert r["k"] == 1  # le faux vert reste visible
    assert r["non_concluants"] == 3  # et les trois non concluants sont rapportés, pas avalés
    assert r["n"] == 1  # ils ne comptent ni comme détection ni comme faux vert
    # Falsifiabilité : si on les rangeait avec les « bons » résultats, le taux tomberait à 1/4 au lieu de 1/1.
    assert r["taux"] == 1.0


def test_que_des_resultats_non_concluants_ne_donnent_pas_zero_faux_vert():
    r = stats.faux_verts([_enr(f"c{i}", "d", "non_conforme", "technical_error") for i in range(5)])
    assert r["taux"] is None and r["ic95"] is None  # « non mesuré », surtout pas 0 %
    assert r["n"] == 0 and r["non_concluants"] == 5  # mais les 5 cas sont signalés


def test_un_non_concluant_sur_variante_saine_n_est_pas_un_faux_rouge():
    r = stats.faux_rouges(
        [_enr("c1", "saine", "conforme", "technical_error"), _enr("c2", "saine", "conforme", "conforme")]
    )
    assert (r["k"], r["n"], r["non_concluants"]) == (0, 1, 1)


def test_aucun_enregistrement_rend_none_pour_chaque_indicateur():
    for indicateur in (stats.faux_verts, stats.faux_rouges):
        r = indicateur([])
        assert r == {"k": 0, "n": 0, "non_concluants": 0, "taux": None, "ic95": None}


def test_un_seul_cas_en_enregistrements():
    r = stats.faux_verts([_enr("seul", "d", "non_conforme", "conforme")])
    assert (r["k"], r["n"]) == (1, 1)
    assert r["taux"] == 1.0
    assert r["ic95"] == stats.intervalle_wilson(1, 1)  # large : un seul cas ne prouve presque rien
    assert r["ic95"][0] < 0.5


def test_les_populations_visees_sont_vides_si_les_enregistrements_sont_d_une_autre_variante():
    saines_seulement = [_enr("c1", "saine", "conforme", "conforme")]
    assert stats.faux_verts(saines_seulement)["taux"] is None  # aucune variante défectueuse mesurée
    defectueuses_seulement = [_enr("c1", "d", "non_conforme", "non_conforme")]
    assert stats.faux_rouges(defectueuses_seulement)["taux"] is None


@pytest.mark.parametrize(
    "champ, valeur", [("obtenu", "passed"), ("attendu", "vert"), ("obtenu", None), ("variante", "")]
)
def test_une_valeur_inconnue_est_refusee_plutot_que_comptee_nulle_part(champ, valeur):
    enregistrement = _enr("c1", "d", "non_conforme", "conforme")
    enregistrement[champ] = valeur
    with pytest.raises(ValueError):
        stats.faux_verts([enregistrement])


# ── Présentation ─────────────────────────────────────────────────────────────────────────────


def test_formater_taux_donne_la_chaine_francaise_attendue():
    assert stats.formater_taux(3, 8) == "3/8 (37,5 %, IC95 % 13,7–69,4 %)"


def test_formater_taux_ne_dit_jamais_zero_quand_rien_n_est_mesure():
    assert stats.formater_taux(0, 0) == "non mesuré"
    assert "0" not in stats.formater_taux(0, 0)


def test_formater_taux_distingue_zero_mesure_de_non_mesure():
    texte = stats.formater_taux(0, 5)
    assert texte.startswith("0/5 (0,0 %")
    assert texte != "non mesuré"
    assert "43,4 %" in texte  # borne haute de Wilson pour 0/5 : z² / (n + z²)


def test_formater_taux_rapporte_les_non_concluants():
    assert stats.formater_taux(3, 8, non_concluants=1) == (
        "3/8 (37,5 %, IC95 % 13,7–69,4 %) ; 1 non concluant"
    )
    assert stats.formater_taux(3, 8, non_concluants=2).endswith("; 2 non concluants")
    assert stats.formater_taux(0, 0, non_concluants=4) == "non mesuré (4 non concluants)"
