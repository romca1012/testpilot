"""Ajout de cas à un module : spec → analyse → découpage → génération → gate (décision 0006,
étendue au §9 « génération multi-cas », 2026-08-05).

« Ajouter des cas » NE crée PAS une coquille vide. Le parcours part toujours d'une
**spécification** : on identifie ses **user stories**, et pour chacune on génère l'**ensemble
complet des cas nécessaires pour la couvrir** — un nombre VARIABLE, jamais fixé d'avance, jamais
maximal (le plus petit ensemble qui couvre tout, sans redondance — le découpage, §9a, porte cette
règle dans son prompt). Chaque user story devient une **Section** (`case_group`, pas une nouvelle
entité). Un cas sans version ni Gherkin ne doit jamais exister dans le référentiel — il afficherait
un cas qui ne teste rien (§3).

Le pipeline existant n'est PAS réinventé : `propose_metier` → `GenerationAgent.generate()` reste
UN cas par appel, testé comme tel. Ce module se contente de **planifier** (découpage) puis de
**répéter** ce pipeline une fois par cas planifié.

La génération est longue et coûteuse (LLM) : elle tourne en tâche de fond, avec un job suivi
PAR ÉCRIT (`GenerationJobRepo`, migration 29, 2026-08-07) — même schéma que les exécutions
(202 + polling), mais plus jamais un simple dict Python en mémoire : un job en mémoire disparaît
d'un coup si le serveur redémarre pendant qu'il tourne (plusieurs minutes de dry-run réel), et
l'écran reste bloqué sans jamais pouvoir dire pourquoi — vécu en conditions réelles le 07/08,
pris pour un simple « timeout ».
"""

from __future__ import annotations

import logging
import re
import uuid

from testpilot import config
from testpilot.api.services import notification_service
from testpilot.store.db import get_initialized_db
from testpilot.store.repositories import CaseRepo, DuplicateName, GenerationJobRepo, ModuleRepo

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Erreur métier de déclenchement (traduite en HTTP par la route)."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code  # not_found | invalid_spec | duplicate | no_connection | invalid_state | invalid_metier
        self.detail = detail


def get_job(conn, job_id: str) -> dict | None:
    """Rend le job — depuis la base (migration 29), jamais un dict en mémoire. Un job "running"
    resté bloqué trop longtemps est automatiquement réinterprété en échec par
    `GenerationJobRepo.get` (voir sa docstring) : cette fonction n'a rien de plus à faire."""
    return GenerationJobRepo(conn).get(job_id)


# Un slug nomme le fichier .feature, MAIS AUSSI le dossier temporaire d'exécution ET, dans ce
# dossier, le fichier `<slug>_steps.py` (behave_runner.py) — il apparaît donc DEUX FOIS dans un
# même chemin. Mesuré le 2026-08-05 : un titre de cas généré par l'IA (une phrase, pas un
# libellé court — « Le formulaire de mutation payeur refuse les codes payeur contenant des
# lettres ou caractères spéciaux ») produisait un slug de ~100 caractères, doublé dans le
# chemin, qui dépassait la limite Windows (260 caractères) — `[Errno 2] No such file or
# directory`, sans rapport apparent avec la vraie cause. 40 caractères, doublés, laissent une
# marge confortable même sur un profil Windows profondément imbriqué.
_SLUG_MAX = 40


def slugify(text: str) -> str:
    """Titre → slug de fichier .feature (ascii, minuscules, underscores), BORNÉ en longueur.

    Un hachage court est ajouté à la coupe : deux titres qui partagent le même préfixe long
    (fréquent — l'IA varie souvent la fin d'un titre, pas son début) ne doivent pas produire le
    même slug tronqué, ce que `unique_feature_slug` ne pourrait alors distinguer que par un
    suffixe numérique arbitraire.
    """
    import hashlib
    import unicodedata
    text = unicodedata.normalize("NFKD", text or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not text:
        return "cas"
    if len(text) > _SLUG_MAX:
        empreinte = hashlib.sha1(text.encode("ascii")).hexdigest()[:6]
        text = f"{text[:_SLUG_MAX].rstrip('_')}_{empreinte}"
    return text


def unique_feature_slug(conn, base: str) -> str:
    """Slug libre : un slug = un fichier ``.feature`` sur disque, donc unique GLOBALEMENT.

    Deux cas — d'un même module ou de deux modules différents — ne peuvent pas partager de slug,
    sinon leurs .feature s'écraseraient l'un l'autre. Appelé UNE FOIS PAR CAS (§9b) : chaque cas
    planifié par le découpage obtient son propre fichier.
    """
    cases = CaseRepo(conn)
    slug = base
    suffix = 2
    while cases.feature_slug_taken(slug):
        slug = f"{base}_{suffix}"
        suffix += 1
    return slug


def start_generation(conn, module_id: int, *, spec_content: str, title: str = "",
                     author: str = "", group_id: int | None = None) -> tuple[str, dict]:
    """Valide la demande et prépare le job. Renvoie (job_id, paramètres de la tâche de fond).

    ⚠️ Aucune vérification de titre/slug ICI : avec un seul cas, le titre à créer était connu
    d'avance (`body.title`) et pouvait être validé avant de payer le LLM. Avec le découpage (§9a),
    les titres RÉELS ne sont connus qu'APRÈS l'appel de découpage — l'unicité (par Section, via
    `CaseRepo.ensure_title_free`) et le slug (`unique_feature_slug`) se vérifient donc à la
    persistance de CHAQUE cas (`resume_generation`), pas ici.

    `group_id` (étape 3bis, 2026-08-07) : la Section choisie AVANT la génération, pour TOUS les
    cas qui en sortiront — obligatoire côté écran, comme `module_id`. Vérifiée ICI, avant tout
    appel LLM (même raison que `verifier_connexion` juste après) : si elle n'existe pas ou
    n'appartient pas à ce module, autant le dire avant de payer quoi que ce soit plutôt qu'à la
    toute fin. `None` reste toléré (appel direct à l'API, hors écran) — repli sur l'enveloppe
    automatique, jamais un job qui refuse de démarrer pour autant.
    """
    module = ModuleRepo(conn).get(module_id)
    if module is None:
        raise GenerationError("not_found", f"module {module_id} introuvable")
    if not (spec_content or "").strip():
        raise GenerationError("invalid_spec", "la spécification est vide")
    if group_id is not None:
        from testpilot.store.repositories import CaseGroupRepo
        groupe = CaseGroupRepo(conn).get(group_id)
        if groupe is None or groupe["module_id"] != module_id:
            raise GenerationError("not_found", f"section {group_id} introuvable dans ce module")

    # ⚠️ La génération OBSERVE l'application (dry-run, smoke-check) : sans connexion complète, elle
    # observerait l'instance par défaut de la machine et écrirait un test taillé pour elle
    # (2026-07-24). On refuse avant le premier appel LLM — donc avant la première dépense.
    from testpilot.connectors.runtime_env import ConnexionIncomplete, verifier_connexion
    from testpilot.store.repositories import ProjectRepo
    try:
        verifier_connexion(ProjectRepo(conn).get(module["project_id"]))
    except ConnexionIncomplete as err:
        raise GenerationError("no_connection", err.message()) from err

    label = (title or "").strip() or f"Cas {module['name']}"

    job_id = uuid.uuid4().hex
    # Le contexte complet est écrit DÈS LE DÉPART (pas seulement à la pause `awaiting_metier`) :
    # un job "running" qui redémarre en cours de route garde de quoi être compris/diagnostiqué,
    # même s'il ne peut pas reprendre tout seul (le découpage et les passes métier restent à
    # refaire — coût assumé, voir `run_generation`).
    GenerationJobRepo(conn).creer(job_id, module_id=module_id, payload={
        "title": label, "spec_content": spec_content, "author": author, "group_id": group_id,
    })
    return job_id, {"module_id": module_id, "title": label, "spec_content": spec_content,
                    "author": author, "group_id": group_id}


def _record_generation_cost(conn, *, case_id: int | None, analysis_usd: float = 0.0,
                            decoupage_usd: float = 0.0, metier_usd: float = 0.0,
                            generation_usd: float = 0.0) -> None:
    """Écrit au ledger ce que la création de cas a coûté — analyse, découpage, métier ET
    génération, chacune sa propre ligne.

    ⚠️ **Sans ça, le §9 était inmesurable sur le chemin que les utilisateurs empruntent.**
    `CostRepo.add_entry` n'était appelé que par `cli.py` et `repair_service` : un cas créé par
    l'écran ne laissait **aucune trace** de son coût de génération — 42 % du budget cible sur le
    cas 1, invisible. La seule ligne `generation` du ledger venait d'un run CLI, et on prétendait
    juger le §9 dessus.

    **Une ligne par phase, pas une seule** : le ledger porte la `phase`, donc il doit dire *ce qui*
    a coûté, pas seulement combien (c'est la raison d'être de `breakdown_for_case`). Le découpage
    (§9a, un appel par génération) et la passe métier (§9b, un appel par cas planifié) sont deux
    phases NOUVELLES depuis la génération multi-cas (2026-08-05) — distinctes de `analysis` et
    `generation`, pour la même raison qu'elles n'ont pas le même modèle non plus (`MODEL_FAST`
    pour analyse/découpage/métier, `MODEL_GENERATION` pour la génération Gherkin) : les fusionner
    attribuerait la dépense au mauvais tarif et rendrait le total inexplicable.

    Aucun `execution_id` : **une génération n'a pas d'exécution** — elle la précède, et le cas
    peut n'être jamais exécuté. C'est précisément pourquoi le lien du ledger devait devenir
    `test_case_id` (migration 12).

    Best-effort : une écriture de comptabilité ne fait jamais échouer une génération qui a réussi
    — mais elle ne disparaît pas en silence (§4.6).

    ⚠️ **Une génération RATÉE coûte quand même, et elle s'inscrit quand même** (2026-07-22). Le
    code refusait d'écrire quand aucun cas n'avait été créé — pour ne pas imputer la dépense à un
    cas au hasard. Le raisonnement était juste, sa conséquence ne l'était pas : mesuré sur le banc,
    `sinistre_client` a brûlé **0,14 $ invisibles au budget**. Une génération qui cale en boucle
    pourrait en brûler beaucoup sans qu'aucun compteur ne bouge — exactement le risque que le §9
    est censé borner.

    `test_case_id` est **nullable**, et le total mensuel somme la période **sans filtrer sur le
    cas** : une ligne orpheline compte donc au budget, sans polluer aucun coût par cas. Ne pas
    imputer à un cas et ne rien inscrire du tout sont deux choses différentes — on avait pris la
    seconde en croyant prendre la première.

    ⚠️ **Multi-cas (§9b) : le découpage et les N passes métier sont inscrits SANS `test_case_id`,
    même quand des cas finissent par exister.** Au moment où ce coût est payé (`run_generation`),
    AUCUN cas n'existe encore — ils naissent tous ensemble à la validation, et un découpage qui
    planifie 5 cas dont 2 seulement sont retenus ne peut pas voir son coût réparti a posteriori
    sans arbitraire (lequel des 2 cas retenus « paie » pour les 3 écartés ?). L'orpheline documentée
    ci-dessus est le même mécanisme, appliqué délibérément ici plutôt que subi.
    """
    from testpilot.store.repositories import CostRepo
    for phase, model, cost in (
        ("analysis", config.MODEL_FAST, analysis_usd),
        ("decoupage", config.MODEL_FAST, decoupage_usd),
        ("metier", config.MODEL_FAST, metier_usd),
        ("generation", config.MODEL_GENERATION, generation_usd),
    ):
        if not cost:
            continue
        try:
            CostRepo(conn).add_entry(phase=phase, model=model, cost_usd=cost,
                                     source=config.COST_SOURCE, test_case_id=case_id)
        except Exception:
            logger.exception("[generation] coût %s de %s USD NON enregistré (cas %s) — le budget "
                             "§9 sera sous-évalué d'autant", phase, cost, case_id)
    total = analysis_usd + decoupage_usd + metier_usd + generation_usd
    if case_id is None and total:
        # Inscrit, mais sans propriétaire : on le DIT, pour que la dépense soit explicable.
        logger.warning("[generation] $%.4f dépensés SANS cas créé — inscrits au ledger sans "
                       "test_case_id (comptés au budget §9, imputés à aucun cas)", total)


def run_generation(job_id: str, *, module_id: int, title: str, spec_content: str,
                   author: str, group_id: int | None = None) -> None:
    """PASSE 4a — analyse la spec, la DÉCOUPE en user stories + cas planifiés (§9a), rédige le
    DOCUMENT MÉTIER de chacun, puis **s'arrête**.

    ⚠️ Ce job ne va PAS jusqu'au bout : il se met en `awaiting_metier` et attend qu'un humain
    valide (ou corrige, ou réduise) l'ensemble des cas proposés, à PLAT, sans regroupement imposé.
    `resume_generation` écrit ensuite le Gherkin de chaque cas retenu **depuis ce document
    validé**, tous dans la MÊME Section — celle déjà choisie AVANT cette passe (`group_id`, étape
    3bis, 2026-08-07). C'est la décision `0022` n°5, étendue à N cas par le §9 : on ne paie plus
    la passe technique (la plus chère) pour une
    intention fausse — ni pour un cas que l'humain aurait de toute façon supprimé à la validation.

    Rien n'est persisté à ce stade — aucun cas n'existe encore (la Section CIBLE, elle, existe déjà :
    choisie ou créée AVANT de lancer cette passe). Un cas qui n'aurait que son métier serait une
    coquille sans Gherkin, précisément ce que `0006` refuse. Le brouillon vit donc dans le job, en
    mémoire : si le serveur redémarre avant validation, le découpage et les passes métier sont à
    refaire, et c'est le prix assumé pour ne jamais salir le référentiel.
    """
    from testpilot.analysis.spec_analyzer import SpecAnalyzer
    from testpilot.generation.decoupage import propose_decoupage
    from testpilot.generation.metier_writer import propose_metier
    from testpilot.guardrails.cost_tracker import CostTracker

    conn = get_initialized_db(config.DB_PATH)
    try:
        # ⚠️ L'ANALYSE COÛTE, et son coût n'était compté NULLE PART — ni ici, ni en CLI.
        # `SpecAnalyzer()` sans `cost_tracker` laisse `plan.cost_usd` à 0.0 : un appel LLM
        # (MODEL_FAST) invisible sur les deux chemins. Le schéma prévoyait pourtant la phase
        # `analysis` depuis le début. On lui donne donc un tracker, et on écrit ce qu'il mesure.
        analysis_tracker = CostTracker()
        plan = SpecAnalyzer(cost_tracker=analysis_tracker).analyze_spec_content(
            slugify(title), spec_content)

        decoupage_tracker = CostTracker()
        stories = propose_decoupage(plan, cost_tracker=decoupage_tracker)
        if not stories:
            _record_generation_cost(conn, case_id=None,
                                    analysis_usd=analysis_tracker.total_cost,
                                    decoupage_usd=decoupage_tracker.total_cost)
            GenerationJobRepo(conn).maj(
                job_id, status="failed",
                error="le découpage n'a identifié aucune user story exploitable dans cette "
                      "spécification — reformulez-la ou détaillez-la davantage",
                cost_usd=analysis_tracker.total_cost + decoupage_tracker.total_cost)
            return

        # Liste PLATE (étape 3, 2026-08-07) : le découpage par user story reste un outil INTERNE
        # de l'IA (il l'aide à couvrir la spec sans redondance, §9a) mais ne crée plus AUCUN
        # conteneur — chaque cas rédigé ne fait qu'EMPORTER le nom de sa story, en simple repère
        # de lecture (`user_story`), jamais une Section imposée.
        cases: list[dict] = []
        metier_cost_total = 0.0
        for story in stories:
            for brief in story.cases:
                # ⚠️ Budget PAR CAS, pas cumulé sur tout le lot (audit 2026-08-07, B2, bloquant) :
                # un `metier_tracker` unique, réutilisé pour tous les cas, faisait grossir
                # `total_cost` d'un cas à l'autre jusqu'à dépasser `COST_LIMIT_PER_RUN_USD` —
                # après quoi TOUS les cas suivants du lot échouaient en cascade dès leur premier
                # appel, indépendamment de leur propre coût. Chaque cas repart avec son propre
                # budget ; `metier_cost_total` n'accumule que pour le RAPPORT, jamais pour la
                # décision du plafond.
                case_tracker = CostTracker()
                draft = propose_metier(plan, brief=brief.brief, cost_tracker=case_tracker)
                metier_cost_total += case_tracker.total_cost
                if not draft.complete:
                    # Titre + étapes + résultat attendu sont obligatoires (`0022` n°3.c). On
                    # ÉCHOUE le job ENTIER plutôt que de proposer un ensemble à trous : l'humain
                    # corrigerait une base fabriquée sans savoir ce qui vient du modèle et ce qui
                    # vient de nous — même prudence qu'en mono-cas, étendue à la boucle.
                    cout = (analysis_tracker.total_cost + decoupage_tracker.total_cost
                           + metier_cost_total)
                    _record_generation_cost(conn, case_id=None,
                                            analysis_usd=analysis_tracker.total_cost,
                                            decoupage_usd=decoupage_tracker.total_cost,
                                            metier_usd=metier_cost_total)
                    GenerationJobRepo(conn).maj(
                        job_id, status="failed",
                        error=f"le document métier de « {brief.title} » (user story « "
                              f"{story.user_story} ») est incomplet — relancez la génération",
                        cost_usd=cout)
                    return
                cases.append({**draft.as_dict(), "user_story": story.user_story})

        total_cost = (analysis_tracker.total_cost + decoupage_tracker.total_cost
                     + metier_cost_total)
        _record_generation_cost(conn, case_id=None, analysis_usd=analysis_tracker.total_cost,
                                decoupage_usd=decoupage_tracker.total_cost,
                                metier_usd=metier_cost_total)

        # Le contexte de reprise (module_id/title/author/spec_content/group_id) est déjà en base
        # depuis `start_generation` — inutile de le réécrire ici. `resume_generation` ne refait ni
        # l'analyse ni le découpage ni les passes métier — seule l'analyse est rejouée (elle
        # alimente l'agent en matière technique qu'un `TestPlan` ne peut pas porter d'un job à
        # l'autre, non sérialisable).
        GenerationJobRepo(conn).maj(job_id, status="awaiting_metier", cases=cases,
                                    cost_usd=total_cost)
    except Exception as exc:  # jamais laisser un job « en cours » sur un plantage
        logger.exception("[generation] job %s (découpage + passe métier) en échec : %s",
                         job_id, exc)
        GenerationJobRepo(conn).maj(job_id, status="failed", error=str(exc)[:300])
    finally:
        conn.close()


def validate_metier(conn, job_id: str, cases: list[dict]) -> dict:
    """Enregistre les cas VALIDÉS (éventuellement corrigés ou réduits) et prépare la reprise.

    `cases` — liste PLATE (étape 3, 2026-08-07) : `[{"title", "preconditions", "steps",
    "expected_result", "user_story"}, ...]`. Pas de `group_id` par cas ici (étape 3bis) : la
    Section est déjà fixée pour TOUT le job, choisie avant même la génération
    (`job["group_id"]`, écrit dès `start_generation`) — cette fonction n'a rien à en faire, elle
    est juste transportée telle quelle jusqu'à `resume_generation`.
    """
    jobs = GenerationJobRepo(conn)
    job = jobs.get(job_id)
    if job is None:
        raise GenerationError("not_found", "job introuvable")
    if job.get("status") != "awaiting_metier":
        raise GenerationError("invalid_state",
                              f"ce job n'attend pas de validation métier (état : {job['status']})")

    validated: list[dict] = []
    for c in cases:
        c = c or {}
        steps = [str(s).strip() for s in (c.get("steps") or []) if str(s or "").strip()]
        if not (str(c.get("title", "")).strip() and steps
                and str(c.get("expected_result", "")).strip()):
            raise GenerationError(
                "invalid_metier",
                f"« {c.get('title') or 'un cas'} » : titre, étapes et résultat attendu sont "
                "obligatoires pour chaque cas")
        validated.append({
            "title": str(c["title"]).strip(),
            "preconditions": str(c.get("preconditions", "") or "").strip(),
            "steps": steps,
            "expected_result": str(c["expected_result"]).strip(),
            "user_story": str(c.get("user_story", "") or "").strip(),
        })

    if not validated:
        raise GenerationError("invalid_metier",
                              "aucun cas retenu — il ne reste rien à générer")

    jobs.maj(job_id, status="running", cases=validated)
    return {"module_id": job["module_id"], "title": job["title"],
           "spec_content": job["spec_content"], "author": job["author"],
           "group_id": job.get("group_id"), "cases": validated}


def _auto_approuver(conn, case_id: int, version_id: int | None) -> None:
    """Approuve la version au titre de la validation métier (amendement §4.3, 2026-07-21).

    Le porteur a tranché que la validation du métier à la création vaut relecture : il n'y a plus
    de gate humain séparé. On approuve donc la version dès qu'elle est produite — TRACÉ (reviewer
    `validation-metier`), jamais silencieux. Sans ça, un run resterait bloqué faute d'approbation.
    """
    if version_id is None:
        return
    from testpilot.store.repositories import ReviewRepo
    from testpilot.verdict import review_gate
    try:
        review_gate.auto_approve_metier(ReviewRepo(conn), case_id=case_id, version_id=version_id,
                                        repair_budget=config.REPAIR_BUDGET_DEFAULT)
    except Exception:
        logger.exception("[generation] auto-approbation de la version %s (cas %s) échouée — "
                         "le cas restera à relire", version_id, case_id)


def _spec_from_metier(metier: dict) -> str:
    """Reconstruit une spécification textuelle depuis le métier d'un cas manuel, pour que
    l'analyse en extraie la matière technique (routes, modèles). Le métier EST l'intention validée
    par l'humain : on va donc droit à l'écriture du Gherkin, sans découverte ni pause."""
    lignes = [f"# {metier.get('title', '')}", ""]
    if metier.get("preconditions"):
        lignes += ["## Préconditions", str(metier["preconditions"]), ""]
    lignes.append("## Étapes")
    for i, s in enumerate(metier.get("steps") or [], start=1):
        lignes.append(f"{i}. {s}")
    lignes += ["", "## Résultat attendu", str(metier.get("expected_result", ""))]
    return "\n".join(lignes)


def start_automation(conn, case_id: int, *, author: str = "") -> tuple[str, dict]:
    """Prépare l'AUTOMATISATION d'un cas manuel : générer son test technique depuis son métier.

    Le cas manuel naît sans `feature_slug` (pas de .feature). On lui en attribue un ici — un run
    le retrouve par ce champ (§7). La génération écrira `{slug}.feature` et une NOUVELLE version
    portant le Gherkin, sur le MÊME cas (décision `0022` n°6).

    `author` (migration 32) : le compte qui a demandé cette automatisation — résolu par
    l'APPELANT, SYNCHRONE, avant toute mise en tâche de fond, transmis à `run_automation`.
    """
    import json as _json

    from testpilot.store.repositories import VersionRepo

    case = CaseRepo(conn).get(case_id)
    if case is None:
        raise GenerationError("not_found", f"cas {case_id} introuvable")

    # Même garde que la génération : écrire un test technique suppose d'observer l'application
    # DU projet, pas celle que la machine a par défaut (2026-07-24).
    from testpilot.connectors.runtime_env import ConnexionIncomplete, verifier_connexion
    from testpilot.store.repositories import ProjectRepo
    try:
        verifier_connexion(ProjectRepo(conn).get(case.get("project_id")))
    except ConnexionIncomplete as err:
        raise GenerationError("no_connection", err.message()) from err

    version = VersionRepo(conn).get(case.get("current_version_id")) or {}
    try:
        steps = [str(s) for s in _json.loads(version.get("test_steps") or "[]")]
    except Exception:
        steps = []
    metier = {
        "title": version.get("title") or case["title"],
        "preconditions": version.get("preconditions", ""),
        "steps": steps,
        "expected_result": version.get("expected_result", ""),
    }
    if not (metier["title"] and metier["steps"] and metier["expected_result"]):
        raise GenerationError(
            "invalid_metier",
            "ce cas doit avoir un titre, des étapes et un résultat attendu pour être automatisé")

    slug = case.get("feature_slug") or unique_feature_slug(conn, slugify(metier["title"]))
    CaseRepo(conn).set_feature_slug(case_id, slug)

    job_id = uuid.uuid4().hex
    GenerationJobRepo(conn).creer(job_id, module_id=case["module_id"],
                                  payload={"case_id": case_id, "slug": slug})
    return job_id, {"case_id": case_id, "module_id": case["module_id"], "slug": slug,
                    "spec_content": _spec_from_metier(metier), "metier": metier,
                    "author": author or "ui"}


def run_automation(job_id: str, *, case_id: int, module_id: int, slug: str,
                   spec_content: str, metier: dict, author: str = "ui") -> None:
    """Tâche de fond : écrit le Gherkin d'un cas manuel DEPUIS son métier, sur le cas existant."""
    from testpilot.analysis.spec_analyzer import SpecAnalyzer
    from testpilot.connectors.odoo import OdooConnector
    from testpilot.connectors.runtime_env import project_env
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.generation.agent import GenerationAgent
    from testpilot.guardrails.cost_tracker import CostTracker
    from testpilot.store.repositories import ProjectRepo, VersionRepo

    conn = get_initialized_db(config.DB_PATH)
    connector = None
    succes = False
    try:
        module = ModuleRepo(conn).get(module_id)
        project = ProjectRepo(conn).get(module["project_id"]) if module else None
        connector = OdooConnector.from_project(project)
        connector.connect()
        runner = BehaveRunner(connection=project_env(project),
                              project_id=(project or {}).get("id"))

        analysis_tracker = CostTracker()
        plan = SpecAnalyzer(cost_tracker=analysis_tracker).analyze_spec_content(slug, spec_content)

        agent = GenerationAgent(dry_runner=runner, connector=connector,
                                case_repo=CaseRepo(conn), version_repo=VersionRepo(conn))
        # `case_id` fourni → une NOUVELLE version est créée sur le cas EXISTANT (re-versioning),
        # avec le métier conservé et le Gherkin fraîchement écrit. Le gate rebloque (§4.3).
        # Pas de `group_id` sur ce chemin (§9c) : ce cas n'a pas de Section, `_persist` garde donc
        # le comportement d'avant pour `spec_content` (écrit sur la VERSION).
        result = agent.generate(plan, case_id=case_id, metier=metier, author=author, projet=project)

        _record_generation_cost(conn, case_id=case_id,
                                analysis_usd=analysis_tracker.total_cost,
                                generation_usd=result.cost_usd)

        if result.success:
            succes = True
            _auto_approuver(conn, case_id, result.version_id)
            GenerationJobRepo(conn).maj(job_id, status="done", case_ids=[case_id])
        else:
            GenerationJobRepo(conn).maj(job_id, status="failed",
                                 error=result.error or result.stopped_reason or "automatisation échouée")
    except Exception as exc:
        logger.exception("[automation] job %s en échec : %s", job_id, exc)
        GenerationJobRepo(conn).maj(job_id, status="failed", error=str(exc)[:300])
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                pass
        # Best-effort ABSOLU (2026-08-12) : prévenir qui a demandé cette automatisation ne doit
        # jamais empêcher la clôture du job, déjà enregistrée juste au-dessus.
        try:
            notification_service.notifier_fin_d_automatisation(
                conn, case_id=case_id, titre_cas=metier.get("title", ""), succes=succes,
                triggered_by=author)
        except Exception:
            logger.exception("[automation] job %s : notification non envoyée", job_id)
        conn.close()


def resume_generation(job_id: str, *, module_id: int, title: str, spec_content: str,
                      author: str, cases: list[dict], group_id: int | None = None) -> None:
    """PASSE 4b — pour CHAQUE cas validé, écrit son Gherkin dans LA MÊME Section — celle que
    l'utilisateur a choisie AVANT de lancer la génération (`group_id`, étape 3bis, 2026-08-07),
    pas cas par cas. Répète le pipeline mono-cas (`propose_metier` déjà passé,
    `GenerationAgent.generate()`) une fois par cas — rien n'est réinventé.

    ⚠️ Cette fonction ne crée plus AUCUNE Section elle-même : avant l'étape 3, elle en fabriquait
    une par user story. La Section existe déjà quand cette fonction s'exécute (choisie ou créée
    sur l'écran de spécification, avant même l'appel LLM). `group_id` absent, ou devenu invalide
    entre le lancement et la génération (Section supprimée entre-temps, très rare), replie TOUS
    les cas sur leur propre enveloppe automatique (`CaseRepo.create`) plutôt que d'échouer — validé
    UNE SEULE FOIS ici, pas cas par cas.
    """
    import dataclasses

    from testpilot.analysis.spec_analyzer import SpecAnalyzer
    from testpilot.connectors.odoo import OdooConnector
    from testpilot.connectors.runtime_env import project_env
    from testpilot.execution.behave_runner import BehaveRunner
    from testpilot.generation.agent import GenerationAgent
    from testpilot.guardrails.cost_tracker import CostTracker
    from testpilot.store.repositories import CaseGroupRepo, ProjectRepo, VersionRepo

    conn = get_initialized_db(config.DB_PATH)
    connector = None
    try:
        module = ModuleRepo(conn).get(module_id)
        project = ProjectRepo(conn).get(module["project_id"]) if module else None

        # Génération ET dry-run tapent l'application DU PROJET du module (décision 0005).
        connector = OdooConnector.from_project(project)
        connector.connect()
        runner = BehaveRunner(connection=project_env(project),
                              project_id=(project or {}).get("id"))

        # L'analyse est refaite ici, UNE SEULE FOIS pour toute la spec (partagée par tous les cas) :
        # elle alimente l'agent en matière technique (modèles, routes, champs requis) que le
        # document métier ne porte pas, et un `TestPlan` n'est pas sérialisable dans le job. Son
        # coût est réel, il est compté avec le reste — comme orpheline (voir plus bas) : aucun cas
        # particulier ne « paie » pour une analyse partagée par tous.
        analysis_tracker = CostTracker()
        plan = SpecAnalyzer(cost_tracker=analysis_tracker).analyze_spec_content(
            slugify(title), spec_content)

        agent = GenerationAgent(dry_runner=runner, connector=connector,
                                case_repo=CaseRepo(conn), version_repo=VersionRepo(conn))

        # La Section est celle CHOISIE PAR L'UTILISATEUR avant la génération — plus aucune
        # création automatique ici (voir docstring). Invalide ou disparue entre-temps (Section
        # supprimée pendant que le job tournait, très rare) : repli sur l'enveloppe 1:1 auto-créée
        # par `CaseRepo.create`, pour TOUS les cas — jamais un lot bloqué pour un ciblage périmé.
        # Validé UNE SEULE FOIS, pas à chaque itération de la boucle.
        erreur_section = ""
        if group_id is not None:
            groupe = CaseGroupRepo(conn).get(group_id)
            if groupe is None or groupe["module_id"] != module_id:
                erreur_section = ("la section choisie n'existe plus — les cas ont été créés "
                                  "chacun dans sa propre enveloppe")
                group_id = None

        case_ids: list[int] = []
        erreurs: list[str] = [erreur_section] if erreur_section else []
        for case in cases:
            # ⚠️ Budget PAR CAS, pas cumulé sur tout le lot (audit 2026-08-07, B2, bloquant) :
            # `agent.cost_tracker` était créé UNE FOIS avant la boucle et réutilisé pour chaque
            # cas — `total_cost` grossissait donc d'un cas à l'autre jusqu'à dépasser
            # `COST_LIMIT_PER_RUN_USD` (0,50 $ par défaut), après quoi TOUS les cas suivants du
            # lot échouaient en cascade dès leur premier appel, indépendamment de leur propre
            # coût — et le coût cumulé du lot entier était attribué au ledger du cas qui avait
            # fait déborder le plafond (double comptage). Chaque cas doit repartir avec son
            # propre budget, comme en génération mono-cas.
            agent.cost_tracker = CostTracker()
            # Chaque cas d'une même spec a besoin de son PROPRE fichier `.feature` : l'analyse
            # est partagée (`plan`), mais `module_name` (qui nomme le fichier) doit être
            # distinct par cas — d'où la copie du plan avec un slug propre à ce cas.
            slug = unique_feature_slug(conn, slugify(case["title"]))
            case_plan = dataclasses.replace(plan, module_name=slug)
            metier = {"title": case["title"], "preconditions": case["preconditions"],
                     "steps": case["steps"], "expected_result": case["expected_result"]}
            try:
                result = agent.generate(case_plan, group_id=group_id, metier=metier,
                                        module_id=module_id, title=case["title"],
                                        author=author, projet=project,
                                        refs=case.get("user_story", ""))
            except DuplicateName as exc:
                erreurs.append(f"« {case['title']} » : {exc}")
                continue
            except Exception as exc:
                # ⚠️ Un cas ne doit JAMAIS pouvoir faire échouer TOUT le lot (mesuré le
                # 2026-08-05) : les cas précédents de cette boucle sont déjà persistés en
                # base au moment où celui-ci plante — les perdre de vue parce qu'un cas
                # SUIVANT échoue techniquement serait pire que signaler ce seul échec et
                # continuer avec les autres.
                logger.exception("[generation] cas « %s » (job %s) en échec technique",
                                 case["title"], job_id)
                erreurs.append(f"« {case['title']} » : {exc}")
                continue

            # Le coût de CE cas (génération/Gherkin) lui est attribué directement — c'est le
            # seul poste dépensé APRÈS que le cas existe, donc le seul qu'on peut lui imputer
            # sans arbitraire.
            _record_generation_cost(conn, case_id=result.case_id,
                                    generation_usd=result.cost_usd)

            if result.success and result.case_id:
                _auto_approuver(conn, result.case_id, result.version_id)
                case_ids.append(result.case_id)
            else:
                erreurs.append(
                    f"« {case['title']} » : "
                    f"{result.error or result.stopped_reason or 'génération échouée'}")

        # L'analyse partagée : une seule ligne orpheline, plutôt qu'une répartition arbitraire
        # entre les cas produits (voir docstring de `_record_generation_cost`).
        _record_generation_cost(conn, case_id=None, analysis_usd=analysis_tracker.total_cost)

        if case_ids:
            GenerationJobRepo(conn).maj(job_id, status="done", case_ids=case_ids,
                                 error="; ".join(erreurs))
        else:
            GenerationJobRepo(conn).maj(job_id, status="failed",
                                 error="; ".join(erreurs) or "aucun cas généré")
    except Exception as exc:  # jamais laisser un job « en cours » sur un plantage
        logger.exception("[generation] job %s (passe Gherkin) en échec : %s", job_id, exc)
        GenerationJobRepo(conn).maj(job_id, status="failed", error=str(exc)[:300])
    finally:
        if connector is not None:
            try:
                connector.disconnect()
            except Exception:
                pass
        conn.close()
