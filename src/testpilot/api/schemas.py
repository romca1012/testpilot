"""DTO Pydantic de l'API — modèle à DEUX AXES exposé tel quel, jamais fusionné.

Les repos renvoient des dicts SQLite ; ces mappers projettent les champs voulus vers des
réponses stables. La séparation exécution/fonctionnel du §5 est préservée jusqu'au client.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict

from testpilot.verdict.status import MODE_AUTOMATIQUE

# ── Vocabulaires contrôlés du cas ─────────────────────────────────────────────
# ⚠️ **Ils vivent ICI, du côté serveur, et nulle part ailleurs.** La base, elle, ne porte AUCUN
# `CHECK` sur `type`/`etat` (précédent `angle`) : c'est ce qui permettra à un administrateur
# d'ajouter une valeur sans migration. La contrepartie est que le refus d'une valeur inconnue
# doit être fait quelque part — un seul endroit, celui qui sait rendre un message utile.
#
# Correspondance TestRail, adoptée le 2026-08-04 à partir de ses vraies catégories :
#   Functional / Regression / Acceptance / Smoke        → fonctionnel
#   Performance / Security / Usability / Compatibility  → non fonctionnel
#   Automated / Exploratory                             → hors de cet axe (ce sont des MÉTHODES,
#                                                          pas des catégories de vérification)
TYPES_CAS = ("fonctionnel", "non_fonctionnel")
ETATS_CAS = ("new", "design", "ready", "obsolete")
PRIORITES_CAS = ("low", "medium", "high")
TYPE_DEFAUT = "fonctionnel"
ETAT_DEFAUT = "new"


# ── Projet / Module (hiérarchie §7) ───────────────────────────────────────────
class ProjectSummary(BaseModel):
    id: int
    name: str
    description: str = ""
    connector_type: str = "odoo"
    # Version DÉCLARÉE de l'instance (ex. « 17 » pour Odoo 17) — chaîne libre, vide acceptée
    # explicitement : « indéterminée » est un choix légitime, jamais une valeur à forcer.
    connector_version: str = ""
    base_url: str = ""
    database: str = ""
    username: str = ""
    # password : jamais exposé par l'API (write-only, cf. décision 0005).
    # Migration 45 : calibration en ÉCRITURE pendant la génération — éteinte par défaut, décidée
    # par le porteur du projet (jamais activée implicitement, cf. `ProjectRepo.
    # set_calibration_writes_enabled`).
    calibration_writes_enabled: bool = False
    module_count: int = 0
    case_count: int = 0
    effective_role: str = ""


class ModuleSummary(BaseModel):
    id: int
    project_id: int
    name: str
    description: str = ""
    case_count: int = 0


class ProjectRef(BaseModel):
    id: int
    name: str


class ModuleRef(BaseModel):
    id: int
    name: str


# ── Cas ───────────────────────────────────────────────────────────────────────
class GroupSummary(BaseModel):
    """Spécification (case_group) — conteneur d'affichage : id, module, titre, nb de cas.

    `parent_group_id` (migration 28) : `None` = Section de premier niveau ; sinon, id de la
    Section qui porte cette Sous-section — c'est ce qui permet à l'écran de reconstruire l'arbre.
    """
    id: int
    module_id: int
    title: str
    case_count: int = 0
    parent_group_id: int | None = None


class CaseSummary(BaseModel):
    id: int
    title: str
    module: str  # nom métier lisible du module (jamais le slug technique)
    module_id: int | None = None
    project_id: int | None = None
    # Spécification (case_group) propriétaire — séparation 2026-07-19.
    # ⚠️ `angle` a été retiré (migration 26) : ce champ n'existe pas dans TestRail, et `type`
    # + le titre disent déjà ce qu'il prétendait dire.
    group_id: int | None = None
    group_title: str | None = None
    # Métadonnées non versionnées (décision 0022 n°3b) : elles ne changent pas ce que le test
    # vérifie. `refs` = tickets externes ; `estimate` alimentera le burndown.
    refs: str = ""
    estimate: str = ""
    # ── Type et État (2026-08-04) — les deux champs de TestRail qui manquaient ─────────────
    # `type` : ce que le cas VÉRIFIE (fonctionnel = le système fait-il ce qui est attendu ;
    # non fonctionnel = une qualité transversale : performance, sécurité, ergonomie…).
    # `etat` : où en est le DOCUMENT (new/design/ready/obsolete). ⚠️ Aucun automatisme ne le
    # touche — modifier un cas ne le remet PAS à zéro (arbitré : la remise à zéro appartient au
    # workflow de relecture Enterprise de TestRail, qui est une autre fonctionnalité).
    # Ils remplacent `validation_status`, qui était dérivé des exécutions et non modifiable.
    type: str = "fonctionnel"
    etat: str = "new"
    priority: str = "medium"  # étiquette de lecture — aucun ordre d'exécution promis
    last_execution_status: str | None = None
    last_functional_status: str | None = None
    last_executed_at: str | None = None
    # Version qui a produit le dernier verdict, et divergence éventuelle avec la version
    # COURANTE (décision 0016, option (iii)). Une tentative de réparation non adoptée écrit
    # quand même les `last_*` du cas : le verdict peut donc décrire une version rembobinée.
    # On le rend VISIBLE — jamais silencieux, et jamais « corrigé » en masquant un run réel.
    last_verdict_version_id: int | None = None
    verdict_from_other_version: bool = False
    # Le STATUT DE LECTURE, calculé par le SERVEUR (2026-07-24). Il vivait en TypeScript ; le
    # filtrage côté serveur aurait alors exigé de réécrire la règle en SQL — deux
    # implémentations qui divergent un jour, en silence. Un seul endroit décide désormais.
    statut: str = "untested"


class VersionOut(BaseModel):
    id: int
    version_number: int
    # Contenu MÉTIER figé dans cette version (décision 0022 n°10) — c'est ce que l'écran affiche
    # et ce que l'historique diffe. `test_steps` est une liste JSON sérialisée.
    title: str = ""
    preconditions: str = ""
    test_steps: str = ""
    expected_result: str = ""
    feature_content: str = ""
    steps_content: str = ""
    spec_hash: str = ""
    # D'où vient cette version, et ce qui a changé (décision 0014). Sans ça, une réparation
    # serait une boîte noire : l'humain verrait « v2 » sans savoir ce qui a bougé, donc sans
    # pouvoir ratifier en connaissance de cause.
    change_summary: str = ""
    created_by: str = ""
    created_at: str = ""


class ReviewOut(BaseModel):
    id: int
    version_id: int
    decision: str
    reviewer: str = ""
    comment: str = ""
    decided_at: str = ""


class LintWarning(BaseModel):
    step: str
    line: int
    kind: str
    message: str


class GateOut(BaseModel):
    allowed: bool
    needs_review: bool
    reason: str
    # Réparations autorisées par la relecture en cours (0014). 0 si non relue ou interdite.
    repair_budget: int = 0
    # Le défaut proposé au relecteur qui n'a pas d'avis — affiché, jamais imposé.
    repair_budget_default: int = 0
    # Avertissements NON-bloquants sur les assertions générées (décision 0008). N'affectent
    # jamais `allowed` : ils informent le relecteur, le gate reste souverain.
    lint_warnings: list[LintWarning] = []


class CaseARelireOut(BaseModel):
    """Un cas bloqué sur le gate de relecture — la LISTE que l'amendement §4.3-bis (2026-09-15)
    rend nécessaire : un cas dont l'approbation automatique a été refusée (points de vigilance)
    doit rester TROUVABLE, pas seulement bloqué. Sans cette liste, on retombe dans le bug qu'on
    corrige (cas 82) — bloqué, mais invisible."""
    case_id: int
    title: str
    module_name: str = ""
    version_id: int
    reason: str
    lint_warnings_count: int = 0


class ExecutionSummary(BaseModel):
    id: int
    test_case_id: int
    version_id: int
    execution_status: str
    functional_status: str
    scenarios_total: int = 0
    scenarios_passed: int = 0
    scenarios_failed: int = 0
    cost_usd: float = 0.0
    iterations: int = 0
    duration_seconds: float = 0.0
    started_at: str = ""
    running: bool = False
    # Replis « libellé → nom technique » tracés pendant le run (décision 0007, phase B+).
    # Informatif et NON-bloquant, à l'image des `lint_warnings` du gate : signale soit un step
    # mal paramétré, soit un champ réellement renommé côté application. Présent même sur un run
    # vert — c'est là que le repli serait autrement invisible.
    field_fallbacks: list[str] = []
    # Raison d'un plantage AVANT tout scénario (migration 11). Vide sur un run normal : un
    # échec de scénario s'explique par ses `scenario_results`, pas par ce champ.
    error_message: str = ""
    # Contexte de ce qui a tourné (rempli sur la liste globale). ``suite_name`` est réservé
    # à l'Exécution nommée transverse (§7) — null tant qu'elle n'est pas implémentée.
    case_title: str | None = None
    module_name: str | None = None
    suite_name: str | None = None
    # CONTRE QUOI ce test a tourné (migration 20). Vide sur les exécutions antérieures : « on ne
    # sait pas » est la vérité, une cible reconstituée depuis la configuration du jour serait un
    # mensonge. **Jamais le mot de passe.**
    target_url: str = ""
    target_database: str = ""
    target_username: str = ""
    # Statut de LECTURE calculé par le serveur — même règle que pour un cas (une seule source).
    statut: str = "untested"
    # Lot 05 (D5) : comment CETTE exécution a abouti, et la réserve « Réussi — à confirmer » calculée par le serveur.
    confiance: str = "nominale"
    a_confirmer: bool = False


class CaseDetail(BaseModel):
    case: CaseSummary
    project: ProjectRef | None = None   # fil d'Ariane Projet > Module > Cas
    module: ModuleRef | None = None
    current_version_id: int | None = None
    versions: list[VersionOut] = []
    reviews: list[ReviewOut] = []
    executions: list[ExecutionSummary] = []
    gate: GateOut | None = None


class ReorderCasesIn(BaseModel):
    """Nouvel ordre d'AFFICHAGE des cas d'un module (décision 0009).

    En LOT, pas un PATCH par cas : un glissement change N positions, et N appels laisseraient un
    ordre incohérent si l'un échouait. Le serveur recalcule les positions — la liste dit le
    RANG, pas l'index.
    """

    case_ids: list[int]


class ScenarioResultOut(BaseModel):
    scenario_name: str
    execution_status: str
    functional_status: str
    statut: str = "untested"
    cause_category: str = ""
    failure_type: str = ""
    error_summary: str = ""
    # Exposé pour rendre `cause_category` AUDITABLE (décision 0015) : sans le step en échec,
    # relire un classement passé demandait d'ouvrir la base à la main.
    step_text: str = ""


class ExecutionDetail(ExecutionSummary):
    scenarios: list[ScenarioResultOut] = []


class ArtifactOut(BaseModel):
    """Un fichier de la trace brute. `label` est le libellé MÉTIER — le nom technique reste
    disponible, mais ce n'est pas ce qu'on montre d'abord (§8 du brief)."""
    name: str
    size: int = 0
    label: str = ""


class ArtifactsOut(BaseModel):
    """La trace d'une exécution.

    ⚠️ `available=False` **avec sa raison** plutôt qu'une liste vide : « il n'y a pas de fichier »
    et « aucune trace n'a été conservée » ne veulent pas dire la même chose. Les confondre, c'est
    prendre une absence de signal pour un signal — le motif que ce projet traque partout.
    """
    available: bool
    reason: str = ""
    files: list[ArtifactOut] = []


# ── Actions ───────────────────────────────────────────────────────────────────
class RunResponse(BaseModel):
    execution_id: int
    status: str  # "running"


class ModuleDetail(BaseModel):
    module: ModuleSummary
    project: ProjectRef


class CasePatch(BaseModel):
    """Métadonnées de LECTURE d'un cas — celles qui ne changent pas ce que le test VÉRIFIE.

    Chaque champ est optionnel : seul ce qui est fourni change. `priority` l'était de fait
    (c'était le seul champ) ; le rendre explicitement optionnel permet de modifier l'État sans
    avoir à renvoyer la priorité, donc sans risquer d'écraser celle d'un autre onglet.
    """
    priority: str | None = None   # low | medium | high
    type: str | None = None       # fonctionnel | non_fonctionnel
    etat: str | None = None       # new | design | ready | obsolete


class CaseMoveIn(BaseModel):
    """Cible d'un déplacement/copie de cas entre Sections (migration 28, étape 2)."""
    group_id: int


class CaseMoveOut(BaseModel):
    """Ce qu'un déplacement/copie rend : l'id du cas concerné (le même pour un déplacement, un
    NOUVEAU pour une copie — c'est ce qui distingue les deux à l'écran)."""
    id: int


class CaseMetierIn(BaseModel):
    """Édition du contenu MÉTIER d'un cas (décision `0022`). Chaque champ est optionnel : seul ce
    qui est fourni change. Une modification d'un champ VERSIONNÉ crée une nouvelle version — jamais
    un écrasement (n°10). `refs`/`estimate` sont des métadonnées et n'en créent pas."""
    title: str | None = None
    preconditions: str | None = None
    test_steps: str | None = None      # liste JSON sérialisée
    expected_result: str | None = None
    refs: str | None = None
    estimate: str | None = None
    editor: str = "ui"
    # Version consultée par l'appelant à l'OUVERTURE du formulaire (audit 2026-09-07, édition
    # concurrente) — `None` désactive le contrôle (compatibilité des anciens clients).
    base_version_id: int | None = None


class CaseMetierOut(BaseModel):
    case: CaseSummary
    version_id: int | None = None      # None = rien de versionné n'a changé
    version_created: bool = False


class ScriptEditIn(BaseModel):
    """Édition DIRECTE du script généré (Gherkin + Python) — rôle Dev (2026-08-07)."""
    feature_content: str
    steps_content: str
    editor: str = "ui"
    base_version_id: int | None = None  # même garde-fou anti-édition-concurrente que CaseMetierIn


class SharedStepOut(BaseModel):
    """Un step de la bibliothèque partagée référencé par le `.feature` de la version consultée."""
    keyword: str
    label: str
    source: str = ""
    note: str = ""
    code: str = ""


class ScriptEffectifOut(BaseModel):
    """Script COMPLET réellement exécuté par une version — `steps_content` propre au cas +
    steps partagés qu'elle référence, résolus jusqu'à leur code (Phase 2, script consultable).

    `feature_content`/`steps_content` sont recopiés tels quels (mêmes valeurs que `VersionOut`) :
    l'écran garde son affichage actuel par défaut, ce DTO n'ajoute qu'une vue alternative."""
    feature_content: str = ""
    steps_content: str = ""
    shared_steps: list[SharedStepOut] = []
    steps_effectif: str = ""


class AddCaseIn(BaseModel):
    """Ajout d'un cas = fournir une SPEC (jamais une coquille vide — décision 0006).

    `group_id` (étape 3bis, 2026-08-07) : la Section CHOISIE PAR L'UTILISATEUR avant même de
    lancer la génération (existante, ou créée depuis cet écran) — tous les cas qui en sortiront y
    atterrissent. Obligatoire côté ÉCRAN (même règle que `module_id`), mais le type reste
    `int | None` ici : le serveur n'impose rien qu'un appel direct à l'API ne pourrait franchir,
    et un `group_id` absent repli simplement sur l'enveloppe automatique (jamais bloquant)."""
    # Refuser les anciens champs inconnus est une barrière de sécurité : `spec_path` permettait
    # autrefois à un client API de faire lire un chemin arbitraire SUR LE SERVEUR. Un chemin local
    # reste accepté par la CLI, jamais par une requête HTTP.
    model_config = ConfigDict(extra="forbid")

    spec_content: str = ""
    title: str = ""
    author: str = "ui"
    group_id: int | None = None


class MetierDraftOut(BaseModel):
    """Le document métier proposé par l'IA — à valider ou corriger avant l'écriture du Gherkin.

    `user_story` (étape 3, 2026-08-07) : la user story dont ce cas est issu — un simple REPÈRE DE
    LECTURE affiché en sous-titre sur l'écran de validation, jamais une Section imposée. L'IA
    continue à découper la spécification en user stories en interne (`decoupage.propose_decoupage`,
    ça l'aide à couvrir sans redondance), mais ce découpage ne crée plus AUCUN conteneur : c'est
    l'utilisateur qui choisit où chaque cas atterrit (`group_id` sur `CaseValidationIn`)."""
    title: str = ""
    preconditions: str = ""
    steps: list[str] = []
    expected_result: str = ""
    user_story: str = ""


class GenerationJobOut(BaseModel):
    job_id: str
    # running | awaiting_metier | done | failed
    # ⚠️ `awaiting_metier` n'est PAS un état d'attente technique : le job est arrêté et n'ira
    # nulle part tant qu'un humain n'aura pas validé l'ensemble des cas proposés (décision `0022`
    # n°5, étendue au §9, puis mise à plat à l'étape 3 : 2026-08-07).
    status: str
    case_ids: list[int] = []
    error: str = ""
    # Rempli uniquement en `awaiting_metier` — une liste PLATE (étape 3), plus de regroupement en
    # Sections imposé par l'IA.
    cases: list[MetierDraftOut] | None = None


class ConcurrencyQueueOut(BaseModel):
    """Visibilité minimale du plafond de tâches de fond partagé (`guardrails/concurrency.py`) —
    combien tournent réellement, combien patientent, quel est le plafond configuré. En mémoire du
    PROCESSUS : ne survit pas à un redémarrage, ne reflète qu'un seul processus (documenté)."""
    max_concurrent: int
    running: int
    waiting: int


class CaseValidationIn(BaseModel):
    """UN cas, tel que l'humain le valide — corrections comprises.

    C'est CE contenu qui fera foi pour l'écriture du Gherkin, pas la proposition de l'IA :
    l'humain peut tout réécrire, ou supprimer le cas de la liste (l'écran de validation le
    permet), c'est l'intérêt de la pause.

    ⚠️ Pas de `group_id` ici (étape 3bis, 2026-08-07, revient sur l'étape 3 initiale) : la Section
    est choisie UNE FOIS, avant même la génération (`AddCaseIn.group_id`), pas cas par cas sur cet
    écran. `user_story` reste un simple repère de LECTURE affiché ici (jamais une Section).
    """
    title: str
    preconditions: str = ""
    steps: list[str]
    expected_result: str
    user_story: str = ""


class MetierValidationIn(BaseModel):
    """L'ensemble des cas tel que l'humain le valide — une liste PLATE (étape 3, 2026-08-07)."""
    cases: list[CaseValidationIn]


class ProjectIn(BaseModel):
    name: str
    description: str = ""
    connector_type: str = "odoo"
    connector_version: str = ""
    base_url: str = ""
    database: str = ""
    username: str = ""
    password: str = ""  # secret : accepté en entrée, jamais relu en sortie


class ProjectPatch(BaseModel):
    """Édition d'un projet, connexion COMPRISE (décision `0005`).

    ⚠️ Défauts à `None`, pas à `""` — contrairement à `ProjectIn`. Sur un PATCH, `""` veut dire
    « vide ce champ » et `None` « n'y touche pas » : les confondre ferait effacer la connexion
    d'un projet à chaque renommage. C'est vital pour `password`, que l'API ne renvoie jamais —
    un écran d'édition l'affiche donc toujours vide, et le réenvoyer tel quel détruirait le
    secret enregistré.
    """
    name: str | None = None
    description: str | None = None
    connector_type: str | None = None
    connector_version: str | None = None
    base_url: str | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None  # secret : accepté en entrée, jamais relu en sortie
    # `None` = n'y touche pas, comme les autres champs de ce PATCH — pas de `""` ambigu possible
    # pour un booléen, mais la même discipline (silence = inchangé) s'applique.
    calibration_writes_enabled: bool | None = None


class ExplorationOut(BaseModel):
    """L'état de la cartographie d'un projet — ce que l'écran montre avant/après exploration.

    ⚠️ `mesure_le` est affiché systématiquement : la cartographie est une PHOTO qui vieillit, et
    tout ce qui la consomme doit dire de quand elle date (cf. `domain_model`).
    """
    explored: bool = False
    running: bool = False
    job_id: str = ""
    mesure_le: str = ""
    pages: int = 0
    transitions: int = 0
    champs: int = 0
    # Les règles de validation mesurées (motif, longueur, bornes). Affichées parce qu'elles sont le
    # seul indicateur VISIBLE qu'une cartographie est fraîche : routes et champs bougent peu, les
    # règles n'apparaissent qu'avec la mesure enrichie (cf. `exploration_service.etat`).
    contraintes: int = 0
    # Modèles BACK-OFFICE découverts par énumération de menus (2026-09-18, `discover_menus`,
    # Odoo uniquement) — seul signe visible que ce complément a bien tourné sur cette mesure.
    modeles_backoffice: int = 0
    resume: str = ""
    error: str = ""


class QualityDayOut(BaseModel):
    jour: str
    success: int = 0
    technical_error: int = 0
    blocked: int = 0
    not_executed: int = 0


class QualityOut(BaseModel):
    """Santé technique de la génération, dans le temps — le suivi de l'évolution de l'outil.

    Axe EXÉCUTION uniquement (un test qui tourne et trouve un bug est un succès technique).
    `ran_rate` = None quand aucune mesure : « rien mesuré » ≠ « 0 % de réussite ».
    """
    total: int = 0
    ran: int = 0
    technical_error: int = 0
    blocked: int = 0
    not_executed: int = 0
    ran_rate: float | None = None
    by_day: list[QualityDayOut] = []
    first_attempt: dict = {}


class ManualCaseIn(BaseModel):
    """Création d'un cas À LA MAIN (bouton « Ajouter un cas de test », sans IA).

    Titre + étapes + résultat attendu obligatoires (décision `0022` n°3.c) — un cas sans eux ne
    décrit rien. `test_steps` = liste JSON, comme partout ailleurs.

    `group_id` (2026-09-11) : la Section DÉJÀ CHOISIE en arrivant sur ce formulaire — parité
    TestRail, où « Add Test Case » se lance TOUJOURS depuis une Section déjà ouverte, et le cas y
    atterrit directement plutôt que dans une section neuve créée pour lui seul. `None` = aucune
    Section choisie (venu du bouton générique « Ajouter un cas », pas d'une Section précise) :
    le cas garde alors le comportement d'avant (auto-enveloppé dans sa propre Section).
    """
    title: str
    preconditions: str = ""
    test_steps: list[str] = []
    expected_result: str = ""
    group_id: int | None = None


class SpecExtractOut(BaseModel):
    """Texte extrait d'un fichier téléversé, pour pré-remplir la zone de génération."""
    text: str
    filename: str = ""


class RunIn(BaseModel):
    """Création d'un run (campagne). `case_ids` n'est utilisé qu'en mode `frozen`.

    ⚠️ `mode` est le MODE D'EXÉCUTION (2026-08-04) : `automatique` (la machine joue les cas) ou
    `manuelle` (un humain les joue et saisit ce qu'il a constaté). Il se choisit **à la création**,
    parce que c'est lui qui décide des gestes offerts ensuite — lancer, ou saisir.
    """
    name: str
    description: str = ""
    refs: str = ""
    selection_mode: str = "frozen"  # all | frozen
    mode: str = MODE_AUTOMATIQUE    # manuelle | automatique
    case_ids: list[int] = []
    # Lot 05 (D5) : campagne STRICTE — jouée sans résolution adaptative ni retry (le vert ne peut venir que de la cascade
    # déterministe). Faux par défaut : le comportement d'une campagne créée sans ce champ ne change pas.
    strict: bool = False


class RunCaseResult(BaseModel):
    """Un cas DANS un run, avec son DERNIER résultat — automatique ou manuel — ou rien si non testé."""
    id: int
    title: str
    # Les deux axes, lus par jointure sur l'exécution. ⚠️ **Vides sur un résultat MANUEL**, et
    # c'est voulu : personne n'a mesuré quoi que ce soit, l'écran ne doit donc rien afficher.
    execution_status: str | None = None
    functional_status: str | None = None
    execution_id: int | None = None
    # ── COMMENT ce résultat a été obtenu (2026-08-04) ──────────────────────────────────────
    # `''` = aucun résultat. `automatique` = une machine l'a produit, la trace est consultable.
    # `manuelle` = un humain a joué le test à la main. C'est la donnée qui empêche le statut de
    # mentir : elle est STOCKÉE dans le registre, jamais déduite de la présence d'une exécution.
    result_mode: str = ""
    statut_manuel: str = ""
    comment: str = ""
    created_by: str = ""
    result_at: str = ""
    # Voir `statut` de CaseSummary : calculé par le serveur, jamais redérivé à l'écran.
    statut: str = "untested"
    # Lot 05 (D5) : comment le verdict a été obtenu, et « Réussi — à confirmer » (un `passed` non nominal), calculés par
    # le serveur. `nominale` sur un résultat manuel ou ancien : rien n'a été mesuré, aucune réserve n'est inventée.
    confiance: str = "nominale"
    a_confirmer: bool = False
    # Qui SUPERVISE ce cas dans CETTE campagne (2026-09-14, traçabilité — inspiré de TestRail).
    # `""` = personne assigné, jamais un nom deviné. Vaut pour un cas manuel comme automatique.
    assigned_to: str = ""


class AssignmentIn(BaseModel):
    """`""` retire l'assignation — même convention que `comment`/`refs` ailleurs : une chaîne
    vide EST la valeur « rien », pas un champ à ignorer."""
    assigned_to: str = ""


class AssignmentOut(BaseModel):
    case_id: int
    assigned_to: str = ""
    assigned_by: str = ""
    assigned_at: str = ""


class ResultIn(BaseModel):
    """Un résultat SAISI À LA MAIN, dans une campagne (écran « Ajouter un résultat »).

    Le statut est **obligatoire et sans défaut** : c'est le seul champ que l'écran ne pré-remplit
    pas. Proposer « Passed » d'avance transformerait la saisie en un clic distrait — exactement ce
    qui rend le mot « testé » sans valeur dans la plupart des outils.

    ⚠️ **Pas de « défauts liés » ni de « temps passé »** en V1 (arbitré) : TestRail les a, nous
    ne les tiendrions pas — un champ qu'on remplit à moitié ment plus qu'un champ absent.
    """
    statut: str
    comment: str = ""


class AttachmentOut(BaseModel):
    """Une pièce jointe d'un résultat — typiquement la capture d'écran qui atteste du constat.

    ⚠️ **Le nom SUR LE DISQUE n'est pas exposé**, et ce n'est pas de la pudeur : le client n'en a
    aucun usage (il télécharge par identifiant numérique), et ne pas le publier retire l'idée même
    qu'un nom de fichier puisse voyager depuis ou vers le serveur.
    """
    id: int
    filename: str               # le nom d'origine — étiquette d'AFFICHAGE, jamais un chemin
    content_type: str           # celui que le serveur servira, déduit de la liste blanche
    size_bytes: int = 0


class ResultOut(BaseModel):
    """Un résultat du registre, joué automatiquement ou manuellement.

    ⚠️ `execution_status` / `functional_status` sont **vides sur un résultat manuel** : ils sont
    lus par jointure sur l'exécution, et un résultat manuel n'en a aucune. Aucune valeur n'est
    inventée pour « remplir » l'affichage.
    """
    id: int
    mode: str                   # manuelle | automatique
    statut: str                 # l'étiquette de lecture, calculée par le serveur
    statut_manuel: str = ""
    comment: str = ""
    created_by: str = ""
    created_at: str = ""
    execution_id: int | None = None
    execution_status: str | None = None
    functional_status: str | None = None
    # Lot 05 (D5) : voir `RunCaseResult.confiance`.
    confiance: str = "nominale"
    a_confirmer: bool = False
    # La preuve visuelle qui accompagne un constat humain (2026-08-05). Liste VIDE par défaut :
    # la pièce jointe est optionnelle, et un résultat sans fichier reste un résultat entier.
    attachments: list[AttachmentOut] = []


class RunArchiveIn(BaseModel):
    """Clôture (ou réouverture) d'une campagne. Réversible : une clôture par erreur ne doit pas
    être irrattrapable."""
    archived: bool = True


class RunSummary(BaseModel):
    id: int
    project_id: int
    name: str
    status: str            # draft | running | completed
    selection_mode: str
    # Le MODE D'EXÉCUTION de la campagne : c'est lui qui décide des gestes offerts par l'écran
    # (une campagne automatique se lance, une campagne manuelle se saisit — jamais les deux).
    mode: str = MODE_AUTOMATIQUE
    case_count: int = 0
    tested_count: int = 0  # cas ayant un résultat dans ce run → % de complétion
    # Parmi eux, ceux dont le dernier résultat a été joué À LA MAIN. Exposé dès maintenant pour
    # qu'un « 100 % » ne puisse jamais laisser croire que tout a été prouvé par la machine.
    manuel_count: int = 0
    # Lot 05 (D5) : campagne stricte, et compteur « verts à confirmer » (réussis dont la confiance n'est pas nominale).
    strict: bool = False
    verts_a_confirmer: int = 0
    # Archivé = LECTURE SEULE (on ne relance plus). Distinct du statut : `completed` dit où en
    # est l'exécution, `is_archived` dit si on a le droit d'y toucher.
    is_archived: bool = False
    created_at: str = ""
    # Le Plan de test (migration 43) qui regroupe cette campagne, s'il y en a un — RÉFÉRENCE
    # SOUPLE (colonne simple sans FK dure, voir `db.py::_migrate_43...`). `None` = hors de tout
    # plan, l'état normal d'une campagne créée avant cette fonctionnalité ou jamais rattachée.
    plan_id: int | None = None


class RunDetailOut(BaseModel):
    run: RunSummary
    description: str = ""
    refs: str = ""
    cases: list[RunCaseResult] = []
    # Contre quoi cette campagne a RÉELLEMENT tourné, lu sur ses exécutions (jamais sur la
    # connexion actuelle du projet, qui a pu changer depuis). Vide = aucun cas encore joué.
    # `target_mixed` : plusieurs cibles distinctes — la connexion a bougé en cours de campagne,
    # ce qui rend les résultats non comparables entre eux. On le DIT au lieu d'en choisir une.
    target_url: str = ""
    target_database: str = ""
    target_mixed: bool = False
    # ⚠️ **La liste des statuts saisissables vient du SERVEUR**, et l'écran l'itère telle quelle.
    # Elle existe déjà en Python (`STATUTS_MANUELS`) et dans un `CHECK` de la base ; la retaper en
    # TypeScript en ferait une troisième version, qui divergerait un jour en silence. C'est le
    # défaut qu'on a déjà payé une fois ici, avec le statut de lecture (§3.6 ONBOARDING).
    statuts_manuels: list[str] = []


class ScheduledRunIn(BaseModel):
    """Création d'une planification récurrente (migration 43). `case_ids` n'est utilisé qu'en
    mode `frozen`, comme pour `RunIn`.

    ⚠️ **Aucun champ `mode`** : une planification est TOUJOURS automatique — personne n'est
    présent à 2h du matin pour saisir un résultat manuel. Ce n'est pas caché à l'écran, ce choix
    n'existe structurellement pas ici (voir `scheduler_service.py`)."""
    name: str
    selection_mode: str = "frozen"     # all | frozen
    case_ids: list[int] = []
    frequency: str                     # daily | weekly
    hour: int
    minute: int
    weekday: int | None = None         # requis si frequency == "weekly" (0=lundi)


class ScheduledRunOut(BaseModel):
    id: int
    project_id: int
    name: str
    selection_mode: str
    frequency: str
    hour: int
    minute: int
    weekday: int | None = None
    is_active: bool = True
    created_by: str = ""
    created_at: str = ""
    last_run_id: int | None = None
    last_triggered_at: str | None = None


class ScheduledRunPatchIn(BaseModel):
    is_active: bool | None = None


class PlanIn(BaseModel):
    """Un Plan regroupe plusieurs campagnes existantes pour un rapport consolidé — purement
    organisationnel, ne change rien à l'exécution ni au lancement d'une campagne."""
    name: str
    description: str = ""
    refs: str = ""


class PlanPatchIn(BaseModel):
    """Édition d'un plan existant — mêmes champs que la création, tous optionnels (seuls ceux
    fournis changent). Jamais `project_id` : un plan ne change pas de projet."""
    name: str | None = None
    description: str | None = None
    refs: str | None = None


class PlanOut(BaseModel):
    id: int
    project_id: int
    name: str
    description: str = ""
    refs: str = ""
    created_by: str = ""
    created_at: str = ""


class PlanDetailOut(BaseModel):
    plan: PlanOut
    # Chaque run garde son PROPRE résumé complet (dont `mode`) — jamais fusionné en un seul
    # chiffre qui mélangerait des verdicts humains (manuelle) et des verdicts machine
    # (automatique) sans le dire.
    runs: list[RunSummary] = []


class ResultAilleurs(BaseModel):
    """Un résultat de CE cas dans UNE campagne — la sienne, ou une autre.

    Sert deux affichages de la page d'un test : la courbe des 30 derniers jours, et « le même cas
    dans les autres campagnes ». Volontairement plus maigre que `ResultOut` : ni commentaire ni
    axes, parce qu'on répond ici à « où et quand », pas à « pourquoi ».
    """
    run_id: int
    run_name: str
    statut: str
    mode: str
    created_by: str = ""
    created_at: str = ""
    # Lot 05 (D5) : « Réussi — à confirmer » dans CETTE campagne, calculé par le serveur.
    a_confirmer: bool = False


class TestDansRunOut(BaseModel):
    """**UN CAS DANS UNE CAMPAGNE** — l'objet que TestRail appelle un « test » (`T…`), distinct du
    cas du référentiel (`C…`).

    ⚠️ **Pourquoi il a sa propre identité.** Le couple campagne × cas existait déjà en base (une
    ligne de `test_result` par résultat), mais aucune URL ni aucun écran ne le nommait : cliquer un
    cas dans une campagne menait soit au rapport technique d'UNE exécution, soit à la fiche du cas —
    jamais à « ce cas, ici, dans cette campagne ». Le statut, les résultats et les commentaires
    appartiennent pourtant à ce couple, pas au cas.

    Ce que le cas apporte (titre, type, priorité, estimation, références, état) est **recopié à la
    lecture**, jamais figé : il n'y a pas de snapshot des cas à la clôture d'une campagne
    (`RunRepo.archive`), et cet écart reste assumé plutôt que masqué.
    """
    run_id: int
    run_name: str
    run_archived: bool = False
    run_mode: str = MODE_AUTOMATIQUE
    case_id: int
    title: str
    # Le bloc de métadonnées, lu sur le cas (jamais réinventé ici).
    type: str = "fonctionnel"
    etat: str = "new"
    priority: str = "medium"
    estimate: str = ""
    refs: str = ""
    # Le statut du DERNIER résultat dans cette campagne — calculé par le serveur, comme partout.
    statut: str = "untested"
    # Lot 05 (D5) : la réserve du DERNIER résultat (`a_confirmer` = un `passed` non nominal), calculée par le serveur.
    confiance: str = "nominale"
    a_confirmer: bool = False
    results: list[ResultOut] = []
    # Les voisins DANS LA CAMPAGNE (jamais dans le module) : les flèches précédent/suivant servent
    # à enchaîner les tests d'une session de recette, pas à parcourir le référentiel.
    prev_case_id: int | None = None
    next_case_id: int | None = None
    # Le même cas ailleurs — y compris dans cette campagne (l'écran filtre ce qu'il montre où).
    historique_du_cas: list[ResultAilleurs] = []


class ActiviteOut(BaseModel):
    """Un résultat posé dans une campagne, vu depuis le fil d'activité."""
    case_id: int
    case_title: str
    statut: str
    mode: str
    created_by: str = ""
    created_at: str = ""
    # Lot 05 (D5) : « Réussi — à confirmer », calculé par le serveur.
    a_confirmer: bool = False


class RunActiviteOut(BaseModel):
    """Le fil chronologique d'une campagne + de quoi mesurer son avancement.

    ⚠️ **Une seule réponse pour deux écrans** (Activité et Progression). La progression est
    l'activité comptée autrement : le nombre de cas ayant reçu leur PREMIER résultat, jour après
    jour, rapporté à `case_count`. Une seconde route qui recompterait la même chose en SQL
    finirait par diverger de celle-ci sans que personne le voie.
    """
    run_id: int
    run_name: str
    case_count: int = 0
    events: list[ActiviteOut] = []


class ModuleIn(BaseModel):
    name: str
    description: str = ""


class GroupIn(BaseModel):
    """Création d'une Spécification. `spec_content` est LE DOCUMENT source (décision `0022`).

    ⚠️ Pas de `spec_hash` : l'empreinte est recalculée par le repo depuis le document, jamais
    reçue de l'appelant — sinon elle pourrait mentir sur ce qu'elle référence.

    `parent_group_id` (migration 28) : fourni pour créer une SOUS-section sous une Section
    existante du même module. `None` (défaut) = Section de premier niveau, comme avant.
    """
    title: str
    description: str = ""
    spec_content: str = ""
    parent_group_id: int | None = None


class GroupPatch(BaseModel):
    """Édition partielle : `None` = « ne touche pas à ce champ » (≠ « vide-le »)."""
    title: str | None = None
    description: str | None = None
    spec_content: str | None = None


class GroupMoveIn(BaseModel):
    """Cible d'un glisser-déposer de Section (étape 2bis) — `None` promeut au premier niveau.

    ⚠️ Pas de pendant « copie » : contrairement à un cas, une Section ne se duplique jamais
    (voir `CaseMoveIn`, réservé aux cas)."""
    parent_group_id: int | None = None


class GroupDetail(BaseModel):
    """La Spécification AVEC son document — la vue de l'écran d'édition.

    `GroupSummary` (sans le document) reste la vue des listes et de l'arbre : une liste de
    spécifications n'a pas à charger N documents complets.
    """
    id: int
    module_id: int
    title: str
    description: str = ""
    spec_content: str = ""
    spec_hash: str = ""
    case_count: int = 0
    parent_group_id: int | None = None
    created_at: str = ""
    updated_at: str = ""


def group_detail(row: dict) -> GroupDetail:
    return GroupDetail(
        id=row["id"], module_id=row["module_id"], title=row["title"],
        description=row.get("description", ""), spec_content=row.get("spec_content", ""),
        spec_hash=row.get("spec_hash", ""), case_count=row.get("case_count", 0),
        parent_group_id=row.get("parent_group_id"),
        created_at=row.get("created_at", ""), updated_at=row.get("updated_at", ""))


class ReviewIn(BaseModel):
    approved: bool
    reviewer: str = "ui"
    comment: str = ""
    # Tentatives de réparation que cette approbation autorise (décision 0014, option C).
    # None → le défaut de configuration. 0 → réparation interdite pour cette version.
    # Réparer exige d'exécuter, et §4.3 exige le gate avant toute exécution : c'est donc le
    # gate qui autorise, explicitement — il n'est pas contourné par la boucle.
    repair_budget: int | None = None


class ReviewResponse(BaseModel):
    decision: str
    # ⚠️ Plus de `validation_status` : la relecture porte sur la VERSION, et c'est le `gate`
    # ci-dessous qui dit ce qu'elle autorise. Renvoyer en plus un statut de cas laissait croire
    # que la décision s'inscrivait à deux endroits.
    gate: GateOut
    # Ce que l'approbation a réellement autorisé — renvoyé pour que l'UI montre la valeur
    # RETENUE, pas celle envoyée (elles diffèrent si le champ était vide).
    repair_budget: int = 0


# ── Réglages d'instance (2026-08-04) ──────────────────────────────────────────
class SettingOut(BaseModel):
    """Un réglage, sa valeur EFFECTIVE et **d'où elle vient**.

    ⚠️ `source` n'est pas décorative : la base l'emporte sur la variable d'environnement, qui
    l'emporte sur le défaut du code. Sans cette information, un exploitant dont la variable est
    ignorée n'a aucun moyen de comprendre pourquoi.
    """
    key: str
    value: str
    source: str          # db | env | default
    description: str = ""
    admin_only: bool = False   # écriture réservée à l'Admin (2026-08-11) — la lecture reste ouverte
    # `secret` (2026-08-12) : `value` est alors `SettingRepo.MASQUE_SECRET` ou "" — JAMAIS le
    # vrai mot de passe, y compris pour l'Admin. Voir `SettingRepo.tous()`.
    secret: bool = False


class SettingPatch(BaseModel):
    """Une valeur VIDE efface le réglage : l'environnement (puis le défaut) reprend la main."""
    value: str = ""


class TimezoneOption(BaseModel):
    value: str
    label: str


class SecurityStatusOut(BaseModel):
    password_min_length: int
    password_hash: str
    session_days: int
    cookie_http_only: bool
    cookie_same_site: str
    cookie_secure: bool
    session_secret_external: bool
    data_secret_external: bool
    login_max_failures: int
    login_window_minutes: int
    production_ready: bool


class SmtpTestIn(BaseModel):
    destinataire: str


class SmtpTestOut(BaseModel):
    """Jamais une exception brute : un Admin qui teste sa configuration doit comprendre
    POURQUOI ça a échoué (hôte injoignable, authentification refusée, etc.)."""
    succes: bool
    erreur: str = ""


# ── Comptes utilisateurs (2026-08-07) ─────────────────────────────────────────
class UserOut(BaseModel):
    """Un compte, TEL QUE L'ÉCRAN ADMIN LE MONTRE — jamais `password_hash`, qui n'a rien à faire
    hors de la base, même haché."""
    id: int
    username: str
    role: str
    email: str = ""
    is_active: bool
    created_at: str


# ── Accès par projet (migration 31, 2026-08-10) ───────────────────────────────
class ProjectAccessOverrideOut(BaseModel):
    user_id: int
    username: str
    role: str          # 'no_access' ou un des 4 rôles


class ProjectGroupAccessOut(BaseModel):
    group_id: int
    group_name: str
    role: str
    member_count: int = 0


class ProjectAccessOut(BaseModel):
    """L'accès à un projet, tel que l'écran Admin le montre : le défaut, et les exceptions."""
    default_access: str = ""      # vide = rôle global (pas de surcharge)
    overrides: list[ProjectAccessOverrideOut] = []
    group_overrides: list[ProjectGroupAccessOut] = []


class ProjectDefaultAccessIn(BaseModel):
    default_access: str = ""      # vide = rôle global ; sinon 'no_access' ou un des 4 rôles


class ProjectAccessOverrideIn(BaseModel):
    user_id: int
    role: str          # 'no_access' ou un des 4 rôles


class ProjectGroupAccessIn(BaseModel):
    group_id: int
    role: str          # '' = rôle global ; sinon no_access ou rôle V1


class ProjectMemberOut(BaseModel):
    user_id: int
    username: str
    email: str = ""
    role: str
    status: str
    created_at: str


class ProjectMemberCreateIn(BaseModel):
    user_id: int
    role: str


class ProjectMemberPatchIn(BaseModel):
    role: str | None = None
    status: str | None = None


class UserProjectAccessIn(BaseModel):
    project_id: int
    role: str


class UserProjectAccessOut(BaseModel):
    project_id: int
    project_name: str
    role: str
    has_access: bool


class UserProjectAccessListIn(BaseModel):
    projects: list[UserProjectAccessIn]


class UserCreateIn(BaseModel):
    username: str
    # Facultatif depuis l'audit 2026-09-09 : un Admin qui invente et transmet lui-même le mot de
    # passe d'un compte qu'il ne détient pas est la faille qu'on corrige — vide (ou omis) fait
    # générer un mot de passe temporaire côté serveur, envoyé par email si l'adresse est connue
    # (voir `routes/users.py::create_user`). Le champ reste accepté explicitement pour ne rien
    # retirer à un Admin qui préfère le communiquer lui-même (remise en main propre, etc.).
    password: str = ""
    role: str
    email: str = ""
    # None conserve le comportement historique (accès dérivé du rôle global). Une liste,
    # même vide, représente au contraire le choix explicite fait par l'Admin dans l'écran.
    projects: list[UserProjectAccessIn] | None = None


class UserCreateOut(UserOut):
    """Réponse de la création SEULEMENT — jamais celle de la liste/lecture d'un compte (`UserOut`
    ne porte jamais de mot de passe, même haché, et ça doit rester vrai partout ailleurs).

    `mot_de_passe_initial` n'est rempli QUE si aucun email n'a pu être envoyé — c'est alors le
    SEUL moyen dont dispose l'Admin de transmettre l'accès, affiché une fois, jamais reconsultable
    ensuite (le compte devra de toute façon en choisir un autre à la première connexion)."""
    email_envoye: bool = False
    mot_de_passe_initial: str | None = None


class UserPatchIn(BaseModel):
    """Les gestes d'un Admin sur un compte existant. `new_password` (2026-08-11) couvre le compte
    qui a oublié le sien, sans exiger l'ancien — le self-service par le titulaire lui-même (qui
    CONNAÎT encore son mot de passe et doit le prouver) vit séparément, en `PATCH /api/auth/password`
    (`routes/auth.py::changer_son_mot_de_passe`, 2026-09-03). `email` (2026-08-12) : nécessaire pour
    prévenir ce compte par email — voir `notification_service`."""
    role: str | None = None
    is_active: bool | None = None
    new_password: str | None = None
    email: str | None = None


class UserGroupIn(BaseModel):
    name: str
    # Comme l'API TestRail, la liste représente toujours l'ensemble complet des membres.
    user_ids: list[int] = []


class UserGroupMemberOut(BaseModel):
    id: int
    username: str
    email: str = ""
    role: str
    is_active: bool


class UserGroupOut(BaseModel):
    id: int
    name: str
    member_count: int = 0
    created_at: str
    members: list[UserGroupMemberOut] = []


# ── Mappers dict → DTO ─────────────────────────────────────────────────────────
def project_summary(row: dict) -> ProjectSummary:
    return ProjectSummary(
        id=row["id"], name=row["name"], description=row.get("description", ""),
        connector_type=row.get("connector_type", "odoo"),
        connector_version=row.get("connector_version", ""), base_url=row.get("base_url", ""),
        database=row.get("database", ""), username=row.get("username", ""),
        calibration_writes_enabled=bool(row.get("calibration_writes_enabled", 0)),
        module_count=row.get("module_count", 0), case_count=row.get("case_count", 0),
        effective_role=row.get("effective_role", ""))


def module_summary(row: dict) -> ModuleSummary:
    return ModuleSummary(id=row["id"], project_id=row["project_id"], name=row["name"],
                         description=row.get("description", ""), case_count=row.get("case_count", 0))


def case_summary(row: dict) -> CaseSummary:
    from testpilot.verdict.status import statut_de_test

    return CaseSummary(
        id=row["id"], title=row["title"],
        # Nom métier du module (repli sur le slug technique si le cas n'est pas encore rattaché).
        module=row.get("module_name") or row.get("feature_slug") or "—",
        module_id=row.get("module_id"), project_id=row.get("project_id"),
        group_id=row.get("group_id"), group_title=row.get("group_title"),
        refs=row.get("refs", "") or "", estimate=row.get("estimate", "") or "",
        type=row.get("type", "") or TYPE_DEFAUT, etat=row.get("etat", "") or ETAT_DEFAUT,
        priority=row.get("priority", "medium"),
        last_execution_status=row.get("last_execution_status"),
        last_functional_status=row.get("last_functional_status"),
        last_executed_at=row.get("last_executed_at"),
        last_verdict_version_id=row.get("last_verdict_version_id"),
        # Divergence seulement si les DEUX sont connues : un cas jamais exécuté, ou sans version
        # courante, ne « diverge » de rien — le dire serait une alerte inventée.
        verdict_from_other_version=bool(
            row.get("last_verdict_version_id")
            and row.get("current_version_id")
            and row["last_verdict_version_id"] != row["current_version_id"]),
        # Calculé ICI, une fois, pour tous les appelants : c'est ce qui garantit que l'étiquette
        # affichée et celle qui sert à filtrer sont la même.
        statut=statut_de_test(row.get("last_execution_status"),
                              row.get("last_functional_status")),
    )


def version_out(row: dict) -> VersionOut:
    return VersionOut(
        id=row["id"], version_number=row["version_number"],
        feature_content=row.get("feature_content", ""),
        steps_content=row.get("steps_content", ""),
        spec_hash=row.get("spec_hash", ""), created_at=row.get("created_at", ""),
        change_summary=row.get("change_summary", "") or "",
        created_by=row.get("created_by", "") or "",
        title=row.get("title", "") or "",
        preconditions=row.get("preconditions", "") or "",
        test_steps=row.get("test_steps", "") or "",
        expected_result=row.get("expected_result", "") or "",
    )


def review_out(row: dict) -> ReviewOut:
    return ReviewOut(
        id=row["id"], version_id=row["version_id"], decision=row["decision"],
        reviewer=row.get("reviewer", ""), comment=row.get("comment", ""),
        decided_at=row.get("decided_at", ""),
    )


def _field_fallbacks(raw) -> list[str]:
    """Décode la liste JSON des replis (0007 B+). Vide si absente ou illisible.

    Un contenu illisible ne doit jamais casser l'affichage d'une exécution : le repli est une
    information de confort, le verdict à deux axes reste la donnée souveraine.
    """
    if not raw:
        return []
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(item) for item in decoded] if isinstance(decoded, list) else []


def execution_summary(row: dict, *, running: bool = False) -> ExecutionSummary:
    from testpilot.verdict.status import a_confirmer, statut_de_test

    return ExecutionSummary(
        id=row["id"], test_case_id=row["test_case_id"], version_id=row["version_id"],
        execution_status=row["execution_status"], functional_status=row["functional_status"],
        scenarios_total=row.get("scenarios_total", 0),
        scenarios_passed=row.get("scenarios_passed", 0),
        scenarios_failed=row.get("scenarios_failed", 0),
        cost_usd=row.get("cost_usd", 0.0), iterations=row.get("iterations", 0),
        duration_seconds=row.get("duration_seconds", 0.0),
        started_at=row.get("started_at", ""), running=running,
        field_fallbacks=_field_fallbacks(row.get("field_fallbacks")),
        error_message=row.get("error_message", "") or "",
        case_title=row.get("case_title"), module_name=row.get("module_name"),
        suite_name=row.get("suite_name"),
        target_url=row.get("target_url", "") or "",
        target_database=row.get("target_database", "") or "",
        target_username=row.get("target_username", "") or "",
        statut=statut_de_test(row.get("execution_status"), row.get("functional_status")),
        confiance=row.get("confiance") or "nominale",
        a_confirmer=a_confirmer(statut_de_test(row.get("execution_status"), row.get("functional_status")),
                                row.get("confiance")),
    )


def scenario_result_out(row: dict) -> ScenarioResultOut:
    from testpilot.verdict.status import statut_de_test

    return ScenarioResultOut(
        scenario_name=row["scenario_name"], execution_status=row["execution_status"],
        functional_status=row["functional_status"],
        statut=statut_de_test(row["execution_status"], row["functional_status"]), cause_category=row.get("cause_category", ""),
        failure_type=row.get("failure_type", ""), error_summary=row.get("error_summary", ""),
        step_text=row.get("step_text", ""),
    )




# ── Actions en LOT (lot C, 2026-07-24) ────────────────────────────────────────
class LotCasIn(BaseModel):
    """Une action sur PLUSIEURS cas à la fois.

    ⚠️ **Pourquoi un endpoint plutôt que N appels depuis l'écran.** Composer une campagne de
    20 cas demandait 20 gestes ; le faire en 20 requêtes déplacerait le problème sans le
    résoudre — la moitié pourrait échouer et laisser le référentiel dans un état que personne
    n'a voulu. Une action, une requête, un compte rendu.
    """
    case_ids: list[int]


class LotPrioriteIn(LotCasIn):
    priority: str   # low | medium | high


class LotOut(BaseModel):
    """Compte rendu d'une action en lot.

    ⚠️ `traites` et `ignores` sont SÉPARÉS : demander 20 cas et en traiter 18 n'est pas un
    succès complet, et l'écran doit pouvoir le dire. Rendre un simple « OK » masquerait deux
    cas disparus entre l'affichage de la liste et le clic.
    """
    traites: int
    ignores: int = 0


class PageCas(BaseModel):
    """Une PAGE de cas — la réponse de `GET /api/cases`.

    ⚠️ `next_cursor` est **opaque** : le client le renvoie tel quel, sans jamais l'interpréter.
    S'il devenait un numéro de page, un client finirait par le fabriquer lui-même, et changer la
    façon de paginer casserait tout le monde.

    `total` est le nombre de cas correspondant au filtre — pas le nombre chargé. C'est ce qui
    permet d'écrire « 40 sur 2 000 » plutôt que de laisser croire que la liste est complète.
    """
    items: list[CaseSummary] = []
    next_cursor: str | None = None
    total: int = 0
