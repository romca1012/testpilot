// Client API — base configurable. En dev, Vite (:5173) appelle FastAPI (:8000) ; en prod, le
// front est servi par FastAPI (même origine → base relative).
const API_BASE = import.meta.env.DEV ? 'http://localhost:8000' : ''

// ⚠️ `credentials: 'include'` est INDISPENSABLE : le verrou d'instance (2026-07-24) tient dans un
// cookie de session, et en développement le front (:5173) et l'API (:8000) sont deux origines —
// sans ça, le cookie ne partirait pas et toute l'application semblerait déconnectée.
const CREDENTIALS: RequestCredentials = 'include'

// Prévenu quand le serveur répond 401 : l'écran de connexion doit revenir de lui-même quand une
// session expire, plutôt que de laisser une page échouer sans explication.
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: (() => void) | null) { onUnauthorized = fn }

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    credentials: CREDENTIALS,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    let code = ''
    try {
      const body = await resp.json()
      if (body?.detail) detail = body.detail
      // RFC 9457 (lot B) : `code` est le contrat stable. `detail` reste la phrase pour l'humain.
      if (body?.code) code = body.code
    } catch { /* réponse non-JSON */ }
    // La connexion elle-même peut répondre 401 (mot de passe faux) : c'est le formulaire qui le
    // dit, il ne faut pas le confondre avec une session expirée.
    if (resp.status === 401 && !path.startsWith('/api/auth/')) onUnauthorized?.()
    throw new ApiError(resp.status, detail, code)
  }
  return resp.status === 204 ? (undefined as T) : resp.json()
}

export class ApiError extends Error {
  /**
   * `code` — l'identifiant STABLE de la cause (RFC 9457, lot B du 2026-07-24).
   *
   * ⚠️ **C'est lui qu'on teste pour décider, jamais `message`.** Ce message est une phrase
   * française destinée à un humain : elle doit rester libre d'évoluer (corriger une tournure ne
   * doit casser aucun écran). Un écran qui branche sur le texte se casse à la première
   * reformulation, et personne ne le voit venir.
   *
   * Codes existants : `introuvable`, `nom_deja_pris`, `conteneur_non_vide`,
   * `connexion_incomplete`, `aucune_version`, `relecture_requise`, `specification_vide`,
   * `metier_incomplet`, `etat_incompatible`, `campagne_vide`, `campagne_en_cours`,
   * `campagne_archivee`, `exploration_en_cours`, `requete_invalide`, `non_gere`.
   */
  constructor(public status: number, message: string, public code: string = '') {
    super(message)
  }
}

export const api = {
  // ── Session (verrou d'instance, 2026-07-24) ──
  // `lock_enabled: false` = instance sans verrou : ne PAS afficher un formulaire rassurant qui
  // ne protège rien. Le `name` n'est pas une identité vérifiée, c'est une signature déclarée.
  getSession: () => request<Session>('/api/auth/session'),
  login: (password: string, name: string) =>
    request<Session>('/api/auth/login', { method: 'POST', body: JSON.stringify({ password, name }) }),
  logout: () => request<Session>('/api/auth/logout', { method: 'POST' }),

  // Projets / modules (hiérarchie §7)
  listProjects: () => request<ProjectSummary[]>('/api/projects'),
  createProject: (payload: ProjectInput) =>
    request<ProjectSummary>('/api/projects', { method: 'POST', body: JSON.stringify(payload) }),
  renameProject: (id: number | string, name: string, description = '') =>
    request<ProjectSummary>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify({ name, description }) }),
  // Édite un projet, CONNEXION comprise (décision 0005). ⚠️ N'envoyer que les champs modifiés :
  // côté serveur `null`/absent = « ne touche pas ». C'est vital pour `password`, que l'API ne
  // renvoie jamais — envoyer la chaîne vide d'un formulaire raffiché effacerait le secret.
  updateProject: (id: number | string, patch: Partial<ProjectInput>) =>
    request<ProjectSummary>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteProject: (id: number | string) =>
    request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
  // Exploration : cartographie l'application DU PROJET (crawl déterministe, aucun LLM).
  // Payée une fois par projet ; la génération lira ensuite cette mesure au lieu de deviner.
  // Santé technique de la génération dans le temps — dérivée des vraies exécutions, jamais
  // fabriquée. C'est le suivi de l'évolution de l'outil.
  getQuality: (projectId: number | string) =>
    request<Quality>(`/api/executions/quality/summary?project_id=${projectId}`),
  getExploration: (id: number | string) =>
    request<Exploration>(`/api/projects/${id}/exploration`),
  // ── Runs (campagnes) — décision 0022 n°8 ──
  createRun: (projectId: number | string, body: {
    name: string; description?: string; refs?: string
    selection_mode: 'all' | 'frozen'; case_ids?: number[]
  }) => request<RunSummary>(`/api/projects/${projectId}/runs`, {
    method: 'POST', body: JSON.stringify(body),
  }),
  listRuns: (projectId: number | string) =>
    request<RunSummary[]>(`/api/projects/${projectId}/runs`),
  getRun: (runId: number | string) => request<RunDetail>(`/api/runs/${runId}`),
  // Lance la campagne : ses cas sont exécutés EN SÉQUENCE en tâche de fond (0022 8.c.1 — créer
  // ne lance rien, lancer est un geste explicite).
  launchRun: (runId: number | string) =>
    request<RunSummary>(`/api/runs/${runId}/launch`, { method: 'POST' }),
  // Clôt (ou rouvre) une campagne : archivée = lecture seule. Réversible, rien n'est effacé.
  archiveRun: (runId: number | string, archived = true) =>
    request<RunSummary>(`/api/runs/${runId}/archive`, {
      method: 'POST', body: JSON.stringify({ archived }),
    }),
  startExploration: (id: number | string) =>
    request<Exploration>(`/api/projects/${id}/exploration`, { method: 'POST' }),
  listModules: (projectId: number | string) => request<ModuleSummary[]>(`/api/projects/${projectId}/modules`),
  // ⚠️ Manquait entièrement côté client : le backend savait créer un module, aucun écran ne le
  // demandait. Conséquence — un projet NEUF n'avait aucun module, donc la liste déroulante de
  // « Ajouter un cas de test » était vide et le formulaire restait sans effet, en silence.
  createModule: (projectId: number | string, name: string, description = '') =>
    request<ModuleSummary>(`/api/projects/${projectId}/modules`, {
      method: 'POST', body: JSON.stringify({ name, description }),
    }),
  renameModule: (moduleId: number | string, name: string) =>
    request<ModuleSummary>(`/api/modules/${moduleId}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  deleteModule: (moduleId: number | string) =>
    request<void>(`/api/modules/${moduleId}`, { method: 'DELETE' }),
  // « Ajouter un cas de test » = saisie MANUELLE (sans IA), à distinguer de addCase (l'IA).
  createManualCase: (moduleId: number | string, body: {
    title: string; preconditions?: string; test_steps: string[]; expected_result: string; angle?: string
  }) => request<CaseSummary>(`/api/modules/${moduleId}/cases/manual`, {
    method: 'POST', body: JSON.stringify(body),
  }),
  deleteCase: (caseId: number | string) =>
    request<void>(`/api/cases/${caseId}`, { method: 'DELETE' }),
  // ── Actions en LOT (lot C) : une action, une requête, un compte rendu ──
  // ⚠️ `traites` et `ignores` sont séparés : demander 20 cas et en traiter 18 n'est pas un
  // succès complet — l'écran doit pouvoir le dire plutôt que d'annoncer « fait ».
  prioriteEnLot: (case_ids: number[], priority: string) =>
    request<LotOut>('/api/cases/lot', { method: 'PATCH', body: JSON.stringify({ case_ids, priority }) }),
  supprimerEnLot: (case_ids: number[]) =>
    request<LotOut>('/api/cases/lot/suppression', { method: 'POST', body: JSON.stringify({ case_ids }) }),
  // Automatiser un cas MANUEL : générer son test technique depuis son métier. Tâche de fond,
  // suivie via getGenerationJob (même mécanique que la génération).
  automateCase: (caseId: number | string) =>
    request<GenerationJob>(`/api/cases/${caseId}/automate`, { method: 'POST' }),
  // Import d'un fichier de spec (.txt/.md/.docx) pour pré-remplir la génération. multipart —
  // pas de JSON, donc pas via `request()`.
  extractSpec: async (moduleId: number | string, file: File): Promise<{ text: string; filename: string }> => {
    const fd = new FormData()
    fd.append('file', file)
    // ⚠️ `API_BASE` et `credentials` comme partout : sans eux, cet appel visait le serveur Vite en
    // développement et partait sans cookie de session — l'import échouait là où tout le reste marche.
    const res = await fetch(`${API_BASE}/api/modules/${moduleId}/cases/extract`,
                            { method: 'POST', credentials: CREDENTIALS, body: fd })
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Import impossible.')
    return res.json()
  },
  // Spécifications (case_group) du projet — pour l'arbre latéral et les compteurs.
  listGroups: (projectId: number | string) => request<GroupSummary[]>(`/api/projects/${projectId}/groups`),
  // ── La SPÉCIFICATION : le document source, d'où naissent 1 à N cas (décision 0022) ──
  // ⚠️ Créer une spécification ne génère AUCUN cas et ne dépense RIEN : elle nomme un document.
  // C'est la génération qui le lira, après confirmation humaine des angles (§4bis du brief).
  listModuleGroups: (moduleId: number | string) =>
    request<GroupSummary[]>(`/api/modules/${moduleId}/groups`),
  createGroup: (moduleId: number | string, body: { title: string; description?: string; spec_content?: string }) =>
    request<GroupDetail>(`/api/modules/${moduleId}/groups`, { method: 'POST', body: JSON.stringify(body) }),
  getGroup: (groupId: number | string) => request<GroupDetail>(`/api/groups/${groupId}`),
  // Édition partielle : n'envoyer que ce qui change (`null`/absent = « ne touche pas »).
  updateGroup: (groupId: number | string, patch: { title?: string; description?: string; spec_content?: string }) =>
    request<GroupDetail>(`/api/groups/${groupId}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  // 409 tant que la spécification porte des cas — pas de cascade : un cas porte de l'historique.
  deleteGroup: (groupId: number | string) =>
    request<void>(`/api/groups/${groupId}`, { method: 'DELETE' }),
  getModule: (id: number | string) => request<ModuleDetail>(`/api/modules/${id}`),
  // Ajouter un cas = fournir une SPEC → analyse/génération/gate (jamais une coquille vide).
  addCase: (moduleId: number | string, spec_content: string, title = '') =>
    request<GenerationJob>(`/api/modules/${moduleId}/cases`, {
      method: 'POST', body: JSON.stringify({ spec_content, title }),
    }),
  getGenerationJob: (jobId: string) => request<GenerationJob>(`/api/modules/jobs/${jobId}`),
  // Passe 4b : le document validé (corrections comprises) FAIT FOI — c'est lui qui part à la
  // génération du Gherkin, pas la proposition initiale de l'IA.
  validateMetier: (jobId: string, metier: MetierDraft) =>
    request<GenerationJob>(`/api/modules/jobs/${jobId}/metier`, {
      method: 'POST', body: JSON.stringify(metier),
    }),
  setCasePriority: (id: number | string, priority: string) =>
    request<CaseSummary>(`/api/cases/${id}`, { method: 'PATCH', body: JSON.stringify({ priority }) }),
  getCaseScenarios: (id: number | string) => request<ScenarioResultOut[]>(`/api/cases/${id}/scenarios`),

  // Cas — toujours scopés par projet (jamais de mélange inter-projets)
  listCases: (projectId: number | string) => request<CaseSummary[]>(`/api/cases?project_id=${projectId}`),
  // Ordre d'AFFICHAGE des cas d'un module (décision 0009). En LOT : un glissement change N
  // positions. Le serveur recalcule les positions et renvoie la liste dans son ordre.
  reorderCases: (moduleId: number | string, caseIds: number[]) =>
    request<CaseSummary[]>(`/api/modules/${moduleId}/cases/order`, {
      method: 'PUT', body: JSON.stringify({ case_ids: caseIds }),
    }),
  getCase: (id: number | string) => request<CaseDetail>(`/api/cases/${id}`),
  // Édition du contenu MÉTIER — un champ versionné modifié crée une NOUVELLE version (0022 n°10),
  // et le gate rebloque l'exécution jusqu'à relecture. `refs`/`estimate` ne versionnent pas.
  updateCaseMetier: (id: number | string, body: CaseMetierIn) =>
    request<CaseMetierOut>(`/api/cases/${id}/metier`, { method: 'PATCH', body: JSON.stringify(body) }),
  runCase: (id: number | string) => request<RunResponse>(`/api/cases/${id}/runs`, { method: 'POST' }),
  // `repair_budget` : tentatives de réparation que cette approbation autorise (0014, option C).
  // undefined → le serveur applique son défaut.
  reviewCase: (id: number | string, approved: boolean, comment = '', repair_budget?: number) =>
    request<ReviewResponse>(`/api/cases/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ approved, comment, repair_budget }),
    }),

  // Exécutions — scopées par projet
  listExecutions: (projectId: number | string, limit = 50) =>
    request<ExecutionSummary[]>(`/api/executions?project_id=${projectId}&limit=${limit}`),
  getExecution: (id: number | string) => request<ExecutionDetail>(`/api/executions/${id}`),
  getReport: (id: number | string) => request<TestReport>(`/api/executions/${id}/report`),
  // ── La CORBEILLE (§7 : rien n'est détruit sans filet) ──
  // Supprimer MASQUE ; restaurer annule ; purger détruit, et n'est possible que sur ce qui est
  // déjà à la corbeille — sinon elle serait décorative.
  listerCorbeille: (projectId: number | string) =>
    request<ElementCorbeille[]>(`/api/projects/${projectId}/corbeille`),
  restaurer: (type: string, id: number) =>
    request<void>(`/api/corbeille/${type}/${id}/restaurer`, { method: 'POST' }),
  purger: (type: string, id: number) =>
    request<void>(`/api/corbeille/${type}/${id}`, { method: 'DELETE' }),

  // Trace BRUTE d'une exécution : ce que la machine a vu. C'est ce qui permet d'INSTRUIRE un
  // résultat non concluant au lieu de seulement le constater.
  listArtifacts: (id: number | string) => request<Artifacts>(`/api/executions/${id}/artifacts`),
  artifactUrl: (id: number | string, nom: string) =>
    `${API_BASE}/api/executions/${id}/artifacts/${encodeURIComponent(nom)}`,
}

// ── Types (miroir des DTO backend) ──────────────────────────────────────────
/** État du verrou d'instance. `lock_enabled=false` → aucun verrou configuré (poste isolé). */
export interface Session { lock_enabled: boolean; authenticated: boolean; name: string }

/** Trace brute d'une exécution. `available=false` porte TOUJOURS sa raison : « pas de fichier »
 *  et « aucune trace conservée » ne se disent pas pareil. */
/** Un élément à la corbeille. `deleted_by` est une signature déclarée, pas une identité
 *  vérifiée (lot 2) — l'écran doit le présenter comme telle. */
/** Compte rendu d'une action en lot. `ignores` = des cas ont disparu entre l'affichage et le
 *  clic (supprimés par quelqu'un d'autre) — à dire, jamais à taire. */
export interface LotOut { traites: number; ignores: number }
export interface ElementCorbeille {
  type: string; id: number; titre: string; deleted_at: string; deleted_by: string
}
export interface Artifact { name: string; size: number; label: string }
export interface Artifacts { available: boolean; reason: string; files: Artifact[] }

export interface ProjectSummary {
  id: number; name: string; description: string
  connector_type: string; base_url: string; database: string; username: string
  module_count: number; case_count: number
}
/** Santé technique de la génération (axe EXÉCUTION, premier jet). `ran_rate` = null quand aucune
 *  mesure : « rien mesuré » n'est pas « 0 % de réussite ». */
export interface QualityDay {
  jour: string; success: number; technical_error: number; not_executed: number
}
export interface Quality {
  total: number; ran: number; technical_error: number; not_executed: number
  ran_rate: number | null; by_day: QualityDay[]
}

/** Un run (campagne). `tested_count`/`case_count` → % de complétion. */
export interface RunSummary {
  id: number; project_id: number; name: string
  status: string            // draft | running | completed
  selection_mode: string; case_count: number; tested_count: number
  is_archived: boolean; created_at: string
}
/** Un cas DANS un run, avec son résultat (ou null = non testé). */
export interface RunCaseResult {
  id: number; title: string
  execution_status: string | null; functional_status: string | null; execution_id: number | null
}
export interface RunDetail {
  run: RunSummary; description: string; refs: string; cases: RunCaseResult[]
  /** Contre quoi la campagne a RÉELLEMENT tourné (lu sur ses exécutions). `target_mixed` = la
   *  connexion a changé en cours de campagne : ses résultats ne sont plus comparables. */
  target_url: string; target_database: string; target_mixed: boolean
}

/** État de la cartographie d'un projet. `mesure_le` est affiché systématiquement : c'est une
 *  PHOTO qui vieillit, et tout ce qui la consomme doit dire de quand elle date. */
export interface Exploration {
  explored: boolean; running: boolean; job_id: string; mesure_le: string
  pages: number; transitions: number; champs: number; resume: string; error: string
  // Règles de validation mesurées (motif, longueur, bornes) : le seul signe visible qu'une
  // cartographie est fraîche. Zéro règle sur un portail qui en a = mesure à refaire.
  contraintes: number
}
export interface ProjectInput {
  name: string; description?: string
  connector_type: string; base_url: string; database: string; username: string; password: string
}
export interface ModuleSummary {
  id: number; project_id: number; name: string; description: string; case_count: number
}
export interface Ref { id: number; name: string }

export interface GroupSummary {
  id: number; module_id: number; title: string; case_count: number
}
/** La Spécification AVEC son document. `spec_hash` est l'empreinte du document tel qu'il est —
 *  c'est elle qui dira un jour qu'un cas est né d'une version dépassée de sa spec (0022 n°6). */
export interface GroupDetail {
  id: number; module_id: number; title: string; description: string
  spec_content: string; spec_hash: string; case_count: number
  created_at: string; updated_at: string
}

export interface CaseMetierIn {
  title?: string; preconditions?: string; test_steps?: string
  expected_result?: string; angle?: string; refs?: string; estimate?: string; editor?: string
}
export interface CaseMetierOut {
  case: CaseSummary; version_id: number | null; version_created: boolean
}

export interface CaseSummary {
  id: number; title: string; module: string; module_id: number | null; project_id: number | null
  // Spécification propriétaire + angle testé (séparation 2026-07-19). `angle` = étiquette libre.
  group_id: number | null; group_title: string | null; angle: string
  // Métadonnées non versionnées (0022 n°3b) : elles ne changent pas ce que le test vérifie.
  refs: string; estimate: string
  validation_status: string
  priority: string   // étiquette de lecture (low|medium|high) — aucun ordre d'exécution
  last_execution_status: string | null; last_functional_status: string | null
  last_executed_at: string | null
  // Version qui a produit le dernier verdict (décision 0016, option (iii)). Une tentative de
  // réparation non adoptée écrit quand même les `last_*` : le verdict peut donc décrire une
  // version rembobinée. On l'affiche plutôt que de le corriger en silence.
  last_verdict_version_id: number | null
  verdict_from_other_version: boolean
}
export interface ModuleDetail { module: ModuleSummary; project: Ref }
/** Le document métier proposé par l'IA, à valider ou corriger (décision 0022 n°5, passe 4a). */
export interface MetierDraft {
  title: string; preconditions: string; steps: string[]
  expected_result: string; angle: string
}
export interface GenerationJob {
  // running | awaiting_metier | done | failed
  // ⚠️ `awaiting_metier` n'est PAS une attente technique : le job est ARRÊTÉ et n'ira nulle part
  // tant qu'un humain n'a pas validé le document métier. Traiter cet état comme « en cours »
  // ferait tourner le formulaire dans le vide indéfiniment.
  job_id: string; status: string; case_id: number | null; error: string
  metier?: MetierDraft | null
}
export interface VersionOut {
  id: number; version_number: number; feature_content: string; steps_content: string
  spec_hash: string; created_at: string
  // Contenu MÉTIER figé dans cette version (décision 0022 n°10). `test_steps` = liste JSON.
  title: string; preconditions: string; test_steps: string; expected_result: string; angle: string
  // Ce qui a changé et qui l'a fait — `created_by === 'repair-agent'` = version issue d'une
  // réparation automatique (0014), à ratifier.
  change_summary: string; created_by: string
}
export interface ReviewOut {
  id: number; version_id: number; decision: string; reviewer: string; comment: string; decided_at: string
}
export interface LintWarning { step: string; line: number; kind: string; message: string }
export interface GateOut {
  allowed: boolean; needs_review: boolean; reason: string
  // Réparations autorisées par la relecture en cours (0014) ; 0 = interdite ou non relue.
  repair_budget: number
  repair_budget_default: number
  lint_warnings?: LintWarning[]
}
export interface ExecutionSummary {
  id: number; test_case_id: number; version_id: number
  execution_status: string; functional_status: string
  scenarios_total: number; scenarios_passed: number; scenarios_failed: number
  cost_usd: number; iterations: number; duration_seconds: number; started_at: string; running: boolean
  // Replis « libellé → nom technique » tracés pendant le run (décision 0007 B+) — non-bloquant.
  field_fallbacks?: string[]
  case_title: string | null; module_name: string | null; suite_name: string | null
}
export interface CaseDetail {
  case: CaseSummary; project: Ref | null; module: Ref | null; current_version_id: number | null
  versions: VersionOut[]; reviews: ReviewOut[]; executions: ExecutionSummary[]; gate: GateOut | null
}
export interface ScenarioResultOut {
  scenario_name: string; execution_status: string; functional_status: string
  cause_category: string; failure_type: string; error_summary: string
}
export interface ExecutionDetail extends ExecutionSummary { scenarios: ScenarioResultOut[] }
export interface RunResponse { execution_id: number; status: string }
export interface ReviewResponse { decision: string; validation_status: string; gate: GateOut }
export interface TestReport {
  module_name: string; title: string; version_number: number
  execution_status: string; functional_status: string; execution_label: string; functional_label: string
  scenarios_total: number; scenarios_passed: number; scenarios_failed: number
  scenarios: Array<{ name: string; execution_status: string; functional_status: string; cause_label: string; error: string }>
  repairs: Array<{ cause_label: string; defect_origin: string; confirmation_status: string; requires_human_confirmation: boolean; what_was_tried: string }>
  cost_usd: number; cost_source: string; iterations: number; duration_seconds: number
  needs_human_confirmation: boolean
}
