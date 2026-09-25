"""Déclenchement et exécution d'un cas depuis l'API (tâche de fond).

Un run UI ré-exécute la version courante APPROUVÉE d'un cas via le vrai runner Behave, puis
calcule le verdict à deux axes et le persiste — même logique que le CLI (§5), sans étape de
génération ni coût LLM. L'état « en cours » est suivi en mémoire (serveur mono-processus).
"""

from __future__ import annotations

import json
import logging
import shutil
import time
import uuid
from pathlib import Path

from testpilot import config
from testpilot.api.services import attachment_service, repair_service
from testpilot.connectors.runtime_env import ConnexionIncomplete, cible_de, verifier_connexion
from testpilot.execution.behave_result import MODE_STRICT_ENV
from testpilot.execution.behave_runner import BehaveRunner
from testpilot.execution.executor import Executor
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import (
    CaseRepo,
    CostRepo,
    ExecutionRepo,
    ProjectRepo,
    RepairRepo,
    ResultRepo,
    ReviewRepo,
    VersionRepo,
    now_iso,
)
from testpilot.verdict import defect_origin as do
from testpilot.verdict import explication, review_gate
from testpilot.verdict.status import (
    CaseVerdict,
    EXEC_TECHNICAL_ERROR,
    FUNC_INDETERMINE,
    derive_verdict,
)

logger = logging.getLogger(__name__)

# Exécutions en cours (id) — suivi mémoire, suffisant pour le serveur de dev mono-processus.
_RUNNING: set[int] = set()


def is_running(execution_id: int) -> bool:
    return execution_id in _RUNNING


class RunError(Exception):
    """Erreur métier de déclenchement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code       # not_found | no_version | needs_review | no_connection
        self.detail = detail


def project_du_cas(conn, case_id: int) -> dict | None:
    """Le PROJET auquel appartient le cas — porteur de la connexion (décision 0005)."""
    case = CaseRepo(conn).get(case_id)
    project_id = (case or {}).get("project_id")
    return ProjectRepo(conn).get(project_id) if project_id else None


def trigger_run(conn, case_id: int, *, triggered_by: str = "") -> tuple[int, str, int, int]:
    """Valide le gate et crée la ligne d'exécution. Renvoie (execution_id, feature_slug, case_id, version_id).

    `triggered_by` (migration 32) : le compte qui a demandé ce run — résolu par l'APPELANT,
    SYNCHRONE, avant toute mise en tâche de fond (même patron que `author` dans `add_case`).
    """
    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise RunError("not_found", f"cas {case_id} introuvable")
    version_id = case.get("current_version_id")
    if not version_id:
        raise RunError("no_version", "aucune version générée pour ce cas")

    gate = review_gate.evaluate_gate(ReviewRepo(conn), version_id)
    if not gate.allowed:
        raise RunError("needs_review", gate.reason)

    # ⚠️ **Savoir contre quoi on teste, AVANT de tester** (2026-07-24). Sans connexion complète, le
    # runtime retombait sur la configuration globale de la machine : l'écran montrait un projet, le
    # navigateur en testait un autre, et le résultat était faux **sans laisser de trace**. On
    # refuse, et on dit quoi corriger.
    project = project_du_cas(conn, case_id)
    try:
        verifier_connexion(project)
    except ConnexionIncomplete as err:
        raise RunError("no_connection", err.message()) from err

    execs = ExecutionRepo(conn)
    # Le premier jet appartient à chaque VERSION générée. Après une régénération, la première
    # exécution de la nouvelle version doit alimenter à nouveau l'onglet Qualité.
    trigger = "rerun" if execs.has_for_version(version_id) else "first_run"
    eid = execs.create(test_case_id=case_id, version_id=version_id, trigger=trigger,
                       cible=cible_de(project), triggered_by=triggered_by)
    _RUNNING.add(eid)
    # feature_slug = nom du .feature (technique), distinct du module métier (§7 / décision 0004).
    return eid, case["feature_slug"], case_id, version_id


def enregistrer_lancement_bloque(conn, *, case_id: int, code: str, message: str,
                                  run_id: int | None = None,
                                  triggered_by: str = "") -> int | None:
    """Rend visible, dans l'historique du cas, un lancement bloqué AVANT `trigger_run` — au lieu
    de ne laisser trace que dans le journal serveur (bug réel, 2026-09-15) : une campagne qui
    butait sur `needs_review`/`no_connection` journalisait `RunError` puis passait au cas suivant,
    qui restait « Untested » sans rien à l'écran pour dire pourquoi — le run, lui, se terminait
    « Terminé » comme si tout avait joué. Réutilise `_ecrire_erreur`, le même mécanisme
    d'affichage qu'un plantage technique en cours de run : aucun nouveau composant d'écran.

    Seuls `needs_review` et `no_connection` ont une VERSION réelle à rattacher — le gate n'est
    évalué qu'après lecture de `current_version_id` (cf. `trigger_run`). Pour `not_found` et
    `no_version`, il n'existe ni cas ni version valides à référencer (clé étrangère NOT NULL sur
    `execution.version_id`) ; rend `None` sans rien créer — un cas jamais généré reste
    honnêtement « Untested », l'appelant continue de se contenter du journal serveur.

    `run_id`, quand fourni (campagne), est rattaché **avant** la clôture — même ordre que le
    chemin normal (`campaign_service.run_campaign`) : `ResultRepo.enregistrer_execution` ignore
    toute exécution SANS `run_id` au moment où `finalize` s'exécute (« hors campagne »), donc un
    rattachement fait après coup laisserait le cas retomber dans le même silence qu'on corrige ici.
    """
    if code not in ("needs_review", "no_connection"):
        return None
    case = CaseRepo(conn).get(case_id)
    version_id = (case or {}).get("current_version_id")
    if not version_id:
        return None
    project = project_du_cas(conn, case_id)
    execs = ExecutionRepo(conn)
    trigger = "rerun" if execs.has_for_version(version_id) else "first_run"
    eid = execs.create(test_case_id=case_id, version_id=version_id, trigger=trigger,
                       cible=cible_de(project), triggered_by=triggered_by)
    if run_id is not None:
        conn.execute("UPDATE execution SET run_id=? WHERE id=?", (run_id, eid))
        conn.commit()
    _ecrire_erreur(conn, eid, case_id, message)
    return eid


def resolve_connection(conn, case_id: int) -> dict[str, str]:
    """Connexion (variables d'env) du PROJET auquel appartient le cas.

    Le run doit taper l'application du projet affiché, pas la config globale — sinon
    l'interface promettrait un multi-projet que le runtime ne tiendrait pas.

    ⚠️ **Lève si la connexion est incomplète** (2026-07-24), au lieu de rendre un dictionnaire vide
    qui laissait la configuration globale s'appliquer en silence. Le garde est déjà passé au
    déclenchement ; celui-ci est le second verrou, sur le chemin de fond — mieux vaut une erreur
    technique explicite qu'un verdict obtenu contre la mauvaise application.
    """
    return verifier_connexion(project_du_cas(conn, case_id))


def resolve_project_id(conn, case_id: int) -> int | None:
    """L'id du PROJET du cas — que le runner passe au résolveur déterministe (§2bis) pour
    charger le bon annuaire. Séparé de `resolve_connection` : le projet peut n'avoir aucune
    connexion saisie (→ config globale) tout en ayant un annuaire mesuré."""
    case = CaseRepo(conn).get(case_id)
    return (case or {}).get("project_id")


def resolve_connector_type(conn, case_id: int) -> str | None:
    """Le `connector_type` du PROJET du cas — que le runner passe pour scoper la bibliothèque
    de steps (Phase 1b). `None` si le projet n'en porte pas encore (repli : bibliothèque
    complète, comportement identique à avant cette phase)."""
    return (project_du_cas(conn, case_id) or {}).get("connector_type")


def _assurer_script_sur_disque(conn, version_id: int, module_name: str) -> None:
    """Réécrit le `.feature`/`_steps.py` de CETTE version sur disque avant de l'exécuter.

    ⚠️ **Bug réel constaté le 2026-09-14** : 15/15 cas SauceDemo revenus « difficulté technique —
    le test n'a pas pu démarrer » sur /dev, alors que leur Gherkin/steps restait intact EN BASE.
    Cause : `BehaveRunner` lit le script SUR DISQUE, jamais depuis la base (`GENERATED_DIR`,
    cf. son propre commentaire) — ce que `CaseRepo.copier`/`update_version` (`repositories.py`)
    savent déjà et compensent en réécrivant le fichier à CHAQUE écriture de version. Mais
    `GENERATED_DIR` (`behave_runtime/generated/`) vit HORS du volume persistant
    (`testpilot-data:/var/lib/testpilot`, `compose.production.yml`) et le Dockerfile le recrée
    VIDE à chaque build — un simple redéploiement (`deploy-dev.yml` tourne après CHAQUE CI verte
    sur master) efface donc silencieusement tous les cas déjà générés, jusqu'à leur prochaine
    régénération ou édition manuelle. La RE-exécution d'un cas déjà généré (run normal, campagne,
    planification) n'avait, elle, aucun filet : on l'ajoute ici, au point d'entrée commun à toutes
    ces voies. Idempotent — sans coût si le fichier existe déjà à l'identique.
    """
    version = VersionRepo(conn).get(version_id)
    feature_content = (version or {}).get("feature_content") or ""
    if not feature_content.strip():
        return  # cas sans Gherkin généré : rien à réécrire, le runner le dira lui-même
    config.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    (config.GENERATED_DIR / f"{module_name}.feature").write_text(feature_content, encoding="utf-8")
    (config.GENERATED_DIR / f"{module_name}_steps.py").write_text(
        version.get("steps_content") or "", encoding="utf-8")


def run_execution(execution_id: int, module_name: str, case_id: int, version_id: int, *,
                  triggered_by: str = "", qualification: bool = False, strict: bool = False) -> None:
    """Tâche de fond : lance Behave réel, calcule + persiste le verdict à deux axes.

    Puis tente une RÉPARATION si le gate l'a autorisée (décision 0014) : la boucle vit dans
    `repair_service`, c'est le circuit qui décide de continuer ou non — jamais l'agent.

    `triggered_by` (migration 32) : transmis à `_maybe_repair` — une tentative de réparation
    n'est pas un nouveau geste humain, elle hérite de l'acteur du run d'origine.
    """
    # ⚠️ L'ouverture est DANS le try : hors de lui, un échec de connexion sautait à la fois le
    # filet (`_finalize_error`) et le `finally` — l'exécution restait « en cours » pour toujours
    # dans `_RUNNING`, et sa ligne `not_executed` sans le moindre message.
    conn = None
    try:
        conn = get_initialized_db()
        _assurer_script_sur_disque(conn, version_id, module_name)
        # Le runtime tape l'application DU PROJET du cas (décision 0005).
        runner = BehaveRunner(connection=resolve_connection(conn, case_id),
                              project_id=resolve_project_id(conn, case_id),
                              connector_type=resolve_connector_type(conn, case_id))
        outcome = _execute_and_persist(conn, execution_id, case_id, module_name, runner,
                                       **({'qualification': True} if qualification else {}),
                                       **({'strict': True} if strict else {}))
        # ⚠️ Isolé du verdict déjà persisté ci-dessus (audit 2026-08-07, défaut bloquant) : un
        # plantage PENDANT la réparation ne doit JAMAIS écraser un verdict RÉEL déjà écrit —
        # `ExecutionRepo.finalize` n'a aucune garde contre un second appel, donc laisser cette
        # exception remonter au `except` du bas appellerait `_finalize_error` sur ce MÊME
        # `execution_id` et remplacerait un verdict fonctionnel (potentiellement un vrai bug
        # détecté) par « erreur technique » — la réparation est un bonus après coup, jamais une
        # condition de validité du verdict original.
        try:
            if not qualification:
                _maybe_repair(conn, case_id=case_id, version_id=version_id, module_name=module_name,
                              outcome=outcome, runner=runner, triggered_by=triggered_by, strict=strict)
        except Exception:
            logger.exception("[run] réparation de l'exécution %s en échec — le verdict "
                             "d'origine reste acquis, non touché", execution_id)
    except Exception as exc:  # jamais laisser l'exécution « en cours » sur un plantage
        logger.exception("[run] exécution %s en échec : %s", execution_id, exc)
        _finalize_error(conn, execution_id, case_id, str(exc))
    finally:
        _RUNNING.discard(execution_id)
        if conn is not None:
            conn.close()


def dossier_artefacts(execution_id: int) -> Path:
    """Où archiver la trace brute d'une exécution : `data/executions/<id>/`."""
    return Path(config.DATA_DIR) / "executions" / str(execution_id)


def _execute_and_persist(conn, execution_id: int, case_id: int, module_name: str, runner,
                         *, qualification: bool = False, strict: bool = False):
    """Un run réel + son verdict persisté. `outcome.execution_id` porte la ligne concernée."""
    started = time.perf_counter()
    # ⚠️ Redésigné AVANT chaque run, pas une fois à la construction : le même runner sert les
    # tentatives de réparation, qui ont chacune leur propre ligne d'exécution. Une cible figée
    # ferait écrire toutes les tentatives dans le dossier de la première.
    chemin = dossier_artefacts(execution_id)
    if hasattr(runner, "cibler_artefacts"):   # les runners de test n'archivent pas
        runner.cibler_artefacts(chemin)
        ExecutionRepo(conn).set_artifacts_path(execution_id, str(chemin))
    # Même motif : une règle apprise pendant CE run doit porter SA ligne d'exécution (0023),
    # pas celle d'une tentative précédente réutilisant le même runner.
    if hasattr(runner, "cibler_execution"):
        runner.cibler_execution(execution_id)
    from testpilot.store.execution_attempts import ExecutionAttemptRepo
    from testpilot.generation.provenance import execution_provenance

    attempts = ExecutionAttemptRepo(conn)
    attempt_ids = {}
    provenance = execution_provenance(conn, execution_id)
    provenance['qualification'] = qualification

    def start_attempt(number, reason):
        path = chemin / f"attempt-{number}"
        attempt_ids[number] = attempts.start(
            execution_id, number, reason=reason, artifacts_path=str(path), provenance=provenance)
        if hasattr(runner, 'cibler_artefacts'):
            runner.cibler_artefacts(path)

    def finish_attempt(number, result, duration):
        attempts.finish(attempt_ids[number], result, duration,
                        connector_type=resolve_connector_type(conn, case_id))
        # Vue de compatibilité du dernier résultat ; les dossiers attempt-N restent intacts.
        path = chemin / f"attempt-{number}"
        if path.is_dir():
            shutil.copytree(path, chemin, dirs_exist_ok=True)

    executor = Executor(runner)
    executor.on_attempt_start = start_attempt
    executor.on_attempt_finish = finish_attempt
    if qualification:
        executor.max_retries = 0
        if hasattr(runner, 'connection'):
            runner.connection = {**runner.connection, 'TESTPILOT_QUALIFICATION': '1'}
    if strict:
        # Lot 05 (D5) : campagne STRICTE — ni retry ni résolution adaptative (le sous-processus lit `TP_MODE_STRICT`).
        # Ce que la campagne mesure alors est la cascade déterministe seule : un champ renommé donne un `retest`.
        executor.max_retries = 0
        if hasattr(runner, 'connection'):
            runner.connection = {**runner.connection, MODE_STRICT_ENV: '1'}
    outcome = executor.execute(module_name)
    duration = time.perf_counter() - started
    # Confiance du verdict selon le connecteur (étape 2.2) — déjà résolu plus haut pour scoper la
    # bibliothèque de steps du runner ; réutilisé ici plutôt que reproduit.
    verdict = derive_verdict(outcome, connector_type=resolve_connector_type(conn, case_id))
    _persist(conn, execution_id, case_id, verdict, outcome, duration, module_name)
    # Attaché ici plutôt que porté par ExecutionOutcome : le pilier execution ne connaît pas la
    # base, et n'a pas à la connaître.
    outcome.execution_id = execution_id
    return outcome


def _maybe_repair(conn, *, case_id: int, version_id: int, module_name: str, outcome, runner,
                  triggered_by: str = "", strict: bool = False):
    """Répare si le gate l'a autorisé. Chaque tentative rejouée = une nouvelle EXÉCUTION (B).

    `triggered_by` (migration 32) : l'acteur du run d'origine, reporté sur chaque tentative — une
    réparation n'est pas un nouveau geste humain, juste la suite du même run.
    """
    cible = cible_de(project_du_cas(conn, case_id))

    def run_once(new_version_id: int):
        """Rejoue le module après une correction, dans sa PROPRE ligne d'exécution."""
        eid = ExecutionRepo(conn).create(test_case_id=case_id, version_id=new_version_id,
                                         trigger="rerun", cible=cible, triggered_by=triggered_by)
        try:
            # La campagne stricte reste stricte pendant la réparation : ni retry ni repli LLM sur le rejeu.
            return _execute_and_persist(conn, eid, case_id, module_name, runner,
                                        **({'strict': True} if strict else {}))
        except Exception:
            # Cette ligne d'exécution existe déjà en base (créée juste au-dessus) : sans ceci,
            # un plantage avant sa finalisation la laisserait « not_executed » pour toujours — un
            # signal RASSURANT, alors qu'elle a réellement tourné et planté (même piège que
            # `_finalize_error`, §4.6). Propage ensuite : la boucle de réparation doit s'arrêter,
            # pas continuer sur un `outcome` inexistant.
            logger.exception("[run] tentative de réparation (exécution %s) en échec technique", eid)
            _finalize_error(conn, eid, case_id,
                            "réparation : la tentative a planté techniquement")
            raise

    connector = _connector_for(conn, case_id)
    session = repair_service.run_repair_loop(
        conn, case_id=case_id, version_id=version_id, module_name=module_name,
        outcome=outcome, run_once=run_once, connector=connector,
        # Le MÊME runner que le run réel : le dry-run de l'agent doit valider le correctif dans
        # l'environnement qui l'exécutera ensuite. Un second runner divergerait (principe 4).
        dry_runner=runner)
    if session.attempts:
        logger.info("[run] réparation : %s tentative(s) → %s (%s)",
                    session.attempts, session.outcome, session.reason)
    return session


def _connector_for(conn, case_id: int):
    """Connecteur du projet du cas — l'agent de réparation en a besoin pour ses règles.

    Best-effort : sans connecteur, l'agent répare avec les seules règles génériques plutôt que
    de faire échouer la réparation.
    """
    try:
        # ⚠️ `build_connector`, jamais `OdooConnector` en dur (bug SauceDemo, 2026-09-11) : voir
        # `connectors/factory.py`. Ce chemin est best-effort (except large ci-dessous), donc
        # l'ancien bug ne faisait pas ÉCHOUER la réparation — mais lui faisait construire un
        # connecteur du mauvais type pour tout projet non-Odoo, silencieusement.
        from testpilot.connectors.factory import build_connector
        case = CaseRepo(conn).get(case_id)
        project_id = (case or {}).get("project_id")
        project = ProjectRepo(conn).get(project_id) if project_id else None
        return build_connector(project) if project else None
    except Exception:
        logger.warning("[repair] connecteur indisponible — règles génériques seules", exc_info=True)
        return None


def _expliquer(conn, execution_id: int, verdict: CaseVerdict, module_name: str) -> str:
    """Le commentaire IA du verdict (§A du plan « fiabiliser le verdict automatique »,
    2026-08-06) — TOUS statuts, décision explicite du porteur. Best-effort : un souci ici ne doit
    JAMAIS empêcher la clôture de l'exécution, qui doit toujours s'écrire.

    Coût tracé sous sa PROPRE phase (`"explication"`), hors du budget §9 (qui ne mesure que la
    CRÉATION d'un cas, pas ses exécutions répétées) — décision explicite du porteur.
    """
    try:
        texte, cout = explication.propose_explication(verdict, module_name=module_name)
    except Exception:
        logger.warning("[explication] génération impossible pour l'exécution %s", execution_id,
                       exc_info=True)
        return ""
    if cout:
        try:
            CostRepo(conn).add_entry(phase="explication", model=config.MODEL_FAST,
                                     cost_usd=cout, source=config.COST_SOURCE,
                                     execution_id=execution_id)
        except Exception:
            logger.warning("[explication] coût de %s USD NON enregistré (exécution %s)",
                           cout, execution_id, exc_info=True)
    return texte


def _joindre_captures(conn, execution_id: int, result_id: int | None) -> None:
    """Rattache au résultat les captures d'écran archivées pour cette exécution (§A) — même
    dossier/table que les pièces jointes qu'un humain ajoute en saisie manuelle
    (`attachment_service`), pour que l'écran les affiche sans code neuf côté lecture.

    Best-effort ABSOLU : une capture manquante ou non copiable ne doit jamais faire tomber une
    exécution déjà persistée. `result_id` est `None` hors campagne (le registre ne s'applique
    pas) — rien à faire, silencieusement.
    """
    if result_id is None:
        return
    source_dir = dossier_artefacts(execution_id) / "screenshots"
    from testpilot.store.execution_attempts import ExecutionAttemptRepo
    attempts = ExecutionAttemptRepo(conn).list_for_execution(execution_id)
    if attempts:
        source_dir = Path(attempts[-1]['artifacts_path']) / 'screenshots'
    if not source_dir.is_dir():
        return
    try:
        cible_dir = attachment_service.dossier(result_id)
        cible_dir.mkdir(parents=True, exist_ok=True)
        repo = ResultRepo(conn)
        # Même plafond que la saisie manuelle (`attachment_service.enregistrer`) : un cas à
        # beaucoup de scénarios ne doit pas dépasser silencieusement la limite d'un résultat.
        deja = len(repo.pieces_jointes(result_id))
        for fichier in sorted(source_dir.glob("*.png")):
            if deja >= config.ATTACHMENT_MAX_PER_RESULT:
                logger.info("[capture] plafond de %s pièces jointes atteint pour le résultat %s"
                           " — captures restantes non jointes", config.ATTACHMENT_MAX_PER_RESULT,
                           result_id)
                break
            stored_name = f"{uuid.uuid4().hex}.png"
            shutil.copy2(fichier, cible_dir / stored_name)
            repo.ajouter_piece_jointe(
                result_id, filename=fichier.name, stored_name=stored_name,
                dossier=str(cible_dir), content_type="image/png",
                size_bytes=fichier.stat().st_size)
            deja += 1
    except OSError:
        logger.warning("[capture] pièce(s) jointe(s) non rattachée(s) au résultat %s", result_id,
                       exc_info=True)


def _persist(conn, execution_id, case_id, verdict, outcome, duration, module_name: str = "") -> None:
    execs = ExecutionRepo(conn)
    for s in verdict.scenarios:
        execs.add_scenario_result(
            execution_id=execution_id, scenario_name=s.name,
            execution_status=s.execution_status, functional_status=s.functional_status,
            failure_type=s.failure_type, cause_category=s.cause_category,
            error_summary=(s.error or "")[:500], step_text=s.step_text,
        )

    if outcome.real_run is not None and outcome.real_run.failures:
        dv = do.diagnose(outcome.real_run.failures)
        if dv is not None:
            from testpilot.guardrails.repair_circuit import failure_signature
            RepairRepo(conn).create(
                execution_id=execution_id, attempt_number=1,
                failure_signature=failure_signature(outcome.real_run.failures),
                cause_category=dv.cause_category, defect_origin=dv.defect_origin,
                confirmation_status=dv.confirmation_status)

    # Replis « libellé → nom technique » tracés pendant le run (0007 B+). Attachés à l'exécution
    # pour rester lisibles a posteriori, y compris quand le run est VERT — Behave n'affiche pas
    # les logs d'un scénario réussi, et c'est justement le cas où un champ renommé côté
    # application passerait inaperçu (verdict 0007 n°2). Aucun run réel (erreur technique
    # avant l'exécution) → liste vide.
    fallbacks = outcome.real_run.field_fallbacks if outcome.real_run is not None else []

    # ⚠️ Le commentaire (§A) est généré ICI, AVANT `finalize` : le registre écrit ses lignes une
    # fois pour toutes (§7, `ResultRepo`), donc le texte doit être prêt AU MOMENT de l'INSERT — une
    # UPDATE après coup romprait l'invariant « rien n'est jamais modifié ».
    commentaire = _expliquer(conn, execution_id, verdict, module_name)

    result_id = execs.finalize(
        execution_id, execution_status=verdict.execution_status,
        functional_status=verdict.functional_status,
        scenarios_total=len(verdict.scenarios),
        scenarios_passed=verdict.scenarios_passed, scenarios_failed=verdict.scenarios_failed,
        cost_usd=0.0, iterations=0, duration_seconds=duration,
        field_fallbacks=json.dumps(fallbacks, ensure_ascii=False) if fallbacks else "",
        comment=commentaire, confiance=verdict.confiance)
    # Les captures, elles, peuvent s'attacher APRÈS coup sans rompre l'invariant : elles vivent
    # dans `result_attachment`, une table à part (même exception déjà documentée pour
    # `attachments_path`, cf. `ResultRepo.ajouter_piece_jointe`).
    _joindre_captures(conn, execution_id, result_id)

    cases = CaseRepo(conn)
    cases.update_last_outcome(case_id, execution_status=verdict.execution_status,
                              functional_status=verdict.functional_status, executed_at=now_iso())


def _ecrire_erreur(conn, execution_id: int, case_id: int, message: str) -> bool:
    """Écrit le verdict d'échec. Rend False si l'écriture n'a PAS abouti — jamais d'exception.

    ⚠️ Pas d'appel IA ici (contrairement à `_persist`) : un plantage AVANT tout scénario n'a ni
    verdict ni scénario à expliquer, et c'est un chemin rare — un commentaire fixe, honnête, vaut
    mieux qu'un appel IA de plus sur un message d'exception déjà technique par nature.
    """
    try:
        ExecutionRepo(conn).finalize(
            execution_id, execution_status=EXEC_TECHNICAL_ERROR,
            functional_status=FUNC_INDETERMINE, scenarios_total=0, scenarios_passed=0,
            scenarios_failed=0, cost_usd=0.0, iterations=0, duration_seconds=0.0,
            error_message=(message or "")[:1000],
            comment="Le test n'a pas pu s'exécuter techniquement avant même de commencer à "
                    "vérifier l'application — rien n'a donc pu être constaté sur son "
                    "fonctionnement.")
        CaseRepo(conn).update_last_outcome(
            case_id, execution_status=EXEC_TECHNICAL_ERROR,
            functional_status=FUNC_INDETERMINE, executed_at=now_iso())
        return True
    except Exception:
        logger.exception("[run] échec de la clôture d'erreur pour %s", execution_id)
        return False


def _finalize_error(conn, execution_id, case_id, message: str) -> None:
    """Clôt une exécution plantée comme erreur technique (verdict honnête, jamais 'conforme').

    ⚠️ **Le filet ne doit pas tomber avec ce qu'il rattrape.** Ce code écrivait avec la connexion
    du run — celle-là même qui peut être la CAUSE du plantage (base verrouillée, connexion
    fermée, thread). L'échec de l'écriture était alors avalé par un `except` muet, et la ligne
    restait `not_executed` **alors que le test avait tourné** : « affiché ≠ réel » (§4.6), et un
    statut qui n'est pas la conséquence d'une exécution réelle (§4.2).

    C'est encore *« l'absence de signal prise pour un signal positif »* : une ligne restée
    `not_executed` se lit « n'a jamais tourné » — l'état le plus rassurant — alors qu'elle
    signifie ici « a tourné, a planté, et on a perdu le verdict ».

    D'où : une seconde tentative sur une connexion NEUVE, puis, en dernier ressort, un log
    `CRITICAL` — bruyant et non un `exception` noyé dans le flux. Jamais de silence.
    """
    if _ecrire_erreur(conn, execution_id, case_id, message):
        return

    try:
        secours = get_initialized_db()
    except Exception:
        logger.critical(
            "[run] exécution %s : le verdict d'échec est PERDU (connexion de secours "
            "impossible). La ligne reste 'not_executed' alors que le test a tourné. Cause "
            "initiale : %s", execution_id, message)
        return
    try:
        if not _ecrire_erreur(secours, execution_id, case_id, message):
            logger.critical(
                "[run] exécution %s : le verdict d'échec est PERDU malgré une connexion neuve. "
                "La ligne reste 'not_executed' alors que le test a tourné. Cause initiale : %s",
                execution_id, message)
    finally:
        secours.close()


def submit_review(conn, case_id: int, version_id: int, *, approved: bool,
                  reviewer: str, comment: str, repair_budget: int | None = None):
    """Enregistre une décision de relecture et renvoie le gate qui en découle."""
    return review_gate.submit_review(
        ReviewRepo(conn), case_id=case_id, version_id=version_id,
        approved=approved, reviewer=reviewer, comment=comment,
        repair_budget=repair_budget)
