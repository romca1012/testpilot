"""Agent de RÉPARATION — propose UNE correction à partir d'un échec réel (décision 0014).

⚠️ Design (b), arbitré : **l'agent ne pilote pas la boucle**. Il reçoit un échec observé, propose
une correction, et rend la main. C'est l'orchestrateur qui exécute, qui décide s'il faut retenter
et quand s'arrêter (`guardrails/repair_circuit`). Lui donner un outil `run_behave` remettrait le
contrôle dans les mains du composant qu'on encadre — exactement ce que `0012` invite à ne pas
faire, puisque le circuit lit un texte que l'agent écrit lui-même.

Réutilise `run_loop` : l'agent réécrit, le **dry-run valide le correctif** (il parse encore ?),
et seulement ensuite l'orchestrateur le rejoue pour de vrai. Un correctif qui ne parse même pas
est ainsi rattrapé sans coûter une exécution réelle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from testpilot import config
from testpilot.generation import steps_library
from testpilot.generation.interfaces import Connector, DryRunner
from testpilot.generation.react_loop import run_loop
from testpilot.generation.state import AgentState
from testpilot.generation.tools import ToolContext
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)

_REPAIR_PROMPT_PATH = config.PROMPTS_DIR / "repair_prompt.md"


@dataclass
class RepairProposal:
    """Ce que l'agent propose. `changed` est faux s'il n'a rien réécrit — un aveu utile."""

    changed: bool
    feature_content: str = ""
    steps_content: str = ""
    summary: str = ""          # ce que l'agent dit avoir fait — montré à un humain tel quel
    # Coût de CETTE tentative seule — jamais le cumul du tracker. Le tracker est désormais
    # PARTAGÉ entre les tentatives d'un cas (pour que le plafond borne le cas, pas l'appel) :
    # rendre `total_cost` ferait compter la tentative 1 une fois de plus à chaque tentative
    # suivante, et le ledger comme la session seraient faux à la hausse.
    cost_usd: float = 0.0
    stopped_reason: str = ""


def build_repair_prompt(connector: Connector | None = None) -> str:
    """Prompt de réparation + catalogue des steps + règles du connecteur.

    Même catalogue que la génération : un correctif qui réinvente un step partagé serait rejeté
    à l'écriture (`0003`), et l'agent doit voir ce qu'il peut réutiliser — y compris les notes
    qui disent ce qu'un step FAIT (`0012`).
    """
    base = _REPAIR_PROMPT_PATH.read_text(encoding="utf-8")
    catalogue = steps_library.as_prompt_section(steps_library.catalogue())
    if catalogue:
        base += "\n\n---\n\n## Steps partagés disponibles (à réutiliser)\n\n" + catalogue
    rules = connector.rules() if connector else ""
    if rules:
        base += "\n\n---\n\n## Connecteur actif\n\n" + rules
    return base


def _failure_report(scenarios, failures, steps_content: str = "") -> str:
    """L'échec observé, tel qu'on le donne à l'agent. Factuel : ce qui s'est passé, rien de plus.

    On ne lui souffle PAS de diagnostic : la taxonomie classe par mots-clés du message (`0012`),
    et lui transmettre sa propre conclusion l'enfermerait dans une piste qui peut être fausse —
    le cas 6 l'a montré (« rôle manquant » alors que la session navigateur était anonyme).
    """
    lignes = ["# Échec observé lors de l'exécution réelle", ""]
    for s in scenarios or []:
        etat = "✔ passé" if s.status == "passed" else f"✘ {s.status}"
        lignes.append(f"- {etat} — {s.name}")
    lignes.append("")
    for f in failures or []:
        lignes.append(f"## Scénario en échec : {f.scenario_name}")
        lignes.append(f"Step : {f.step_text}")
        lignes.append("Erreur :")
        lignes.append("```")
        lignes.append((f.raw or f.traceback_summary or "(aucun détail)")[:1500])
        lignes.append("```")
        lignes.append("")
    if steps_content:
        # ⚠️ Sans le contenu ACTUEL, l'agent réécrit de mémoire — et rend un EXTRAIT. Mesuré en
        # run réel (0014 étape 6) : il n'a renvoyé que le step corrigé, les 3 autres ont disparu,
        # le dry-run a échoué, le test ne tournait plus.
        lignes.append("## Contenu ACTUEL de `_steps.py` — pars de lui, renvoie-le ENTIER")
        lignes.append("```python")
        lignes.append(steps_content)
        lignes.append("```")
        lignes.append("")
    lignes.append(
        "Corrige la CAUSE en réécrivant `_steps.py` **EN ENTIER** (le `.feature` est gelé, sauf "
        "les deux exceptions de tes consignes) : `write_steps_file` REMPLACE le fichier — tout "
        "step que tu n'écris pas est PERDU et deviendra `undefined`. Si tu conclus que "
        "l'application se comporte mal, ne maquille rien : dis-le et ne réécris pas.")
    return "\n".join(lignes)


def _last_assistant_text(state: AgentState) -> str:
    """Dernier texte libre de l'agent — ce qu'il dit avoir fait."""
    for message in reversed(state.messages):
        if message.get("role") != "assistant":
            continue
        contenu = message.get("content")
        if isinstance(contenu, str):
            return contenu.strip()
        for bloc in reversed(contenu or []):
            texte = bloc.get("text") if isinstance(bloc, dict) else getattr(bloc, "text", None)
            if texte and texte.strip():
                return texte.strip()
    return ""


def propose_fix(*, module_name: str, scenarios, failures, steps_content: str = "",
                llm: LLMAdapter | None = None, connector: Connector | None = None,
                dry_runner: DryRunner | None = None,
                cost_tracker: CostTracker | None = None,
                max_iterations: int | None = None) -> RepairProposal:
    """Une tentative de correction. Ne lance JAMAIS le test réel (design (b)).

    ⚠️ **`cost_tracker` doit être PARTAGÉ entre les tentatives d'un même cas.** Sans lui, on en
    crée un neuf — donc au plafond entier (`COST_LIMIT_PER_RUN_USD`), donc **remis à zéro à chaque
    tentative** : le plafond bornait un APPEL, jamais le cas, et un cas pouvait dépenser
    `budget × plafond` sans qu'aucun garde-fou ne bronche. `repair_service` en construit un seul
    pour toute la boucle (`REPAIR_COST_LIMIT_PER_CASE_USD`) et le passe à chaque tentative.
    Le défaut ci-dessous ne sert qu'aux appels isolés (tests).
    """
    llm = llm or LLMAdapter()
    cost_tracker = cost_tracker or CostTracker()
    # Le tracker étant partagé, son total contient déjà les tentatives précédentes : on ne rend
    # que le DELTA, sinon `session.cost_usd` et le ledger double-compteraient.
    cout_avant = cost_tracker.total_cost

    # ⚠️ `feature_written`/`steps_written` à True et `dry_run_passed` à True : les fichiers
    # EXISTENT déjà sur disque et parsent (ils ont été validés à la génération). Sans ça, la
    # boucle lancerait un dry-run avant que l'agent n'ait rien écrit — il passerait, et elle
    # conclurait « done » sans la moindre réparation.
    # `feature_content`/`steps_content` restent VIDES : c'est à ça qu'on saura ce que l'agent a
    # réellement réécrit (le tool `_apply_effect` les remplit).
    state = AgentState(module_name=module_name, feature_written=True, steps_written=True,
                       dry_run_passed=True)
    state.messages.append({"role": "user",
                           "content": _failure_report(scenarios, failures, steps_content)})

    shared_steps = steps_library.catalogue()
    ctx = ToolContext(
        module_name=module_name,
        generated_dir=config.GENERATED_DIR,
        connector=connector,
        reserved_steps=frozenset(s.label for s in shared_steps),
    )
    run_loop(
        llm=llm,
        system_prompt=build_repair_prompt(connector),
        state=state,
        ctx=ctx,
        dry_runner=dry_runner,
        cost_tracker=cost_tracker,
        max_iterations=max_iterations if max_iterations is not None else config.MAX_ITERATIONS,
        stall_limit=config.REPAIR_STALL_LIMIT,
    )

    changed = bool(state.steps_content or state.feature_content)
    if not changed:
        logger.info("[repair] l'agent n'a rien réécrit (%s)", state.stopped_reason)
    return RepairProposal(
        changed=changed,
        feature_content=state.feature_content,
        steps_content=state.steps_content,
        summary=_last_assistant_text(state),
        cost_usd=round(cost_tracker.total_cost - cout_avant, 6),
        stopped_reason=state.stopped_reason or "incomplete",
    )
