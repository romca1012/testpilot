"""Lot 05 (D5) — la confiance du verdict : un vert obtenu par repli ou par retry n'est pas un vert nominal.

Calcul PUR depuis le sidecar des paliers et le fait d'avoir rejoué. Ce n'est ni un statut ni un axe : les deux axes et
le statut de lecture ne bougent pas.
"""

from __future__ import annotations

from testpilot.execution.behave_result import BehaveResult, BehaveScenario
from testpilot.execution.executor import ExecutionOutcome
from testpilot.verdict import status as st


def _outcome(scenarios, paliers=(), *, retried=False):
    real = BehaveResult(success=True, returncode=0, passed=len(scenarios),
                        scenarios=[BehaveScenario(n, "passed", constats_reussis=1) for n in scenarios],
                        selector_tiers=list(paliers))
    return ExecutionOutcome(module_name="m", dry_run_passed=True, real_run=real, retried=retried)


def _adaptatif(ident, scenario):
    return {"ident": ident, "tier": "adaptive", "scenario": scenario}


def test_un_vert_sans_repli_ni_retry_est_nominal():
    verdict = st.derive_verdict(_outcome(["S1"], [{"ident": "sujet", "tier": "name", "scenario": "S1"}]))

    assert verdict.confiance == st.CONFIANCE_NOMINALE
    assert verdict.scenarios[0].confiance == st.CONFIANCE_NOMINALE


def test_un_vert_obtenu_par_resolution_adaptative_est_auto_resolue_et_nomme_l_element():
    verdict = st.derive_verdict(_outcome(["S1"], [_adaptatif("sujet_renomme", "S1")]))

    assert verdict.scenarios[0].confiance == st.CONFIANCE_AUTO_RESOLUE
    assert verdict.scenarios[0].resolutions_adaptatives == ["sujet_renomme"]
    assert verdict.confiance == st.CONFIANCE_AUTO_RESOLUE


def test_un_vert_apres_retry_est_apres_retry_meme_sans_repli():
    verdict = st.derive_verdict(_outcome(["S1"], retried=True))

    assert verdict.confiance == st.CONFIANCE_APRES_RETRY


def test_le_retry_prime_sur_la_resolution_adaptative():
    verdict = st.derive_verdict(_outcome(["S1"], [_adaptatif("x", "S1")], retried=True))

    assert verdict.scenarios[0].confiance == st.CONFIANCE_APRES_RETRY


def test_falsifiable_la_resolution_d_un_scenario_ne_qualifie_pas_les_autres_mais_le_cas_prend_la_pire():
    """Sans le rattachement par scénario, S2 (nominal) serait présenté comme auto-résolu — ou S1 comme nominal."""
    verdict = st.derive_verdict(_outcome(["S1", "S2"], [_adaptatif("x", "S1")]))

    par_nom = {s.name: s.confiance for s in verdict.scenarios}
    assert par_nom == {"S1": st.CONFIANCE_AUTO_RESOLUE, "S2": st.CONFIANCE_NOMINALE}
    assert verdict.confiance == st.CONFIANCE_AUTO_RESOLUE, "un cas n'est nominal que si TOUS ses scénarios le sont"


def test_une_resolution_sans_scenario_identifie_qualifie_tous_les_scenarios():
    """Sens PRUDENT : sans nom on ne peut pas prouver qu'un scénario n'est pas concerné — jamais un faux « nominal »."""
    verdict = st.derive_verdict(_outcome(["S1", "S2"], [_adaptatif("x", "")]))

    assert [s.confiance for s in verdict.scenarios] == [st.CONFIANCE_AUTO_RESOLUE] * 2


def test_un_palier_non_adaptatif_ne_qualifie_jamais():
    """Le palier `name` (cascade déterministe) est le cas silencieux nominal — y compris hors du nom du scénario."""
    verdict = st.derive_verdict(_outcome(["S1"], [{"ident": "a", "tier": "name", "scenario": ""},
                                                  {"ident": "b", "tier": "placeholder", "scenario": "S1"}]))

    assert verdict.confiance == st.CONFIANCE_NOMINALE


def test_la_confiance_ne_change_ni_les_deux_axes_ni_le_statut_de_lecture():
    """`Réussi — à confirmer` est une qualification : les axes et `statut_de_test` restent ceux d'un vert."""
    nominal = st.derive_verdict(_outcome(["S1"]))
    a_confirmer = st.derive_verdict(_outcome(["S1"], [_adaptatif("x", "S1")], retried=True))

    assert (a_confirmer.execution_status, a_confirmer.functional_status) == (
        nominal.execution_status, nominal.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)
    assert st.statut_de_test(a_confirmer.execution_status, a_confirmer.functional_status) == st.STATUT_PASSED


def test_sans_scenario_le_cas_reste_nominal_et_un_dry_run_aussi():
    assert st.aggregate([]).confiance == st.CONFIANCE_NOMINALE
    sans_dry = ExecutionOutcome(module_name="m", dry_run_passed=False)
    assert st.derive_verdict(sans_dry).confiance == st.CONFIANCE_NOMINALE


def test_falsifiable_une_resolution_adaptative_tardive_n_est_jamais_coupee_par_le_plafond_du_sidecar(tmp_path):
    """Revue lot 05 : 250 résolutions nominales PUIS une adaptative — sous l'ancien plafond de 200 lignes elle disparaissait
    et le vert passait « nominal ». Le lecteur ne coupe jamais une ligne adaptative."""
    import json

    from testpilot.execution.behave_result import read_selector_tiers

    sidecar = tmp_path / "selector_tiers.jsonl"
    lignes = [{"ident": f"champ{i}", "tier": "name", "scenario": "S9"} for i in range(250)]
    lignes.append({"ident": "sujet_renomme", "tier": "adaptive", "scenario": "S9"})
    sidecar.write_text("\n".join(json.dumps(ligne) for ligne in lignes) + "\n", encoding="utf-8")

    paliers = read_selector_tiers(sidecar)
    verdict = st.derive_verdict(_outcome(["S9"], paliers))

    assert any(p["tier"] == "adaptive" for p in paliers)
    assert verdict.confiance == st.CONFIANCE_AUTO_RESOLUE
    assert verdict.scenarios[0].resolutions_adaptatives == ["sujet_renomme"]


def test_le_plafond_du_sidecar_reste_applique_aux_paliers_ordinaires(tmp_path):
    """Le plafond protège toujours la mémoire de dérive : seuls les repli adaptatifs (rares) le dépassent."""
    import json

    from testpilot.execution.behave_result import read_selector_tiers

    sidecar = tmp_path / "selector_tiers.jsonl"
    sidecar.write_text("\n".join(json.dumps({"ident": f"c{i}", "tier": "name", "scenario": "S"})
                                 for i in range(500)) + "\n", encoding="utf-8")

    assert len(read_selector_tiers(sidecar)) == 200
