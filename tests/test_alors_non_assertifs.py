"""Q1 (D16, D17) — la preuve PAR `Alors`, sans navigateur.

Trois mécanismes, chacun prouvé dans les DEUX sens (falsifiabilité) :

1. le VERDICT : un `Alors` assertif passé sans constat empêche le `conforme`, même si un autre constate ;
2. le CATALOGUE et `write_test_plan` : une attente n'est pas une assertion ;
3. le HOOK d'exécution `after_step` : il consigne un `Alors` assertif vide, jamais un step exempté.

La preuve de bout en bout avec un vrai navigateur vit dans `test_conformite_alors_par_alors.py`.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from testpilot import config
from testpilot.execution.behave_result import (
    BehaveResult,
    BehaveScenario,
    rattacher_constats,
    read_constats,
)
from testpilot.execution.executor import ExecutionOutcome
from testpilot.generation import steps_library
from testpilot.generation.technical_plan import write_test_plan
from testpilot.generation.tools import ToolContext
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict import status as st

_LIB = config.STEPS_LIBRARY_DIR
sys.path.insert(0, str(_LIB))
_ATTENTE = "j'attends la soumission du formulaire"


def _outcome(scenarios):
    reel = BehaveResult(success=True, returncode=0, scenarios=scenarios)
    return ExecutionOutcome(module_name="m", dry_run_passed=True, real_run=reel)


# ── 1. Le verdict ────────────────────────────────────────────────────────────────────────────

def test_un_alors_assertif_vide_empeche_le_conforme_meme_si_un_autre_constate():
    scenario = BehaveScenario("[Nominal]", "passed", constats_reussis=1,
                              alors_sans_constat=["la vérification dans une branche non prise"])

    v = st.derive_verdict(_outcome([scenario]))

    assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_INDETERMINE)
    assert v.scenarios[0].cause_category == dt.AUCUN_CONSTAT
    assert v.scenarios[0].step_text == "la vérification dans une branche non prise"  # trace, jamais critère


def test_sans_alors_vide_le_scenario_prouve_reste_conforme():
    """Sens inverse : la règle ne doit pas devenir systématique."""
    v = st.derive_verdict(_outcome([BehaveScenario("[Nominal]", "passed", constats_reussis=2,
                                                   alors_sans_constat=[])]))

    assert (v.execution_status, v.functional_status) == (st.EXEC_SUCCESS, st.FUNC_CONFORME)


def test_sans_mecanisme_la_regle_ne_s_applique_pas():
    """`None` = dry-run, résultat construit à la main, exécution antérieure : comportement historique."""
    v = st.derive_verdict(_outcome([BehaveScenario("[Nominal]", "passed", constats_reussis=1,
                                                   alors_sans_constat=None)]))

    assert v.functional_status == st.FUNC_CONFORME


def test_un_alors_vide_n_efface_jamais_un_echec_reel():
    """Un `failed` reste `non_conforme` : la règle ne s'applique qu'à un scénario passé."""
    from testpilot.execution.behave_result import BehaveFailure

    echoue = BehaveScenario("[Erreur]", "failed", error="ASSERT FAILED", constats_reussis=0,
                            alors_sans_constat=["x"])
    v = st.derive_verdict(ExecutionOutcome(
        module_name="m", dry_run_passed=True,
        real_run=BehaveResult(success=False, returncode=1, scenarios=[echoue],
                              failures=[BehaveFailure("[Erreur]", "", "assertion", "",
                                                      raw="ASSERT FAILED: x", step_type="then")])))

    assert v.functional_status == st.FUNC_NON_CONFORME


def test_le_sidecar_rattache_les_alors_vides_a_leur_scenario(tmp_path):
    chemin = tmp_path / "constats.jsonl"
    chemin.write_text("\n".join(json.dumps(ligne) for ligne in [
        {"scenario": "A", "step_type": "then", "ok": True, "source": ""},
        {"scenario": "A", "step_type": "then", "ok": None, "sans_constat": True, "step": "un Alors vide"},
        {"scenario": "B", "step_type": "then", "ok": True, "source": ""},
    ]) + "\n", encoding="utf-8")
    resultat = BehaveResult(success=True, returncode=0,
                            scenarios=[BehaveScenario("A", "passed"), BehaveScenario("B", "passed")])

    rattacher_constats(resultat, read_constats(chemin))

    a, b = resultat.scenarios
    assert a.constats_reussis == 1, "la ligne `sans_constat` n'est JAMAIS un constat réussi"
    assert a.alors_sans_constat == ["un Alors vide"]
    assert b.alors_sans_constat == []


# ── 2. Catalogue et write_test_plan ──────────────────────────────────────────────────────────

def _fonctions_then_ou_step(fichier: Path):
    arbre = ast.parse(fichier.read_text(encoding="utf-8"))
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.FunctionDef):
            continue
        noms = set()
        for deco in noeud.decorator_list:
            cible = deco.func if isinstance(deco, ast.Call) else deco
            noms.add(cible.id if isinstance(cible, ast.Name) else getattr(cible, "attr", ""))
        yield noeud, noms


def test_l_ensemble_des_then_sans_constat_est_exactement_l_ensemble_des_steps_marques():
    """Accord AST ↔ marqueur (D17) : deux mécanismes, une seule vérité. Un nouveau `@then` qui ne
    peut constater DOIT être marqué ; un marqueur posé sur un step qui constate est une erreur."""
    constatent = steps_library.helpers_qui_constatent(_LIB)
    sans_constat, marques = set(), set()
    for fichier in sorted(_LIB.rglob("*.py")):
        if fichier.name.startswith("__"):
            continue
        for fonction, decorateurs in _fonctions_then_ou_step(fichier):
            cle = f"{fichier.relative_to(_LIB).as_posix()}::{fonction.name}"
            if "non_assertif" in decorateurs:
                marques.add(cle)
            if decorateurs & {"then", "step"}:
                appels = {steps_library._nom_appele(n) for n in ast.walk(fonction) if isinstance(n, ast.Call)}
                if not (appels & constatent):
                    sans_constat.add(cle)

    assert sans_constat == marques, (
        f"@then sans constat non déclarés : {sorted(sans_constat - marques)} ; "
        f"marqueurs sur un step qui constate : {sorted(marques - sans_constat)}")
    assert "generic/_generic_steps.py::step_wait_form" in marques


def test_le_catalogue_reel_marque_l_attente_non_assertive_et_les_autres_assertifs():
    catalogue = steps_library.catalogue()

    attente = [s for s in catalogue if s.label == _ATTENTE and s.keyword == "then"]
    assert attente and not attente[0].asserte
    autres = [s for s in catalogue if s.keyword == "then" and s.label != _ATTENTE]
    assert autres and all(s.asserte for s in autres)


def _contexte(tmp_path, then_steps):
    ctx = ToolContext("cas", tmp_path)
    ctx.requirements = {"expected_result": "Confirmation"}
    ctx.shared_steps = [SimpleNamespace(keyword="given", label="la page ouverte", asserte=True),
                        *[SimpleNamespace(keyword="then", label=lbl, asserte=a) for lbl, a in then_steps]]
    return ctx


def _plan(*alors):
    return {"title": "T", "scenarios": [{"name": "S", "requirement_ids": ["expected_result"], "steps": [
        {"keyword": "Soit", "text": "la page ouverte", "evidence_ids": []},
        *[{"keyword": "Alors" if i == 0 else "Et", "text": t, "evidence_ids": []}
          for i, t in enumerate(alors)]]}]}


def test_un_plan_dont_le_seul_alors_est_une_attente_est_refuse(tmp_path):
    ctx = _contexte(tmp_path, [(_ATTENTE, False)])

    resultat = write_test_plan(ctx, _plan(_ATTENTE))

    assert not resultat.ok
    assert "attente" in resultat.observation.lower() and "ne vérifie rien" in resultat.observation
    assert not list(tmp_path.iterdir()), "rien n'est écrit"


def test_un_plan_avec_une_attente_et_une_vraie_assertion_est_accepte(tmp_path):
    """Sens inverse : l'attente reste utilisable, elle ne compte simplement pas comme preuve."""
    ctx = _contexte(tmp_path, [("la confirmation visible", True), (_ATTENTE, False)])

    assert write_test_plan(ctx, _plan("la confirmation visible", _ATTENTE)).ok


def test_un_step_sans_information_asserte_reste_compte_comme_assertion(tmp_path):
    """Doublures d'avant Q1 (sans champ `asserte`) : comportement historique inchangé."""
    ctx = ToolContext("cas", tmp_path)
    ctx.requirements = {"expected_result": "Confirmation"}
    ctx.shared_steps = [SimpleNamespace(keyword="given", label="la page ouverte"),
                        SimpleNamespace(keyword="then", label="la confirmation visible")]

    assert write_test_plan(ctx, _plan("la confirmation visible")).ok


# ── 3. Le hook d'exécution ───────────────────────────────────────────────────────────────────

def _charger_environment():
    spec = importlib.util.spec_from_file_location("environment_q1", config.BEHAVE_RUNTIME_DIR / "environment.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["environment_q1"] = module
    spec.loader.exec_module(module)
    return module


def _step(type_="then", statut="passed", non_assertif=False, nom="un Alors"):
    """Un step tel que Behave 1.3.3 le fournit à `after_step` : SANS attribut `match` (mesuré)."""
    return SimpleNamespace(step_type=type_, status=SimpleNamespace(name=statut), name=nom,
                           _non_assertif=non_assertif)


def _contexte_runner(constats_avant, step_attendu=None):
    """Le `context` de Behave : le registre du runner retrouve la fonction du step."""
    def find_match(step):
        fonction = lambda context: None  # noqa: E731
        if getattr(step, "_non_assertif", False):
            fonction._tp_non_assertif = True
        return SimpleNamespace(func=fonction)

    return SimpleNamespace(_tp_constats_avant_step=constats_avant,
                           _runner=SimpleNamespace(step_registry=SimpleNamespace(find_match=find_match)))


def _lignes(chemin: Path):
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne.strip()] \
        if chemin.exists() else []


def test_after_step_consigne_un_alors_assertif_passe_sans_constat(tmp_path, monkeypatch):
    import _base_helpers as h
    env = _charger_environment()
    sidecar = tmp_path / "constats.jsonl"
    monkeypatch.setenv(h.CONSTATS_FILE_ENV, str(sidecar))
    h.definir_etat_constat(scenario="S", step_type="then")
    contexte = _contexte_runner(h.nombre_de_constats())

    env.after_step(contexte, _step())

    assert _lignes(sidecar) == [{"scenario": "S", "step_type": "then", "ok": None, "sans_constat": True,
                                 "step": "un Alors"}]


def test_after_step_ne_dit_rien_si_le_step_a_constate(tmp_path, monkeypatch):
    import _base_helpers as h
    env = _charger_environment()
    sidecar = tmp_path / "constats.jsonl"
    monkeypatch.setenv(h.CONSTATS_FILE_ENV, str(sidecar))
    h.definir_etat_constat(scenario="S", step_type="then")
    contexte = _contexte_runner(h.nombre_de_constats())

    h.constater(True, "ok")  # le step constate…
    env.after_step(contexte, _step())

    assert [ligne.get("sans_constat") for ligne in _lignes(sidecar)] == [None], "…seul le constat est consigné"


def test_after_step_exempte_un_step_non_assertif_un_given_et_un_echec(tmp_path, monkeypatch):
    import _base_helpers as h
    env = _charger_environment()
    sidecar = tmp_path / "constats.jsonl"
    monkeypatch.setenv(h.CONSTATS_FILE_ENV, str(sidecar))
    h.definir_etat_constat(scenario="S", step_type="then")
    contexte = _contexte_runner(h.nombre_de_constats())

    env.after_step(contexte, _step(non_assertif=True))   # attente déclarée (D17)
    env.after_step(contexte, _step(type_="given"))       # un Soit n'a pas à constater
    env.after_step(contexte, _step(statut="failed"))     # un échec est déjà traité par le verdict

    assert _lignes(sidecar) == []


def test_after_step_n_est_jamais_fatal(tmp_path):
    env = _charger_environment()

    env.after_step(SimpleNamespace(), SimpleNamespace(step_type="then", status=None))  # ne lève pas
