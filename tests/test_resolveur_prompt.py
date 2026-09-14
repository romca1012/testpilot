"""Étape 2c du §2bis — le prompt fait EMPLOYER le step d'intention sur le chemin nominal.

Le résolveur (2b) existe, mais tant que le prompt ne le recommande pas, le LLM continue de nommer
les champs un par un — et de se tromper sur les valeurs (re-mesure 2026-07-22). Ces gardes fixent
la bascule : intention par défaut pour créer, steps fins conservés pour le négatif.
"""

from __future__ import annotations

from testpilot.analysis.plan import TestPlan
from testpilot.generation import prompt as pm
from testpilot.generation import steps_library

_LABEL_INTENTION = 'je remplis le formulaire de "{route}" avec des données valides'


def _plan(routes):
    return TestPlan(module_name="m", models=[], scenarios=[], personas=["u"],
                    portal_routes=routes, risks=[], connector_type="odoo", cost_usd=0.0,
                    raw_spec="SPEC", entry_url=routes[0] if routes else "")


def _modele(champs):
    return {"mesure_le": "2026-07-22", "pages": {"/form/{id}": {"champs": champs}},
            "transitions": {}, "onglets_internes": {}}


def _champ(name, **kw):
    return {"name": name, "required": True, "tag": "input", "type": "text", "visible": True, **kw}


def test_le_step_d_intention_existe_dans_la_bibliotheque_et_le_catalogue():
    """Le LLM ne peut employer que ce qu'on lui montre (0003). Le step doit être au catalogue,
    avec sa note qui dit qu'il est le chemin NOMINAL.

    ⚠️ Depuis le 2026-09-14 (bug SauceDemo), ce step est enregistré sous `@given` ET `@when` —
    le prompt système autorise l'IA à l'enchaîner après un `Soit` comme après un `Quand` (`Et`
    hérite du précédent). Le catalogue en rend donc DEUX entrées ; on vérifie qu'AU MOINS une
    porte `when` (peu importe l'ordre), plutôt que de figer une position de liste."""
    steps = steps_library.catalogue()
    intention = [s for s in steps if s.label == _LABEL_INTENTION]
    assert intention, "le step d'intention n'est pas découvert dans la bibliothèque"
    assert {s.keyword for s in intention} >= {"given", "when"}
    assert all("NOMINAL" in (s.note or "").upper() for s in intention), (
        "sa note doit le désigner comme nominal, quelle que soit l'entrée")


def test_le_prompt_recommande_le_step_d_intention_pour_creer():
    s = pm._section_champs_requis(_plan(["/form/{id}"]),
                                  _modele([_champ("code_client1", contraintes={"pattern": r"\d{7}"})]))
    assert "je remplis le formulaire de" in s
    assert "données valides" in s
    assert "n'énumère pas les champs" in s.lower() or "n'énumère pas les champs" in s


def test_le_prompt_garde_le_step_fin_pour_le_scenario_negatif():
    """L'hybride : les steps champ-par-champ restent décrits, pour tester un refus délibéré."""
    s = pm._section_champs_requis(_plan(["/form/{id}"]),
                                  _modele([_champ("code_client1", contraintes={"pattern": r"\d{7}"})]))
    assert "je renseigne le champ" in s
    assert "NÉGATIF" in s.upper()


def test_la_recommandation_ne_casse_pas_le_rendu_des_contraintes():
    """Régression : l'ajout du chemin nominal ne doit pas effacer la référence des contraintes,
    encore utile au scénario négatif (motif verbatim + conséquence)."""
    s = pm._section_champs_requis(_plan(["/form/{id}"]),
                                  _modele([_champ("code_client1", contraintes={"pattern": r"\d{7}"})]))
    assert r"`\d{7}`" in s
    assert "bloque la soumission" in s
