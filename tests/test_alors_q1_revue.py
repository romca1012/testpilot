"""Q1 — corrections de la revue indépendante du 2026-10-07 (exemption forgeable, compteur trop généreux, libellé faux,
contrôle qui disparaît sans trace, doublures infidèles à Behave). Chaque test prouve les DEUX sens.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.execution import behave_result
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.generation.tools import ToolContext
from testpilot.generation.tools import write as write_tools
from testpilot.verdict import defect_origin as origin
from testpilot.verdict import defect_taxonomy as dt
from testpilot.verdict import explication

sys.path.insert(0, str(config.STEPS_LIBRARY_DIR))
import _base_helpers as h  # noqa: E402


def _charger_environment():
    spec = importlib.util.spec_from_file_location("environment_q1_revue", config.BEHAVE_RUNTIME_DIR / "environment.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["environment_q1_revue"] = module
    spec.loader.exec_module(module)
    return module


def _lignes(chemin: Path):
    return [json.loads(ligne) for ligne in chemin.read_text(encoding="utf-8").splitlines() if ligne.strip()] \
        if chemin.exists() else []


def _step(statut="passed", type_="then", nom="un Alors"):
    return SimpleNamespace(step_type=type_, status=SimpleNamespace(name=statut), name=nom)


def _contexte(fonction, avant):
    """Le `context` de Behave : le registre du runner retrouve la fonction du step (pas de `step.match`)."""
    return SimpleNamespace(
        _tp_constats_avant_step=avant,
        _runner=SimpleNamespace(step_registry=SimpleNamespace(find_match=lambda _s: SimpleNamespace(func=fonction))))


# ── 1. Le compteur ne compte que les constats RÉUSSIS ─────────────────────────────────────────────

def test_un_constat_echoue_n_est_jamais_compte_comme_reussi():
    avant = h.nombre_de_constats_reussis()

    with pytest.raises(AssertionError):
        h.constater(False, "faux")

    assert h.nombre_de_constats_reussis() == avant


def test_un_constat_reussi_est_compte():
    avant = h.nombre_de_constats_reussis()

    h.constater(True, "vrai")

    assert h.nombre_de_constats_reussis() == avant + 1


def test_le_decorateur_constat_compte_seulement_le_succes():
    @h.constat
    def ok():
        return None

    @h.constat
    def ko():
        raise AssertionError("faux")

    avant = h.nombre_de_constats_reussis()
    ok()
    assert h.nombre_de_constats_reussis() == avant + 1
    with pytest.raises(AssertionError):
        ko()
    assert h.nombre_de_constats_reussis() == avant + 1


def test_un_alors_qui_avale_son_propre_echec_est_signale(tmp_path, monkeypatch):
    """Revue (b) : `try: constater(...) except AssertionError: pass` — avant, le constat ÉCHOUÉ comptait comme
    « a constaté » et le vide passait."""
    monkeypatch.setenv("TP_GENERATED_STEPS_FILE", "cas_steps.py")
    sidecar = tmp_path / "constats.jsonl"
    monkeypatch.setenv(h.CONSTATS_FILE_ENV, str(sidecar))
    env = _charger_environment()
    h.definir_etat_constat(scenario="S", step_type="then")
    contexte = _contexte(lambda c: None, h.nombre_de_constats_reussis())

    try:
        h.constater(False, "faux")
    except AssertionError:
        pass  # l'Alors avale l'échec
    env.after_step(contexte, _step())

    assert [ligne.get("sans_constat") for ligne in _lignes(sidecar) if ligne.get("sans_constat")] == [True]


# ── 2. L'exemption ne s'accorde jamais à une fonction du fichier GÉNÉRÉ ──────────────────────────

def _fonction_marquee(nom_fichier: str):
    """Une fonction marquée `@non_assertif`, dont le code est attribué à `nom_fichier`."""
    code = compile("def f(context):\n    return None\n", str(Path("/x") / nom_fichier), "exec")
    espace: dict = {}
    exec(code, espace)  # noqa: S102 — fabrique une fonction « venue » de ce fichier, jamais du code d'un tiers
    fonction = espace["f"]
    fonction._tp_non_assertif = True
    return fonction


def test_une_fonction_du_socle_marquee_est_exemptee(monkeypatch):
    monkeypatch.setenv("TP_GENERATED_STEPS_FILE", "cas_steps.py")
    env = _charger_environment()

    assert env._est_exempte_non_assertive(_fonction_marquee("_generic_steps.py")) is True


def test_une_fonction_du_fichier_genere_n_est_jamais_exemptee(monkeypatch):
    """Revue (d) : même marquée, une fonction du fichier de steps GÉNÉRÉ ne s'exempte pas elle-même."""
    monkeypatch.setenv("TP_GENERATED_STEPS_FILE", "cas_steps.py")
    env = _charger_environment()

    assert env._est_exempte_non_assertive(_fonction_marquee("cas_steps.py")) is False


def test_sans_nom_de_fichier_genere_connu_aucune_exemption(monkeypatch):
    monkeypatch.delenv("TP_GENERATED_STEPS_FILE", raising=False)
    env = _charger_environment()

    assert env._est_exempte_non_assertive(_fonction_marquee("_generic_steps.py")) is False


def test_une_fonction_non_marquee_n_est_pas_exemptee(monkeypatch):
    monkeypatch.setenv("TP_GENERATED_STEPS_FILE", "cas_steps.py")
    env = _charger_environment()
    fonction = _fonction_marquee("_generic_steps.py")
    del fonction._tp_non_assertif

    assert env._est_exempte_non_assertive(fonction) is False


def test_le_runner_designe_le_fichier_genere_au_sous_processus(tmp_path):
    env = BehaveRunner()._subprocess_env(tmp_path, "cas_42")

    assert env["TP_GENERATED_STEPS_FILE"] == "cas_42_steps.py"
    assert behave_result.GENERATED_STEPS_FILE_ENV == "TP_GENERATED_STEPS_FILE"  # accord avec environment.py
    assert "TP_GENERATED_STEPS_FILE" not in BehaveRunner()._subprocess_env(tmp_path)  # inconnu : jamais inventé


# ── 3. Le garde d'écriture refuse le mécanisme de preuve ─────────────────────────────────────────

_ENTETE = "from behave import then\nfrom _base_helpers import constater\n"


def _ecrire(tmp_path, code):
    ctx = ToolContext(module_name="m", generated_dir=tmp_path, connector=None)
    return write_tools.write_steps_file(ctx, code)


@pytest.mark.parametrize("code", [
    # import du marqueur + décorateur
    _ENTETE + "from _base_helpers import non_assertif\n@then('x')\n@non_assertif\n"
              "def s(context):\n    constater(True, 'm')\n",
    # pose directe de l'attribut
    _ENTETE + "@then('x')\ndef s(context):\n    s._tp_non_assertif = True\n    constater(True, 'm')\n",
    # forme par chaîne
    _ENTETE + "@then('x')\ndef s(context):\n    setattr(s, '_tp_non_assertif', True)\n    constater(True, 'm')\n",
    # compteur
    _ENTETE + "import _base_helpers\n@then('x')\ndef s(context):\n    _base_helpers._COMPTEUR_CONSTATS['n'] += 1\n"
              "    constater(True, 'm')\n",
])
def test_un_step_genere_ne_touche_pas_au_mecanisme_de_preuve(tmp_path, code):
    resultat = _ecrire(tmp_path, code)

    assert resultat.ok is False
    assert "MECANISME_RESERVE" in resultat.observation
    assert not (tmp_path / "m_steps.py").exists()


def test_un_step_genere_ordinaire_reste_accepte(tmp_path):
    """Sens inverse : le garde ne devient pas un refus systématique."""
    resultat = _ecrire(tmp_path, _ENTETE + "@then('une vérification propre')\ndef s(context):\n"
                                           "    constater('ok' in context.page.inner_text('body'), 'absent')\n")

    assert resultat.ok is True


# ── 4. Un contrôle impossible laisse une trace (jamais un silence) ───────────────────────────────

def test_repere_absent_le_controle_impossible_est_consigne(tmp_path, monkeypatch):
    monkeypatch.setenv("TP_GENERATED_STEPS_FILE", "cas_steps.py")
    sidecar = tmp_path / "constats.jsonl"
    monkeypatch.setenv(h.CONSTATS_FILE_ENV, str(sidecar))
    env = _charger_environment()
    h.definir_etat_constat(scenario="S", step_type="then")

    env.after_step(_contexte(lambda c: None, None), _step())  # `before_step` n'a pas posé de repère

    assert [(ligne["sans_constat"], ligne["raison"]) for ligne in _lignes(sidecar)] == [(True, "controle_impossible")]


def test_une_erreur_dans_le_controle_est_consignee_sans_remonter(tmp_path, monkeypatch):
    """Un contexte qui lève : avant, la branche `except` n'était jamais exercée (test « jamais fatal » vide)."""
    monkeypatch.setenv("TP_GENERATED_STEPS_FILE", "cas_steps.py")
    sidecar = tmp_path / "constats.jsonl"
    monkeypatch.setenv(h.CONSTATS_FILE_ENV, str(sidecar))
    env = _charger_environment()
    h.definir_etat_constat(scenario="S", step_type="then")

    class _Piege:
        @property
        def _runner(self):
            raise RuntimeError("registre indisponible")

    env.after_step(_Piege(), _step())  # ne lève pas

    assert [ligne["raison"] for ligne in _lignes(sidecar)] == ["controle_impossible"]


# ── 5. La fonction du step est retrouvée par un VRAI registre Behave ──────────────────────────────

def test_fonction_du_step_avec_un_vrai_registre_behave():
    from behave.model import Step
    from behave.step_registry import StepRegistry

    registre = StepRegistry()

    def mon_step(context):
        return None

    registre.add_step_definition("then", "j'attends autre chose", mon_step)
    step = Step("f.feature", 1, "Alors", "then", "j'attends autre chose")
    env = _charger_environment()
    contexte = SimpleNamespace(_runner=SimpleNamespace(step_registry=registre))

    assert not hasattr(step, "match"), "Behave 1.3.3 ne pose pas `step.match` (mesuré)"
    assert env._fonction_du_step(contexte, step) is mon_step


# ── 6. Libellé, classement et note de la cause dédiée ────────────────────────────────────────────

def test_la_cause_alors_sans_constat_a_son_libelle_et_n_ouvre_aucune_reparation():
    assert dt.LABELS[dt.ALORS_SANS_CONSTAT] == "Un résultat attendu n'a rien vérifié"
    assert dt.LABELS[dt.ALORS_SANS_CONSTAT] != dt.LABELS[dt.AUCUN_CONSTAT]
    assert dt.ALORS_SANS_CONSTAT in dt.CATEGORIES
    assert origin._ORIGIN_BY_CAUSE[dt.ALORS_SANS_CONSTAT] == origin.INDETERMINE


def test_la_note_ne_pretend_pas_que_rien_n_a_ete_constate():
    """Un AUTRE `Alors` a constaté : la note d'`aucun_constat` (« rien n'a été constaté ») serait fausse."""
    assert "aucune vérification ne s'est exécutée" not in explication._NOTE_ALORS_SANS_CONSTAT
    assert "a bien été vérifiée" in explication._NOTE_ALORS_SANS_CONSTAT
    assert "aucune vérification ne s'est exécutée" in explication._NOTE_AUCUN_CONSTAT  # l'ancienne reste vraie
