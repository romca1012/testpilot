"""`force_name_field` — contourne l'auto-génération Odoo du champ `name` via un setter natif.

Défaut RÉEL mesuré (Sapian, 2026-09-23, cas 127) : `[name="name"]` résout le
`<div class="o_field_widget">` englobant sur le web client Odoo moderne (OWL), jamais le
contrôle lui-même — même trou que celui déjà corrigé dans `locate_field`. Le setter natif choisi
doit aussi s'adapter au tag réel (`<textarea>` mesuré sur le formulaire de ticket Helpdesk,
`<input>` ailleurs) : `HTMLInputElement`/`HTMLTextAreaElement` ont des prototypes différents.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "behave_runtime" / "steps_library"))

from _base_helpers import force_name_field  # noqa: E402


class _LocatorConteneur:
    def __init__(self):
        self.attendu = False

    def wait_for(self, **_kw):
        self.attendu = True


class _PageEspion:
    def __init__(self):
        self._conteneur = _LocatorConteneur()
        self.scripts = []

    def locator(self, _selecteur):
        return self._conteneur

    def evaluate(self, script):
        self.scripts.append(script)


def test_attend_le_conteneur_avant_de_poser_la_valeur():
    page = _PageEspion()

    force_name_field(page, "Ticket BDD test")

    assert page._conteneur.attendu is True
    assert len(page.scripts) == 1


def test_le_script_descend_dans_le_conteneur_si_ce_n_est_pas_deja_un_controle():
    """Le cœur du correctif : ne PAS supposer que `[name="name"]` EST le contrôle — chercher un
    `input`/`textarea` DEDANS si le nœud résolu n'en est pas un lui-même."""
    page = _PageEspion()

    force_name_field(page, "Ticket BDD test")

    script = page.scripts[0]
    assert "conteneur.matches('input, textarea')" in script
    assert "conteneur.querySelector('input, textarea')" in script


def test_le_script_choisit_le_bon_prototype_selon_le_tag():
    page = _PageEspion()

    force_name_field(page, "Ticket BDD test")

    script = page.scripts[0]
    assert "HTMLTextAreaElement.prototype" in script
    assert "HTMLInputElement.prototype" in script


def test_la_valeur_est_echappee_contre_l_injection_dans_le_script():
    page = _PageEspion()

    force_name_field(page, "Valeur avec des ' guillemets \\ et antislash")

    script = page.scripts[0]
    assert "\\'" in script  # le guillemet simple est échappé, jamais injecté tel quel
