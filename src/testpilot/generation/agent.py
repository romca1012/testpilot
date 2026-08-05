"""Orchestrateur mince du pilier generation.

``generate(plan)`` : assemble prompt + contexte, lance la boucle ReAct, construit le
GenerationResult, et (si des repos sont fournis) persiste la version + pose le statut de
validation « en attente de relecture ». N'exécute jamais le test et n'appelle jamais le
gate de relecture — il ne fait qu'exposer l'information pour que ``verdict`` s'y branche.
"""

from __future__ import annotations

import logging

from testpilot import config
from testpilot.analysis.plan import TestPlan
from testpilot.analysis.spec_analyzer import spec_hash
from testpilot.generation import domain_model
from testpilot.generation import prompt as prompt_mod
from testpilot.generation import steps_library
from testpilot.generation.interfaces import Connector, DryRunner
from testpilot.generation.react_loop import run_loop
from testpilot.generation.state import AgentState, GenerationResult
from testpilot.store.repositories import ensure_default_module
from testpilot.generation.tools import ToolContext
from testpilot.guardrails.cost_tracker import CostTracker
from testpilot.llm.adapter import LLMAdapter

logger = logging.getLogger(__name__)



class GenerationAgent:
    def __init__(self, *, llm: LLMAdapter | None = None, connector: Connector | None = None,
                 dry_runner: DryRunner | None = None, cost_tracker: CostTracker | None = None,
                 case_repo=None, version_repo=None, max_iterations: int | None = None,
                 stall_limit: int | None = None):
        self.llm = llm or LLMAdapter()
        self.connector = connector
        self.dry_runner = dry_runner
        self.cost_tracker = cost_tracker or CostTracker()
        self.case_repo = case_repo
        self.version_repo = version_repo
        self.max_iterations = max_iterations if max_iterations is not None else config.MAX_ITERATIONS
        self.stall_limit = stall_limit if stall_limit is not None else config.REPAIR_STALL_LIMIT

    def generate(self, plan: TestPlan, *, case_id: int | None = None,
                 title: str = "", author: str = "", module_id: int | None = None,
                 metier: dict | None = None, group_id: int | None = None,
                 projet: dict | None = None, refs: str = "") -> GenerationResult:
        """`metier` — le document métier VALIDÉ (passe 4b de `0022`). Présent, il fixe le périmètre
        du Gherkin et se fige DANS la version, avec lui (décision n°10 : une version = le cas
        entier). Absent, le comportement est celui d'avant (chemin CLI et cas legacy).

        `projet` — le projet testé, qui porte SA cartographie du domaine. Sans lui, aucun annuaire
        n'est chargé : l'agent explore comme avant, sans contrainte inventée.

        `refs` — nom de la user story dont ce cas est issu (§9, génération multi-cas). Écrit tel
        quel sur le CAS (champ `refs`, texte libre comme TestRail), jamais versionné."""
        state = AgentState(module_name=plan.module_name)
        # L'annuaire du domaine alimente la CONTRAINTE de complétude (champs requis + obligation
        # de soumettre). Jusqu'ici seul le GATE le lisait : la génération devait deviner les
        # champs requis « par observation », d'où sa variabilité (2 champs sur 8 au tirage du
        # 2026-07-19). Best-effort : absent ⇒ message d'avant, aucune contrainte inventée.
        # ⚠️ Il est propre au PROJET (son instance), plus au type de connecteur : deux projets
        # Odoo distincts n'ont ni les mêmes routes ni les mêmes champs.
        modele = domain_model.charger_modele(projet)
        state.messages.append({"role": "user",
                               "content": prompt_mod.build_initial_message(plan, modele, metier)})
        # Un seul catalogue pour les deux usages : ce qu'on MONTRE à l'agent (prompt) et ce
        # qu'on lui REFUSE à l'écriture (redéfinition). Cf. décision 0003.
        shared_steps = steps_library.catalogue()
        ctx = ToolContext(
            module_name=plan.module_name,
            generated_dir=config.GENERATED_DIR,
            connector=self.connector,
            reserved_steps=frozenset(s.label for s in shared_steps),
        )
        run_loop(
            llm=self.llm,
            system_prompt=prompt_mod.build_system_prompt(self.connector, shared_steps),
            state=state,
            ctx=ctx,
            dry_runner=self.dry_runner,
            cost_tracker=self.cost_tracker,
            max_iterations=self.max_iterations,
            stall_limit=self.stall_limit,
        )
        result = self._build_result(plan, state)
        if result.success and self.case_repo is not None and self.version_repo is not None:
            self._persist(plan, result, case_id=case_id, title=title, author=author,
                          module_id=module_id, metier=metier, group_id=group_id, refs=refs)
        return result

    def _build_result(self, plan: TestPlan, state: AgentState) -> GenerationResult:
        success = state.dry_run_passed and state.stopped_reason == "done"
        return GenerationResult(
            success=success,
            module_name=plan.module_name,
            stopped_reason=state.stopped_reason or "incomplete",
            dry_run_passed=state.dry_run_passed,
            iterations=state.iterations,
            cost_usd=round(self.cost_tracker.total_cost, 6),
            feature_path=(config.GENERATED_DIR / f"{plan.module_name}.feature") if state.feature_written else None,
            steps_path=(config.GENERATED_DIR / f"{plan.module_name}_steps.py") if state.steps_written else None,
            feature_content=state.feature_content,
            steps_content=state.steps_content,
            spec_hash=spec_hash(plan.raw_spec),
            awaiting_review=success,
        )

    def _persist(self, plan: TestPlan, result: GenerationResult, *,
                 case_id: int | None, title: str, author: str,
                 module_id: int | None = None, metier: dict | None = None,
                 group_id: int | None = None, refs: str = "") -> None:
        """Crée/repère le cas, écrit la nouvelle version, pose le statut « à relire »."""
        import json as _json

        metier = metier or {}
        # Le titre du CAS vient du document métier quand il existe : c'est lui que l'humain a
        # validé. L'argument `title` reste le repli (chemin CLI, cas sans passe métier).
        libelle = (metier.get("title") or "").strip() or title or plan.module_name

        if case_id is None:
            # Rattachement métier (§7) : module imposé par l'appelant (ajout depuis un module),
            # sinon projet/module par défaut déduit du slug technique (CLI).
            if module_id is None:
                module_id = ensure_default_module(self.case_repo.conn, plan.module_name)
            case_id = self.case_repo.create(
                title=libelle, module_id=module_id, group_id=group_id,
                feature_slug=plan.module_name,
                author=author, description=plan.raw_spec[:500], refs=refs,
            )
        # ⚠️ Générer une nouvelle version ne touche PLUS à l'état du cas (migration 25). Ce qui
        # rouvre la relecture, c'est la version elle-même : le gate porte sur la VERSION, et une
        # version neuve n'est pas approuvée. Le statut recopié sur le cas ne faisait que redire
        # ça, moins fidèlement — et il empêchait l'État d'être ce qu'il doit être : un champ que
        # l'humain pose, et que la machine ne lui reprend pas (arbitré le 2026-08-04).

        # ⚠️ Le texte de la spec change de propriétaire (§9c, 2026-08-05) : avec une Section
        # explicite (`group_id`), c'est ELLE qui le porte (`case_group.spec_content`, écrit à sa
        # création par `generation_service`) — pas la version. Sans Section (chemin CLI, ou
        # automatisation d'un cas manuel qui n'a ni `group_id` ni Section), rien d'autre ne le
        # porte : on garde le comportement d'avant pour ne rien perdre sur ces chemins-là.
        version_spec_content = plan.raw_spec if group_id is None else ""

        version_id = self.version_repo.create(
            test_case_id=case_id,
            spec_content=version_spec_content,
            spec_hash=result.spec_hash,
            feature_content=result.feature_content,
            steps_content=result.steps_content,
            feature_path=str(result.feature_path or ""),
            steps_path=str(result.steps_path or ""),
            change_summary="Génération IA",
            created_by=author,
            # ── Le MÉTIER se fige DANS la version, avec le technique (décision `0022` n°10) ──
            # Sans ça, les champs de la migration 14 restaient vides sur tout cas généré et
            # l'écran en dérivait un aperçu depuis le Gherkin : un texte qui avait l'air rédigé
            # sans l'être. C'est ce couple figé ensemble qui rend l'historique diffable et permet
            # au gate d'approuver « le cas entier » d'un seul geste.
            title=libelle,
            preconditions=metier.get("preconditions", ""),
            # `""` et non `"[]"` quand il n'y a pas de métier : « jamais rédigé » et « rédigé
            # vide » ne sont pas le même fait, et c'est ce champ qui décide si l'écran affiche le
            # document ou son repli dérivé.
            test_steps=(_json.dumps(metier["steps"], ensure_ascii=False)
                        if metier.get("steps") else ""),
            expected_result=metier.get("expected_result", ""),
        )
        self.case_repo.set_current_version(case_id, version_id)
        result.case_id = case_id
        result.version_id = version_id
        result.awaiting_review = True

    @staticmethod
    def _reserved_steps() -> frozenset[str]:
        """Libellés de steps de la bibliothèque partagée (best-effort ; vide si absente)."""
        return steps_library.reserved_labels()
