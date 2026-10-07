"""Q3-a — le champ `hypotheses_non_verifiees` du plan technique, et la phrase de prompt qui le demande.

Contexte (mesuré le 2026-10-07, `react_loop.py`) : la « clôture » du PILIER 4 (« dis ce dont tu n'es
pas sûr ») n'était JAMAIS produite, car le dry-run vert met fin à la boucle sans tour supplémentaire.
Le champ fait voyager ce doute DANS le plan, déjà persisté en JSON (aucune migration).

Chaque garde est prouvée dans les DEUX sens (falsifiabilité) : la borne qui refuse ET le cas voisin qui
passe ; le prompt qui change quand l'interrupteur est allumé ET qui reste identique quand il est éteint.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from testpilot import config
from testpilot.generation import prompt as pm
from testpilot.generation.interrupteurs import ENV_PROMPT_HYPOTHESES
from testpilot.generation.technical_plan import (
    HYPOTHESES_CLE,
    HYPOTHESES_MAX,
    SCHEMA,
    hypotheses_depuis_plan,
    write_test_plan,
)
from testpilot.generation.tool_validation import validate_tool_input
from testpilot.generation.tools import ToolContext, dispatch


def _plan(**extra):
    plan = {"title": "Confirmation", "scenarios": [{
        "name": "Succès", "requirement_ids": ["expected_result"], "steps": [
            {"keyword": "Soit", "text": "la page ouverte", "evidence_ids": []},
            {"keyword": "Alors", "text": "la confirmation visible", "evidence_ids": []}]}]}
    plan.update(extra)
    return plan


def _ctx(tmp_path):
    ctx = ToolContext("cas", tmp_path)
    ctx.requirements = {"expected_result": "Confirmation visible"}
    ctx.shared_steps = [SimpleNamespace(keyword="given", label="la page ouverte", asserte=True),
                        SimpleNamespace(keyword="then", label="la confirmation visible",
                                        asserte=True)]
    return ctx


# ── 1. Le schéma : borné, optionnel ──────────────────────────────────────────────────────────

def test_le_champ_est_optionnel_un_plan_existant_reste_valide(tmp_path):
    """Aucun plan écrit avant Q3-a ne porte le champ : il ne doit pas devenir requis."""
    assert HYPOTHESES_CLE not in SCHEMA["required"]
    assert validate_tool_input(_plan(), SCHEMA) == ""
    assert write_test_plan(_ctx(tmp_path), _plan()).ok


def test_cinq_hypotheses_passent_six_sont_refusees():
    cinq = [f"doute {i}" for i in range(HYPOTHESES_MAX)]
    assert validate_tool_input(_plan(**{HYPOTHESES_CLE: cinq}), SCHEMA) == ""
    erreur = validate_tool_input(_plan(**{HYPOTHESES_CLE: cinq + ["de trop"]}), SCHEMA)
    assert "5 éléments au plus" in erreur


def test_une_hypothese_trop_longue_ou_vide_est_refusee():
    assert validate_tool_input(_plan(**{HYPOTHESES_CLE: ["x" * 200]}), SCHEMA) == ""
    assert "caractères au plus" in validate_tool_input(
        _plan(**{HYPOTHESES_CLE: ["x" * 201]}), SCHEMA)
    assert "texte vide" in validate_tool_input(_plan(**{HYPOTHESES_CLE: ["   "]}), SCHEMA)


def test_le_type_est_controle():
    assert validate_tool_input(_plan(**{HYPOTHESES_CLE: "un doute"}), SCHEMA)  # str, pas liste
    assert validate_tool_input(_plan(**{HYPOTHESES_CLE: [3]}), SCHEMA)         # entier, pas texte


def test_dispatch_refuse_six_hypotheses_sans_rien_ecrire(tmp_path):
    """Le refus passe par le VRAI chemin de l'agent (`dispatch`), pas seulement par le validateur."""
    ctx = _ctx(tmp_path)
    resultat = dispatch("write_test_plan", _plan(**{HYPOTHESES_CLE: ["a"] * 6}), ctx)
    assert not resultat.ok and "5 éléments au plus" in resultat.observation
    assert not (tmp_path / "cas.feature").exists()
    assert ctx.technical_plan == {}


# ── 2. Conservé dans le plan persisté, relu, jamais écrit dans le Gherkin ────────────────────

def test_le_champ_est_conserve_dans_le_plan_persiste_et_relu(tmp_path):
    ctx = _ctx(tmp_path)
    plan = _plan(**{HYPOTHESES_CLE: ["Le texte exact du message n'a pas été observé."]})
    assert write_test_plan(ctx, plan).ok
    persiste = json.dumps(ctx.technical_plan, ensure_ascii=False)   # ce que `agent.py` écrit en base
    assert hypotheses_depuis_plan(persiste) == ["Le texte exact du message n'a pas été observé."]
    assert hypotheses_depuis_plan(ctx.technical_plan) == hypotheses_depuis_plan(persiste)


def test_l_hypothese_n_entre_jamais_dans_le_gherkin(tmp_path):
    """Information pour l'humain : un doute de l'agent n'est ni un step ni un commentaire du test."""
    ctx = _ctx(tmp_path)
    assert write_test_plan(ctx, _plan(**{HYPOTHESES_CLE: ["SECRET-DOUTE"]})).ok
    assert "SECRET-DOUTE" not in (tmp_path / "cas.feature").read_text(encoding="utf-8")


def test_hypotheses_depuis_plan_est_pure_et_tolerante():
    assert hypotheses_depuis_plan(_plan()) == []                       # plan ancien
    assert hypotheses_depuis_plan({}) == []
    assert hypotheses_depuis_plan("") == []
    assert hypotheses_depuis_plan("pas du json") == []
    assert hypotheses_depuis_plan("[1, 2]") == []                      # JSON valide, mauvais type
    assert hypotheses_depuis_plan(None) == []
    assert hypotheses_depuis_plan({HYPOTHESES_CLE: "texte"}) == []
    assert hypotheses_depuis_plan({HYPOTHESES_CLE: ["a", "", "  ", 3, None, " b "]}) == ["a", "b"]
    # Même borne qu'à l'écriture : on n'affiche jamais plus que ce que l'outil aurait accepté.
    assert len(hypotheses_depuis_plan({HYPOTHESES_CLE: [str(i) for i in range(9)]})) == 5


def test_la_lecture_ne_modifie_pas_le_plan():
    plan = _plan(**{HYPOTHESES_CLE: [" a "]})
    avant = copy.deepcopy(plan)
    hypotheses_depuis_plan(plan)
    assert plan == avant


def test_aucun_module_de_verdict_ne_lit_les_hypotheses():
    """Garde structurelle (décision 0015) : le texte de l'agent n'est jamais une source de vérité.
    Si un module de décision se met à lire ce champ, ce test le dit."""
    racine = Path(config.PROMPTS_DIR).parent.parent          # src/testpilot
    modules = [racine / "verdict", racine / "execution", racine / "guardrails",
               racine / "generation" / "repair_agent.py",
               racine / "api" / "services" / "repair_service.py"]
    fichiers = []
    for cible in modules:
        assert cible.exists(), f"{cible} a bougé : mettre à jour cette garde"
        fichiers += [cible] if cible.is_file() else list(cible.rglob("*.py"))
    assert len(fichiers) > 5, "garde du garde : trop peu de fichiers examinés"
    for chemin in fichiers:
        assert HYPOTHESES_CLE not in chemin.read_text(encoding="utf-8"), (
            f"{chemin} lit `{HYPOTHESES_CLE}` : un doute de l'agent ne décide de rien")


# ── 3. Le prompt : identique éteint, une phrase de plus allumé ───────────────────────────────

# Ce que `build_system_prompt` ajoutait AVANT Q3-a après le fichier (recopié ici, volontairement :
# la comparaison est avec le passé, pas avec le code courant).
_QUEUE_HISTORIQUE = (
    "\n\nChaque nom de champ utilisé doit être cité à l'identique dans le crawl fourni "
    "ou dans le résultat d'un appel inspect_schema(modèle) / inspect_page_form(URL). "
    "Avant d'utiliser un champ absent du crawl, inspecte sa source. Le registre est "
    "alimenté uniquement par les résultats des outils, jamais par tes déclarations. "
    "Un champ absent du crawl et du registre sera signalé à la relecture."
)


def _fichier() -> str:
    return (Path(config.PROMPTS_DIR) / "system_prompt.md").read_text(encoding="utf-8")


def test_prompt_eteint_est_identique_octet_pour_octet(monkeypatch):
    monkeypatch.delenv(ENV_PROMPT_HYPOTHESES, raising=False)
    assert pm.build_system_prompt(None, None) == _fichier() + _QUEUE_HISTORIQUE


def test_prompt_allume_ajoute_exactement_une_phrase_dans_le_pilier_4(monkeypatch):
    monkeypatch.delenv(ENV_PROMPT_HYPOTHESES, raising=False)
    eteint = pm.build_system_prompt(None, None)
    monkeypatch.setenv(ENV_PROMPT_HYPOTHESES, "1")
    allume = pm.build_system_prompt(None, None)

    assert allume != eteint
    assert allume.count(pm._PHRASE_HYPOTHESES) == 1
    assert "hypotheses_non_verifiees" in allume and "hypotheses_non_verifiees" not in eteint
    # Un seul ajout, rien d'autre : retirer la phrase (et son saut de ligne) rend le prompt éteint.
    assert allume.replace("\n\n" + pm._PHRASE_HYPOTHESES, "") == eteint
    # Et elle est bien DANS le PILIER 4, avant « OPTIMISATION DES COÛTS ».
    assert (allume.index("## PILIER 4") < allume.index(pm._PHRASE_HYPOTHESES)
            < allume.index("## OPTIMISATION DES COÛTS"))


@pytest.mark.parametrize("valeur", ["0", "", "non", "false"])
def test_une_valeur_fausse_n_allume_pas(monkeypatch, valeur):
    monkeypatch.setenv(ENV_PROMPT_HYPOTHESES, valeur)
    assert pm.build_system_prompt(None, None) == _fichier() + _QUEUE_HISTORIQUE


def test_une_ancre_disparue_leve_au_lieu_de_mesurer_un_prompt_sans_la_phrase(monkeypatch):
    monkeypatch.setenv(ENV_PROMPT_HYPOTHESES, "1")
    monkeypatch.setattr(pm, "_ANCRE_CLOTURE", "ancre qui n'existe pas")
    with pytest.raises(RuntimeError, match="PILIER 4"):
        pm.build_system_prompt(None, None)
