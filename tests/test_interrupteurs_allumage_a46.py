"""Décision A46 (porteur, 2026-10-16, après les mesures M1 et ciblée) — la génération avec données de test est ALLUMÉE par
défaut ; la comparaison des montants avec unité reste éteinte.

Falsifiable : échoue si un interrupteur des données de test redevient éteint sans variable, si une valeur d'extinction
n'éteint plus, si `TESTPILOT_STEP_NOMBRE` s'allume tout seul, ou si `allume()` lit autrement que les fonctions dédiées.
"""

import pytest

from testpilot.generation import interrupteurs as i

DONNEES = (i.ENV_VARIABLES_DE_TEST, i.ENV_CAS_DIT_SES_DONNEES)


@pytest.mark.parametrize("valeur", [None, "", "  ", "1", "oui", "ON"])
def test_falsifiable_absent_vide_ou_vrai_allume(valeur):
    env = {} if valeur is None else {nom: valeur for nom in DONNEES}
    assert i.variables_de_test_actif(env) is True
    assert i.cas_dit_ses_donnees_actif(env) is True
    assert all(i.allume(nom, env) for nom in DONNEES)


@pytest.mark.parametrize("valeur", ["0", "false", "no", "non", "off", " OFF ", "Non"])
def test_falsifiable_une_extinction_explicite_eteint(valeur):
    env = {nom: valeur for nom in DONNEES}
    assert i.variables_de_test_actif(env) is False
    assert i.cas_dit_ses_donnees_actif(env) is False
    assert not any(i.allume(nom, env) for nom in DONNEES)


def test_le_cas_ne_dit_ses_donnees_qu_avec_les_variables_de_test():
    assert i.cas_dit_ses_donnees_actif({i.ENV_VARIABLES_DE_TEST: "0"}) is False
    assert i.cas_dit_ses_donnees_actif({i.ENV_CAS_DIT_SES_DONNEES: "0"}) is False


def test_falsifiable_les_montants_avec_unite_et_les_autres_restent_eteints():
    for nom in (i.ENV_STEP_NOMBRE, i.ENV_TOOLS_STRICT, i.ENV_PROMPT_HYPOTHESES, i.ENV_TOOLS_DESCRIPTIONS_V2,
                i.ENV_REGLES_CONNECTEUR):
        assert i.allume(nom, {}) is False, nom
    assert i.allume(i.ENV_STEP_NOMBRE, {i.ENV_STEP_NOMBRE: "1"}) is True
