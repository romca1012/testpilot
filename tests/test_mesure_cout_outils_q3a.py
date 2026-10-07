"""Q3-a — le calcul de surcoût local (`scripts/mesure_cout_outils_q3a.py`) est juste.

Une estimation de coût fausse ferait décider « activer » ou « ne pas activer » à tort : l'arithmétique
du cache (1 écriture + n-1 lectures) et la monotonie des configurations sont donc vérifiées sur des
valeurs calculables à la main. Aucun appel réseau.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "mesure_cout_outils_q3a.py"
_spec = importlib.util.spec_from_file_location("mesure_cout_outils_q3a", _SCRIPT)
mesure = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mesure)


def test_estimation_est_caracteres_sur_quatre_arrondie_au_dessus():
    assert mesure.estimer_tokens("a" * 8) == 2
    assert mesure.estimer_tokens("a" * 9) == 3
    assert mesure.estimer_tokens("a" * 9, 3.0) == 3
    assert mesure.estimer_tokens("") == 0


def test_surcout_avec_cache_une_ecriture_puis_des_lectures():
    # Sonnet 4.6 : cache_write 3,75 $/M, cache_read 0,30 $/M, input 3 $/M.
    # 1 000 000 tokens ajoutés, 25 tours : 3,75 + 24 x 0,30 = 10,95 $ avec cache ; 25 x 3 = 75 $ sans.
    cout = mesure.surcout_usd(1_000_000, tours=25)
    assert cout["avec_cache"] == pytest.approx(10.95)
    assert cout["sans_cache"] == pytest.approx(75.0)


def test_le_cache_est_toujours_moins_cher_que_pas_de_cache_au_dela_d_un_tour():
    for tours in (2, 6, 25):
        cout = mesure.surcout_usd(1000, tours=tours)
        assert cout["avec_cache"] < cout["sans_cache"]
    # Falsifiabilité : à UN seul tour, l'écriture de cache coûte PLUS que le plein tarif (1,25x).
    un = mesure.surcout_usd(1000, tours=1)
    assert un["avec_cache"] > un["sans_cache"]


def test_aucun_surcout_quand_tout_est_eteint_et_il_croit_avec_chaque_interrupteur():
    base = mesure.tokens_outils({})
    assert base > 0
    assert mesure.surcout_usd(mesure.tokens_outils({}) - base)["avec_cache"] == 0
    for nom, env in mesure.CONFIGURATIONS.items():
        if env:
            assert mesure.tokens_outils(env) > base, nom       # chaque interrupteur AJOUTE du texte
    assert mesure.tokens_outils(mesure.CONFIGURATIONS["tout allumé"]) >= max(
        mesure.tokens_outils(env) for env in mesure.CONFIGURATIONS.values() if env)


def test_la_borne_haute_depasse_l_estimation_nominale():
    env = mesure.CONFIGURATIONS["tout allumé"]
    assert mesure.tokens_outils(env, 3.0) > mesure.tokens_outils(env, 4.0)


def test_le_champ_d_hypotheses_plein_reste_negligeable_devant_le_budget():
    from testpilot import config
    assert 0 < mesure.surcout_sortie_hypotheses_usd() < 0.02 * config.BUDGET_PER_CASE_USD
