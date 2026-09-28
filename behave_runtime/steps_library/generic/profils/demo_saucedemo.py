"""Profil d'instance DEMO_SAUCEDEMO (lot 06, D6, F6) — steps propres à une démo/fixture, jamais
utilisés par aucun test de conformité ni aucun cas connu à ce jour (aucune occurrence trouvée dans
`tests/`, y compris `tests/fixtures/torture_app/` — voir le rapport du lot). Conservé plutôt que
supprimé : un cas généré existant pourrait s'y référer, et supprimer sans preuve romprait son
rejeu sans avertissement.

Copié par le runner sous `steps/_profil_generic.py` (nom CANONIQUE) SEULEMENT quand le projet
déclare `profil_instance = "demo_saucedemo"` (`BehaveRunner._profil_files`) — jamais inclus par
défaut.
"""

from behave import given, when

from _base_helpers import click_first_actionable


@given('je clique sur le bouton "{label}" avec accessoires')
@when('je clique sur le bouton "{label}" avec accessoires')
def step_click_button_with_accessoires(context, label):
    click_first_actionable(context.page,
        [f".btn-{label}", f":is(button, a):has-text('{label}')"],
        quoi=f"Bouton '{label}' (accessoires)")
