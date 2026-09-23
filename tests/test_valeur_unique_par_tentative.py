"""`steps_library/generic/_generic_steps.py::step_fill_unique` — Lot 4 du plan de fiabilisation
de la génération (2026-09-23).

Constat du diagnostic réel (cas 128 « Sondage », Sapian, staging 2026-09-22) : le Gherkin généré
utilisait un nom de donnée FIXE — une valeur qui collisionnerait avec ce qu'une tentative
précédente a créé si son nettoyage a échoué entre-temps (répertoires de « Lot 4 » du plan
approuvé : « préparer des données uniques par tentative »). Ce step laisse le modèle marquer
explicitement un champ qui a besoin d'une valeur unique, sans changer le comportement du step
nominal pour tous les autres champs.

Même patron que `test_generic_navigation_step.py` : le module de steps est chargé directement,
aucun Playwright réel — `fill_field` est monkeypatché pour isoler la logique de suffixage de la
résolution DOM, déjà couverte ailleurs (`test_select_field_value_sans_name.py` etc.).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _charger_generic_steps():
    steps_lib = RACINE / "behave_runtime" / "steps_library"
    sys.path.insert(0, str(steps_lib))
    spec = importlib.util.spec_from_file_location(
        "_generic_steps_valeur_unique", steps_lib / "generic" / "_generic_steps.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Contexte:
    def __init__(self, tentative_token: str):
        self.page = object()  # jamais lu : `fill_field` est monkeypatché
        self.tentative_token = tentative_token


def test_la_valeur_est_suffixee_par_le_jeton_de_la_tentative(monkeypatch):
    mod = _charger_generic_steps()
    appels = []
    monkeypatch.setattr(mod, "fill_field", lambda page, name, value: appels.append((name, value)))
    ctx = _Contexte(tentative_token="188-a1b2c3")

    mod.step_fill_unique(ctx, "Référence", "Demande test BDD")

    assert appels == [("Référence", "Demande test BDD 188-a1b2c3")]


def test_deux_tentatives_differentes_produisent_des_valeurs_differentes(monkeypatch):
    """Le cœur du correctif : c'est CE qui empêche la collision entre deux tentatives."""
    mod = _charger_generic_steps()
    appels = []
    monkeypatch.setattr(mod, "fill_field", lambda page, name, value: appels.append(value))

    mod.step_fill_unique(_Contexte(tentative_token="188-aaaaaa"), "Référence", "Demande test")
    mod.step_fill_unique(_Contexte(tentative_token="189-bbbbbb"), "Référence", "Demande test")

    assert appels[0] != appels[1]


def test_le_step_nominal_ne_suffixe_jamais(monkeypatch):
    """Garde anti-régression : le step SANS « rendue unique » doit garder son comportement
    STRICTEMENT inchangé — la plupart des champs n'ont besoin d'aucun suffixe."""
    mod = _charger_generic_steps()
    appels = []
    monkeypatch.setattr(mod, "fill_field", lambda page, name, value: appels.append(value))
    ctx = _Contexte(tentative_token="188-a1b2c3")

    mod.step_fill(ctx, "Sujet", "Demande test BDD")

    assert appels == ["Demande test BDD"]
