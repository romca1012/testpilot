"""Étape 5 du plan unique (AV-7) — une génération qui n'aboutit pas dit POURQUOI : raison de l'arrêt, tours, fichiers écrits ou
non, derniers refus d'outil, dernier essai à blanc (`GenerationResult.diagnostic_arret`, lu par le banc). Mesuré : 5 générations
sur 5 du même cas sans essai à blanc passé, et rien de plus que « génération sans essai à blanc passé » pour l'instruire.
"""

from __future__ import annotations


def test_av7_la_boucle_consigne_les_refus_et_le_resultat_les_rend_seulement_en_echec(monkeypatch):
    """Étape 5 (AV-7) : une génération qui n'aboutit pas dit pourquoi (raison, tours, refus récents)."""
    from testpilot.analysis.plan import TestPlan
    from testpilot.generation.agent import GenerationAgent
    from testpilot.generation.state import AgentState

    def boucle(**kw):
        etat: AgentState = kw["state"]
        etat.refus_recents = ["[write_feature_file] ENREGISTREMENT_NON_POSE : …"]
        etat.stopped_reason, etat.iterations, etat.feature_written = "max_iterations", 25, True
    monkeypatch.setattr("testpilot.generation.agent.run_loop", boucle)
    plan = TestPlan(module_name="m", models=[], scenarios=[], personas=[], portal_routes=[], risks=[], raw_spec="spec")
    resultat = GenerationAgent().generate(plan)
    assert not resultat.success
    assert resultat.diagnostic_arret == {"arret": "max_iterations", "tours": 25, "feature_ecrite": True,
                                         "steps_ecrits": False, "refus_recents": ["[write_feature_file] ENREGISTREMENT_NON_POSE : …"],
                                         "dernier_dry_run": ""}
