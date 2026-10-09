"""Lot VH-04, étape 8 — le banc relève les refus des gardes d'écriture et n'achète plus une réparation que le produit refuse.

- Base-4 (2026-10-09) : deux générations sur 30 ont échoué, l'une à 0,54 $, sans qu'on sache si les gardes d'écriture
  faisaient tourner l'agent en rond : chaque refus est maintenant consigné (outil, code) et compté par essai dans le rapport.
- Base-4 : 0,24 $ de réparations tentées sur des échecs sous un « Alors », que le produit envoie à un humain (VH-03).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))
import banc_agents as ba  # noqa: E402

from testpilot.generation.tools import ToolContext  # noqa: E402
from testpilot.generation.tools import write as w  # noqa: E402


def test_les_noms_de_la_variable_sont_d_accord():
    assert ba._REFUS_ECRITURE_FILE_ENV == w.REFUS_ECRITURE_FILE_ENV


def test_un_refus_d_ecriture_est_consigne_avec_son_code(tmp_path, monkeypatch):
    fichier = tmp_path / "refus.jsonl"
    monkeypatch.setenv(w.REFUS_ECRITURE_FILE_ENV, str(fichier))
    ctx = ToolContext(module_name="m", generated_dir=tmp_path)

    w.write_steps_file(ctx, "def (:\n")                                   # syntaxe invalide
    w.write_steps_file(ctx, "from behave import when\n\n@when('a')\ndef a(context):\n    global x\n")  # Python interdit
    w.write_steps_file(ctx, "from behave import when\n\n@when('b')\ndef b(context):\n    context.page.reload()\n")  # accepté

    lignes = [json.loads(l) for l in fichier.read_text(encoding="utf-8").splitlines()]
    assert [l["outil"] for l in lignes] == ["write_steps_file", "write_steps_file"]
    assert lignes[0]["code"] == "SYNTAX_ERROR" and all(l["code"] for l in lignes)
    assert ba.lire_refus_d_ecriture(fichier)["SYNTAX_ERROR"] == 1


def test_sans_variable_rien_n_est_ecrit(tmp_path, monkeypatch):
    monkeypatch.delenv(w.REFUS_ECRITURE_FILE_ENV, raising=False)
    w.write_steps_file(ToolContext(module_name="m", generated_dir=tmp_path), "def (:\n")

    assert not list(tmp_path.glob("*.jsonl"))


def test_un_fichier_absent_ou_illisible_ne_fait_rien_tomber(tmp_path):
    assert ba.lire_refus_d_ecriture(tmp_path / "absent.jsonl") == {}
    (tmp_path / "x.jsonl").write_text('{"code": "A"}\npas du json\n', encoding="utf-8")
    assert ba.lire_refus_d_ecriture(tmp_path / "x.jsonl") == {"A": 1, "ILLISIBLE": 1}


# ── Règle de réparation du produit ────────────────────────────────────────────────────────────────────────


def _trace(raw: str, step_type: str) -> dict:
    return {"scenarios": [], "echecs": [{"scenario_name": "S", "step_text": "x", "raw": raw, "traceback_summary": "",
                                         "page_url": "", "step_type": step_type}]}


@pytest.mark.parametrize("raw, step_type", [
    ("playwright._impl._errors.TimeoutError: Locator.wait_for: Timeout 8000ms exceeded.", "then"),   # sous un Alors
    ("ASSERT FAILED: Le texte « 129,51 » n'est pas affiché", "then"),                               # vérification
    ("_base_helpers.ErreurServeur5xxError: 500", "when"),                                             # vrai bug
])
def test_falsifiable_le_banc_ne_paie_pas_une_reparation_que_le_produit_refuse(raw, step_type):
    assert ba.decision_du_circuit(_trace(raw, step_type)).startswith("circuit du produit")


def test_un_echec_d_action_reste_reparable():
    trace = _trace("_base_helpers.ElementIntrouvableError: Bouton 'Nouveau client' : aucun élément actionnable", "when")

    assert ba.decision_du_circuit(trace) == ""


def test_la_trace_porte_le_type_du_step():
    from types import SimpleNamespace

    echec = SimpleNamespace(scenario_name="S", step_text="x", raw="r", traceback_summary="", page_url="", step_type="then")
    trace = ba.trace_de_l_echec(SimpleNamespace(real_run=SimpleNamespace(scenarios=[], failures=[echec])))

    assert trace["echecs"][0]["step_type"] == "then"
