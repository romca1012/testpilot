"""Ajout d'un cas à un module : spec → analyse → génération → gate (décision 0006).

« Ajouter un cas » NE crée PAS une coquille vide. Le parcours cible du brief part toujours
d'une **spécification** : on enchaîne donc le flux existant (analyse → génération → relecture),
en imposant simplement le module d'accueil. Un cas sans version ni Gherkin ne doit jamais
exister dans le référentiel — il afficherait un cas qui ne teste rien (§3).

La génération est longue et coûteuse (LLM) : elle tourne en tâche de fond, avec un job suivi
en mémoire — même schéma que les exécutions (202 + polling).
"""

from __future__ import annotations

import logging
import re
import uuid

from testpilot import config
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, DuplicateName, ModuleRepo

logger = logging.getLogger(__name__)

# job_id → {status: running|done|failed, case_id, error}
_JOBS: dict[str, dict] = {}


class GenerationError(Exception):
    """Erreur métier de déclenchement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code  # not_found | invalid_spec
        self.detail = detail


def get_job(job_id: str) -> dict | None:
    return _JOBS.get(job_id)


def slugify(text: str) -> str:
    """Titre → slug de fichier .feature (ascii, minuscules, underscores)."""
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "cas"


def unique_feature_slug(conn, base: str) -> str:
    """Slug libre : un slug = un fichier ``.feature`` sur disque, donc unique GLOBALEMENT.

    Deux cas d'un même module ne peuvent pas partager de slug, sinon leurs .feature
    s'écraseraient l'un l'autre.
    """
    cases = CaseRepo(conn)
    slug = base
    suffix = 2
    while cases.feature_slug_taken(slug):
        slug = f"{base}_{suffix}"
        suffix += 1
    return slug


def start_generation(conn, module_id: int, *, spec_content: str, title: str = "",
                     author: str = "") -> tuple[str, dict]:
    """Valide la demande et prépare le job. Renvoie (job_id, paramètres de la tâche de fond)."""
    module = ModuleRepo(conn).get(module_id)
    if module is None:
        raise GenerationError("not_found", f"module {module_id} introuvable")
    if not (spec_content or "").strip():
        raise GenerationError("invalid_spec", "la spécification est vide")

    label = (title or "").strip() or f"Cas {module['name']}"
    # Titre unique DANS le module, vérifié AVANT de lancer la tâche de fond : sinon la
    # génération partirait (appel LLM payant, plusieurs minutes) pour finir en job « failed »
    # au moment de l'insertion. Mieux vaut un 409 immédiat et actionnable.
    try:
        CaseRepo(conn).ensure_title_free(module_id, label)
    except DuplicateName as exc:
        raise GenerationError("duplicate", str(exc)) from exc
    slug = unique_feature_slug(conn, slugify(label))

    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "running", "case_id": None, "error": "", "module_id": module_id}
    return job_id, {"module_id": module_id, "slug": slug, "title": label,
                    "spec_content": spec_content, "author": author}


def _record_generation_cost(conn, *, case_id: int | None, analysis_usd: float,
                            generation_usd: float) -> None:
    """Écrit au ledger ce que la création d'un cas a coûté — analyse ET génération.

    ⚠️ **Sans ça, le §9 était inmesurable sur le chemin que les utilisateurs empruntent.**
    `CostRepo.add_entry` n'était appelé que par `cli.py` et `repair_service` : un cas créé par
    l'écran ne laissait **aucune trace** de son coût de génération — 42 % du budget cible sur le
    cas 1, invisible. La seule ligne `generation` du ledger venait d'un run CLI, et on prétendait
    juger le §9 dessus.

    **Deux lignes, pas une** : le ledger porte la `phase`, donc il doit dire *ce qui* a coûté, pas
    seulement combien (c'est la raison d'être de `breakdown_for_case`). Elles n'ont pas le même
    modèle non plus (`MODEL_FAST` pour l'analyse, `MODEL_GENERATION` pour la génération) : les
    fusionner attribuerait la dépense au mauvais tarif et rendrait le total inexplicable.

    Aucun `execution_id` : **une génération n'a pas d'exécution** — elle la précède, et le cas
    peut n'être jamais exécuté. C'est précisément pourquoi le lien du ledger devait devenir
    `test_case_id` (migration 12).

    Best-effort : une écriture de comptabilité ne fait jamais échouer une génération qui a réussi
    — mais elle ne disparaît pas en silence (§4.6).
    """
    if case_id is None:
        # L'agent n'a pas créé de cas (échec avant persistance) : la dépense est réelle mais n'a
        # aucun cas où s'accrocher. On le DIT plutôt que de l'imputer à un cas au hasard.
        if analysis_usd or generation_usd:
            logger.warning("[generation] $%.4f dépensés sans cas créé — hors ledger (aucun "
                           "test_case_id où rattacher). Le budget §9 ignore cette dépense.",
                           analysis_usd + generation_usd)
        return
    from testpilot.store.repositories import CostRepo
    for phase, model, cost in (("analysis", config.MODEL_FAST, analysis_usd),
                               ("generation", config.MODEL_GENERATION, generation_usd)):
        if not cost:
            continue
        try:
            CostRepo(conn).add_entry(phase=phase, model=model, cost_usd=cost,
                                     source=config.COST_SOURCE, test_case_id=case_id)
        except Exception:
            logger.exception("[generation] coût %s de %s USD NON enregistré (cas %s) — le budget "
                             "§9 sera sous-évalué d'autant", phase, cost, case_id)


def run_generation(job_id: str, *, module_id: int, slug: str, title: str,
                   spec_content: str, author: str, angle: str = "nominal") -> None:
    """PASSE 4a — analyse la spec, rédige le DOCUMENT MÉTIER, puis **s'arrête**.

    ⚠️ Ce job ne va PAS jusqu'au bout : il se met en `awaiting_metier` et attend qu'un humain
    valide (ou corrige) le document. `resume_generation` écrit ensuite le Gherkin **depuis ce
    document validé**. C'est la décision `0022` n°5, et son intérêt est chiffré : on ne paie plus
    la passe technique (la plus chère) pour une intention fausse.

    Rien n'est persisté à ce stade — aucun cas n'existe encore. Un cas qui n'aurait que son
    métier serait une coquille sans Gherkin, précisément ce que `0006` refuse. Le brouillon vit
    donc dans le job, en mémoire : si le serveur redémarre avant validation, la passe métier est
    à refaire (~$0,02), et c'est le prix assumé pour ne jamais salir le référentiel.
    """
    from testpilot.analysis.spec_analyzer import SpecAnalyzer
    from testpilot.generation.metier_writer import propose_metier
    from testpilot.guardrails.cost_tracker import CostTracker

    conn = get_initialized_db(config.DB_PATH)
    try:
        # ⚠️ L'ANALYSE COÛTE, et son coût n'était compté NULLE PART — ni ici, ni en CLI.
        # `SpecAnalyzer()` sans `cost_tracker` laisse `plan.cost_usd` à 0.0 : un appel LLM
        # (MODEL_FAST) invisible sur les deux chemins. Le schéma prévoyait pourtant la phase
        # `analysis` depuis le début. On lui donne donc un tracker, et on écrit ce qu'il mesure.
        analysis_tracker = CostTracker()
        plan = SpecAnalyzer(cost_tracker=analysis_tracker).analyze_spec_content(slug, spec_content)

        metier_tracker = CostTracker()
        draft = propose_metier(plan, angle=angle, cost_tracker=metier_tracker)

        if not draft.complete:
            # Titre + étapes + résultat attendu sont obligatoires (`0022` n°3.c). On ÉCHOUE plutôt
            # que de proposer un document à trous : l'humain corrigerait une base fabriquée sans
            # savoir ce qui vient du modèle et ce qui vient de nous.
            _JOBS[job_id].update(
                status="failed",
                error="le document métier rendu est incomplet (titre, étapes et résultat attendu "
                      "sont obligatoires) — relancez la génération",
                cost_usd=analysis_tracker.total_cost + metier_tracker.total_cost)
            return

        _JOBS[job_id].update(
            status="awaiting_metier",
            metier=draft.as_dict(),
            # Contexte de reprise : `resume_generation` ne refait ni l'analyse ni la passe métier.
            _resume={"module_id": module_id, "slug": slug, "title": title, "author": author,
                     "spec_content": spec_content},
            cost_usd=analysis_tracker.total_cost + metier_tracker.total_cost)
    except Exception as exc:  # jamais laisser un job « en cours » sur un plantage
        logger.exception("[generation] job %s (passe métier) en échec : %s", job_id, exc)
        _JOBS[job_id].update(status="failed", error=str(exc)[:300])
    finally:
        conn.close()


def validate_metier(job_id: str, metier: dict) -> dict:
    """Enregistre le document métier VALIDÉ (éventuellement corrigé) et prépare la reprise."""
    job = _JOBS.get(job_id)
    if job is None:
        raise GenerationError("not_found", "job introuvable")
    if job.get("status") != "awaiting_metier":
        raise GenerationError("invalid_state",
                              f"ce job n'attend pas de validation métier (état : {job['status']})")
    steps = [str(s).strip() for s in (metier.get("steps") or []) if str(s or "").strip()]
    if not (str(metier.get("title", "")).strip() and steps
            and str(metier.get("expected_result", "")).strip()):
        raise GenerationError("invalid_metier",
                              "titre, étapes et résultat attendu sont obligatoires")
    validated = {
        "title": str(metier["title"]).strip(),
        "preconditions": str(metier.get("preconditions", "") or "").strip(),
        "steps": steps,
        "expected_result": str(metier["expected_result"]).strip(),
        "angle": str(metier.get("angle", "") or job.get("metier", {}).get("angle", "")).strip(),
    }
    job.update(status="running", metier=validated)
    return {**job["_resume"], "metier": validated}


def resume_generation(job_id: str, *, module_id: int, slug: str, title: str,
                      spec_content: str, author: str, metier: dict) -> None:
    """PASSE 4b — écrit le Gherkin DEPUIS le métier validé, puis persiste le cas ENTIER."""
    from testpilot.analysis.spec_analyzer import SpecAnalyzer
    from testpilot.connectors.odoo import OdooConnector
    from testpilot.connectors.runtime_env import project_env
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.generation.agent import GenerationAgent
    from testpilot.guardrails.cost_tracker import CostTracker
    from testpilot.store.repositories import ProjectRepo, VersionRepo

    conn = get_initialized_db(config.DB_PATH)
    connector = None
    try:
        module = ModuleRepo(conn).get(module_id)
        project = ProjectRepo(conn).get(module["project_id"]) if module else None

        # Génération ET dry-run tapent l'application DU PROJET du module (décision 0005).
        connector = OdooConnector.from_project(project)
        connector.connect()
        runner = BehaveRunner(connection=project_env(project))

        # L'analyse est refaite ici : elle alimente l'agent en matière technique (modèles, routes,
        # champs requis) que le document métier ne porte pas — et un `TestPlan` n'est pas
        # sérialisable dans le job. Son coût est réel, il est compté avec le reste.
        analysis_tracker = CostTracker()
        plan = SpecAnalyzer(cost_tracker=analysis_tracker).analyze_spec_content(slug, spec_content)

        agent = GenerationAgent(dry_runner=runner, connector=connector,
                                case_repo=CaseRepo(conn), version_repo=VersionRepo(conn))
        result = agent.generate(plan, title=title, author=author, module_id=module_id,
                                metier=metier, projet=project)

        # Le coût est écrit AVANT tout aiguillage succès/échec : une génération qui échoue a
        # coûté quand même. Ne compter que les réussites donnerait un budget flatteur — « affiché
        # ≠ réel » (§4.6) appliqué à l'argent, exactement ce que la boucle de réparation évite.
        # Le coût de la passe MÉTIER (payé avant la pause) est ajouté ici : c'est le seul moment
        # où un `test_case_id` existe pour le porter.
        _record_generation_cost(conn, case_id=result.case_id,
                                analysis_usd=analysis_tracker.total_cost
                                + float(_JOBS.get(job_id, {}).get("cost_usd", 0.0)),
                                generation_usd=result.cost_usd)

        if result.success and result.case_id:
            _JOBS[job_id].update(status="done", case_id=result.case_id)
        else:
            _JOBS[job_id].update(status="failed",
                                 error=result.error or result.stopped_reason or "génération échouée")
    except Exception as exc:  # jamais laisser un job « en cours » sur un plantage
        logger.exception("[generation] job %s (passe Gherkin) en échec : %s", job_id, exc)
        _JOBS[job_id].update(status="failed", error=str(exc)[:300])
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                pass
        conn.close()
