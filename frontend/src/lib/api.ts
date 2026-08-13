// Client API — base configurable. En dev, Vite (:5173) appelle FastAPI (:8000) ; en prod, le
// front est servi par FastAPI (même origine → base relative).
// ⚠️ EXPORTÉE : un lien `<a href>` de téléchargement direct (pièce jointe) a besoin de la même
// base que `fetch` — la reconstruire à côté aurait fait deux vérités qui peuvent diverger.
// ⚠️ TEMPORAIRE : pointé sur :8010 tant que le port 8000 reste occupé par un processus fantôme
// (2026-08-10, voir la session — Windows ne le retrouve dans aucune table de process, mais le
// port répond encore). Remettre 'http://localhost:8000' une fois ce port libéré (redémarrage du
// poste probablement nécessaire).
export const API_BASE = import.meta.env.DEV ? 'http://localhost:8010' : ''

// ⚠️ `credentials: 'include'` est INDISPENSABLE : le verrou d'instance (2026-07-24) tient dans un
// cookie de session, et en développement le front (:5173) et l'API (:8000) sont deux origines —
// sans ça, le cookie ne partirait pas et toute l'application semblerait déconnectée.
const CREDENTIALS: RequestCredentials = 'include'

// Prévenu quand le serveur répond 401 : l'écran de connexion doit revenir de lui-même quand une
// session expire, plutôt que de laisser une page échouer sans explication.
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(fn: (() => void) | null) { onUnauthorized = fn }

// Extraction d'erreur PARTAGÉE entre `request()` (JSON) et `requestForm()` (multipart) : les deux
// parlent au même serveur RFC 9457, et dupliquer cette lecture aurait fait deux endroits où un
// oubli (ex. ne pas relire `code`) casse silencieusement l'un des deux chemins sans casser l'autre.
async function erreurDepuis(resp: Response, path: string): Promise<never> {
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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    credentials: CREDENTIALS,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!resp.ok) await erreurDepuis(resp, path)
  return resp.status === 204 ? (undefined as T) : resp.json()
}

// Upload `multipart/form-data` (pièce jointe, import de spec…) : PAS de `request()` ici, parce
// que `request()` pose TOUJOURS `Content-Type: application/json` — un en-tête incompatible avec
// un envoi de fichier, où c'est le NAVIGATEUR qui doit écrire `multipart/form-data; boundary=…`
// (une valeur qu'on ne peut pas reproduire à la main). Même logique d'erreur que `request()`
// (`erreurDepuis`), donc même contrat `ApiError.code` côté écran — seul le transport diffère.
async function requestForm<T>(path: string, body: FormData): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, { method: 'POST', credentials: CREDENTIALS, body })
  if (!resp.ok) await erreurDepuis(resp, path)
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
  // ── Session — comptes utilisateurs réels (2026-08-07) ──
  // `name`/`role` viennent d'un COMPTE vérifié (identifiant + mot de passe), plus d'un nom
  // librement déclaré comme avant le 2026-08-07.
  getSession: () => request<Session>('/api/auth/session'),
  login: (username: string, password: string) =>
    request<Session>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => request<Session>('/api/auth/logout', { method: 'POST' }),

  // ── Comptes — Admin seulement (le serveur le vérifie ; ces appels échoueraient en 403 sinon) ──
  listUsers: () => request<UserAccount[]>('/api/admin/users'),
  createUser: (payload: { username: string; password: string; role: string; email?: string }) =>
    request<UserAccount>('/api/admin/users', { method: 'POST', body: JSON.stringify(payload) }),
  patchUser: (id: number, patch: { role?: string; is_active?: boolean; new_password?: string; email?: string }) =>
    request<UserAccount>(`/api/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),

  // Projets / modules (hiérarchie §7)
  listProjects: () => request<ProjectSummary[]>('/api/projects'),
  createProject: (payload: ProjectInput) =>
    request<ProjectSummary>('/api/projects', { method: 'POST', body: JSON.stringify(payload) }),
  updateProject: (id: number | string, patch: Partial<ProjectInput>) =>
    request<ProjectSummary>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  deleteProject: (id: number | string) =>
    request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
  // ── Accès par projet — Admin seulement (migration 31, 2026-08-10) ──
  // Surcharge du rôle global : accès par défaut du projet (vide = rôle global) + exceptions
  // par compte. `no_access` rend le projet invisible/404 pour qui le porte.
  getProjectAccess: (id: number | string) =>
    request<ProjectAccess>(`/api/projects/${id}/access`),
  setProjectDefaultAccess: (id: number | string, default_access: string) =>
    request<ProjectAccess>(`/api/projects/${id}/access`,
      { method: 'PATCH', body: JSON.stringify({ default_access }) }),
  setProjectAccessOverride: (id: number | string, user_id: number, role: string) =>
    request<ProjectAccess>(`/api/projects/${id}/access/users`,
      { method: 'POST', body: JSON.stringify({ user_id, role }) }),
  removeProjectAccessOverride: (id: number | string, userId: number) =>
    request<ProjectAccess>(`/api/projects/${id}/access/users/${userId}`, { method: 'DELETE' }),
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
    // ⚠️ Le MODE D'EXÉCUTION se choisit ICI, à la création, et jamais résultat par résultat :
    // c'est lui qui décide si la campagne se LANCE ou se SAISIT.
    mode?: 'automatique' | 'manuelle'
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
  // ── Exécution MANUELLE d'un cas (2026-08-04), dans une campagne manuelle ──
  // Le flux de TestRail : une campagne, un cas, un statut, un commentaire. Le résultat sera
  // étiqueté « Manuelle » partout — c'est la condition à laquelle l'exécution manuelle
  // n'affaiblit pas la promesse du produit.
  listResults: (runId: number | string, caseId: number | string) =>
    request<ResultOut[]>(`/api/runs/${runId}/cases/${caseId}/results`),
  addResult: (runId: number | string, caseId: number | string, body: { statut: string; comment?: string }) =>
    request<ResultOut>(`/api/runs/${runId}/cases/${caseId}/results`, {
      method: 'POST', body: JSON.stringify(body),
    }),
  // ── Pièces jointes d'un résultat (2026-08-05) ── TOUJOURS après `addResult` : la preuve
  // visuelle d'un test manuel est optionnelle, jamais une condition pour enregistrer le résultat.
  // multipart — `files` répété une fois par fichier, exactement ce qu'attend
  // `files: list[UploadFile]` côté FastAPI.
  addAttachments: (resultId: number | string, files: File[]) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f))
    return requestForm<AttachmentOut[]>(`/api/results/${resultId}/attachments`, fd)
  },
  // ── UN CAS DANS UNE CAMPAGNE — l'objet « test » (2026-08-05) ──
  // Distinct de `getCase` (le cas du référentiel) et de `getExecution` (le rapport technique
  // d'UNE exécution) : ici on demande « où en est CE cas, dans CETTE campagne ».
  getTestDansRun: (runId: number | string, caseId: number | string) =>
    request<TestDansRun>(`/api/runs/${runId}/tests/${caseId}`),
  // Le fil chronologique d'une campagne. Les écrans Activité ET Progression le lisent : la
  // progression est l'activité comptée autrement, pas une seconde mesure.
  getRunActivite: (runId: number | string) =>
    request<RunActivite>(`/api/runs/${runId}/activite`),
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
    title: string; preconditions?: string; test_steps: string[]; expected_result: string
  }) => request<CaseSummary>(`/api/modules/${moduleId}/cases/manual`, {
    method: 'POST', body: JSON.stringify(body),
  }),
  deleteCase: (caseId: number | string) =>
    request<void>(`/api/cases/${caseId}`, { method: 'DELETE' }),
  // Déplacer/copier un cas entre Sections (migration 28, étape 2). Déplacer = même id, aucun
  // historique touché ; copier = un cas NEUF, sans le moindre résultat hérité (parité TestRail).
  deplacerCas: (caseId: number | string, groupId: number) =>
    request<{ id: number }>(`/api/cases/${caseId}/deplacer`, {
      method: 'POST', body: JSON.stringify({ group_id: groupId }),
    }),
  copierCas: (caseId: number | string, groupId: number) =>
    request<{ id: number }>(`/api/cases/${caseId}/copier`, {
      method: 'POST', body: JSON.stringify({ group_id: groupId }),
    }),
  // Glisser-déposer une Section (étape 2bis) — jamais de copie : dupliquer une Section
  // dupliquerait en cascade tous les cas qu'elle contient (voir `copierCas`, réservé aux cas).
  deplacerGroupe: (groupId: number, parentGroupId: number | null) =>
    request<{ parent_group_id: number | null }>(`/api/groups/${groupId}/deplacer`, {
      method: 'POST', body: JSON.stringify({ parent_group_id: parentGroupId }),
    }),
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
  // pas de JSON, donc via `requestForm()` (et non `request()`).
  extractSpec: (moduleId: number | string, file: File): Promise<{ text: string; filename: string }> => {
    const fd = new FormData()
    fd.append('file', file)
    return requestForm(`/api/modules/${moduleId}/cases/extract`, fd)
  },
  // Spécifications (case_group) du projet — pour l'arbre latéral et les compteurs.
  listGroups: (projectId: number | string) => request<GroupSummary[]>(`/api/projects/${projectId}/groups`),
  // ── La SPÉCIFICATION : le document source, d'où naissent 1 à N cas (décision 0022) ──
  // ⚠️ Créer une spécification ne génère AUCUN cas et ne dépense RIEN : elle nomme un document.
  // C'est la génération qui le lira, après confirmation humaine du périmètre (§4bis du brief).
  createGroup: (moduleId: number | string, body: { title: string; description?: string; spec_content?: string; parent_group_id?: number | null }) =>
    request<GroupDetail>(`/api/modules/${moduleId}/groups`, { method: 'POST', body: JSON.stringify(body) }),
  getGroup: (groupId: number | string) => request<GroupDetail>(`/api/groups/${groupId}`),
  // Édition partielle : n'envoyer que ce qui change (`null`/absent = « ne touche pas »).
  updateGroup: (groupId: number | string, patch: { title?: string; description?: string; spec_content?: string }) =>
    request<GroupDetail>(`/api/groups/${groupId}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  // 409 tant que la spécification porte des cas — pas de cascade : un cas porte de l'historique.
  deleteGroup: (groupId: number | string) =>
    request<void>(`/api/groups/${groupId}`, { method: 'DELETE' }),
  // `group_id` (étape 3bis, 2026-08-07) : la Section choisie AVANT la génération, pour TOUS les
  // cas qui en sortiront — pas cas par cas.
  addCase: (moduleId: number | string, spec_content: string, title = '', group_id: number | null = null) =>
    request<GenerationJob>(`/api/modules/${moduleId}/cases`, {
      method: 'POST', body: JSON.stringify({ spec_content, title, group_id }),
    }),
  getGenerationJob: (jobId: string) => request<GenerationJob>(`/api/modules/jobs/${jobId}`),
  // Passe 4b : la liste PLATE des cas validés (corrections, suppressions — étape 3, 2026-08-07)
  // FAIT FOI — c'est elle qui part à la génération du Gherkin, pas la proposition initiale de
  // l'IA. Pas de Section ici (étape 3bis) : elle est déjà fixée depuis `addCase`.
  validateMetier: (jobId: string, cases: MetierDraft[]) =>
    request<GenerationJob>(`/api/modules/jobs/${jobId}/metier`, {
      method: 'POST', body: JSON.stringify({ cases }),
    }),
  // ── Réglages d'INSTANCE (2026-08-04) — ils ne dépendent d'aucun projet ──
  // ⚠️ La réponse porte `source` (db | env | default) : la base l'emporte sur la variable
  // d'environnement, et l'écran doit pouvoir le DIRE plutôt que de laisser un exploitant
  // chercher pourquoi sa variable semble ignorée.
  listSettings: () => request<SettingOut[]>('/api/settings'),
  setSetting: (key: string, value: string) =>
    request<SettingOut>(`/api/settings/${key}`, { method: 'PATCH', body: JSON.stringify({ value }) }),
  testSmtp: (destinataire: string) =>
    request<{ succes: boolean; erreur: string }>('/api/settings/smtp/test',
      { method: 'POST', body: JSON.stringify({ destinataire }) }),

  setCasePriority: (id: number | string, priority: string) =>
    request<CaseSummary>(`/api/cases/${id}`, { method: 'PATCH', body: JSON.stringify({ priority }) }),
  /** Métadonnées de lecture d'un cas : priorité, Type, État. On n'envoie QUE ce qui change —
   *  renvoyer les autres champs écraserait ce qu'un autre onglet vient d'y écrire. */
  setCaseMetadonnees: (id: number | string, champs: { priority?: string; type?: string; etat?: string }) =>
    request<CaseSummary>(`/api/cases/${id}`, { method: 'PATCH', body: JSON.stringify(champs) }),
  getCaseScenarios: (id: number | string) => request<ScenarioResultOut[]>(`/api/cases/${id}/scenarios`),

  // Cas — toujours scopés par projet (jamais de mélange inter-projets), et PAGINÉS.
  // ⚠️ La recherche (`q`) et le filtre (`statut`) partent au SERVEUR : appliqués côté navigateur,
  // ils ne porteraient que sur la page chargée, et chercher un cas absent de celle-ci répondrait
  // « aucun résultat ». Un filtre qui ment sur l'absence est pire que pas de filtre.
  listCases: (projectId: number | string, opts: {
    module_id?: number; group_id?: number; q?: string; statut?: string
    cursor?: string | null; limit?: number
  } = {}) => {
    const p = new URLSearchParams({ project_id: String(projectId) })
    if (opts.module_id != null) p.set('module_id', String(opts.module_id))
    if (opts.group_id != null) p.set('group_id', String(opts.group_id))
    if (opts.q) p.set('q', opts.q)
    if (opts.statut) p.set('statut', opts.statut)
    if (opts.cursor) p.set('cursor', opts.cursor)
    if (opts.limit) p.set('limit', String(opts.limit))
    return request<PageCas>(`/api/cases?${p.toString()}`)
  },
  // Ordre d'AFFICHAGE des cas d'un module (décision 0009). En LOT : un glissement change N
  // positions. Le serveur recalcule les positions et renvoie la liste dans son ordre.
  reorderCases: (moduleId: number | string, caseIds: number[]) =>
    request<CaseSummary[]>(`/api/modules/${moduleId}/cases/order`, {
      method: 'PUT', body: JSON.stringify({ case_ids: caseIds }),
    }),
  getCase: (id: number | string) => request<CaseDetail>(`/api/cases/${id}`),
  // Script COMPLET réellement exécuté (Phase 2) : `steps_content` propre au cas + le code des
  // steps partagés que son `.feature` référence — invisible autrement, la bibliothèque partagée
  // n'apparaît nulle part dans `steps_content`.
  getScriptEffectif: (caseId: number | string, versionId: number | string) =>
    request<ScriptEffectifOut>(`/api/cases/${caseId}/versions/${versionId}/script-effectif`),
  // Édition du contenu MÉTIER — un champ versionné modifié crée une NOUVELLE version (0022 n°10),
  // et le gate rebloque l'exécution jusqu'à relecture. `refs`/`estimate` ne versionnent pas.
  updateCaseMetier: (id: number | string, body: CaseMetierIn) =>
    request<CaseMetierOut>(`/api/cases/${id}/metier`, { method: 'PATCH', body: JSON.stringify(body) }),
  // Édition DIRECTE du script généré — réservée au rôle Dev (le serveur le vérifie, 403 sinon).
  // Jamais auto-approuvée : le gate rebloque l'exécution jusqu'à relecture.
  updateCaseScript: (id: number | string, feature_content: string, steps_content: string) =>
    request<CaseMetierOut>(`/api/cases/${id}/script`, {
      method: 'PATCH', body: JSON.stringify({ feature_content, steps_content }),
    }),
  reviewCase: (id: number | string, approved: boolean, comment = '', repair_budget?: number) =>
    request<ReviewResponse>(`/api/cases/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ approved, comment, repair_budget }),
    }),

  // Exécutions — scopées par projet
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
  // Rapport HTML autonome — imprimable et partageable hors de l'outil.
  rapportImprimable: (id: number | string) => `${API_BASE}/api/executions/${id}/report.html`,
  artifactUrl: (id: number | string, nom: string) =>
    `${API_BASE}/api/executions/${id}/artifacts/${encodeURIComponent(nom)}`,
}

// ── Types (miroir des DTO backend) ──────────────────────────────────────────
/** État du verrou d'instance. `lock_enabled=false` → aucun verrou configuré (poste isolé). */
export interface Session { lock_enabled: boolean; authenticated: boolean; name: string; role: string }

// Les 4 rôles, hiérarchie croissante — même ordre que `access.ROLES` côté serveur (la vérité
// reste toujours le serveur ; ceci ne sert qu'à ADAPTER l'affichage, jamais à décider un droit).
export const ROLES = ['lecture_seule', 'testeur', 'dev', 'admin'] as const
export type Role = typeof ROLES[number]
export function roleSuffisant(role: string, minimum: Role): boolean {
  return ROLES.indexOf(role as Role) >= ROLES.indexOf(minimum)
}
export const LIBELLE_ROLE: Record<string, string> = {
  lecture_seule: 'Lecture seule', testeur: 'Testeur', dev: 'Dev', admin: 'Admin',
}

export interface UserAccount {
  id: number; username: string; role: string; email: string; is_active: boolean; created_at: string
}

// Accès par projet (migration 31, 2026-08-10) — `no_access` volontairement HORS de `ROLES` :
// niveau()/role_suffisant() côté serveur le traitent déjà comme -1 sans y toucher.
export const ACCES_PROJET_REFUSE = 'no_access'
export const LIBELLE_ACCES: Record<string, string> = {
  '': 'Rôle global (par défaut)', ...LIBELLE_ROLE, [ACCES_PROJET_REFUSE]: 'Aucun accès',
}
export interface ProjectAccessOverride { user_id: number; username: string; role: string }
export interface ProjectAccess { default_access: string; overrides: ProjectAccessOverride[] }

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
  selection_mode: string
  /** Le MODE D'EXÉCUTION de la campagne : 'automatique' (la machine joue les cas) ou 'manuelle'
   *  (un humain les joue et saisit ce qu'il a constaté). Choisi à la CRÉATION — c'est lui qui
   *  décide des gestes offerts : une campagne automatique se lance, une manuelle se saisit. */
  mode: string
  case_count: number; tested_count: number
  /** Parmi les cas testés, ceux dont le DERNIER résultat a été joué à la main. Un « 100 % » ne
   *  doit jamais laisser croire que tout a été prouvé par la machine. */
  manuel_count: number
  is_archived: boolean; created_at: string
}
/** Un cas DANS un run, avec son résultat (ou null = non testé). */
export interface RunCaseResult {
  id: number; title: string
  // Les deux axes — ⚠️ VIDES sur un résultat MANUEL : personne n'a mesuré, on n'affiche rien.
  execution_status: string | null; functional_status: string | null; execution_id: number | null
  /** '' = aucun résultat | 'automatique' = une machine l'a produit | 'manuelle' = un humain a
   *  joué le test à la main. STOCKÉ avec le résultat, jamais déduit d'une exécution présente. */
  result_mode: string
  statut_manuel: string
  comment: string
  created_by: string
  result_at: string
  /** Statut de lecture calculé par le SERVEUR (un statut manuel court-circuite la dérivation). */
  statut: string
}
export interface RunDetail {
  run: RunSummary; description: string; refs: string; cases: RunCaseResult[]
  /** Contre quoi la campagne a RÉELLEMENT tourné (lu sur ses exécutions). `target_mixed` = la
   *  connexion a changé en cours de campagne : ses résultats ne sont plus comparables. */
  target_url: string; target_database: string; target_mixed: boolean
  /** ⚠️ Itérée telle quelle par l'écran de saisie — JAMAIS retapée ici. La liste vit en Python
   *  et dans un CHECK de la base ; une troisième copie en TypeScript divergerait un jour. */
  statuts_manuels: string[]
}

/** Un résultat de CE cas dans UNE campagne (la sienne ou une autre) — « où et quand », pas
 *  « pourquoi » : ni commentaire ni axes, l'écran qui les veut ouvre le test concerné. */
export interface ResultAilleurs {
  run_id: number; run_name: string; statut: string; mode: string
  created_by: string; created_at: string
}
/** **UN CAS DANS UNE CAMPAGNE** — le « test » de TestRail, distinct du cas du référentiel.
 *  Le statut, les résultats et les commentaires appartiennent à ce couple, pas au cas. */
export interface TestDansRun {
  run_id: number; run_name: string; run_archived: boolean; run_mode: string
  case_id: number; title: string
  type: string; etat: string; priority: string; estimate: string; refs: string
  statut: string
  results: ResultOut[]
  /** Voisins DANS LA CAMPAGNE — jamais dans le module : les flèches enchaînent une session de
   *  recette, elles ne parcourent pas le référentiel. */
  prev_case_id: number | null; next_case_id: number | null
  historique_du_cas: ResultAilleurs[]
}
/** Un résultat posé dans une campagne, vu depuis son fil d'activité. */
export interface ActiviteEvent {
  case_id: number; case_title: string; statut: string; mode: string
  created_by: string; created_at: string
}
export interface RunActivite {
  run_id: number; run_name: string; case_count: number; events: ActiviteEvent[]
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
  // `null` = Section de premier niveau ; sinon l'id de la Section qui porte cette Sous-section
  // (migration 28) — c'est ce qui permet à l'écran de reconstruire l'arbre.
  parent_group_id?: number | null
}
/** La Spécification AVEC son document. `spec_hash` est l'empreinte du document tel qu'il est —
 *  c'est elle qui dira un jour qu'un cas est né d'une version dépassée de sa spec (0022 n°6). */
export interface GroupDetail {
  id: number; module_id: number; title: string; description: string
  spec_content: string; spec_hash: string; case_count: number
  parent_group_id?: number | null
  created_at: string; updated_at: string
}

export interface CaseMetierIn {
  title?: string; preconditions?: string; test_steps?: string
  expected_result?: string; refs?: string; estimate?: string; editor?: string
}
export interface CaseMetierOut {
  case: CaseSummary; version_id: number | null; version_created: boolean
}

/** Une PAGE de cas. `next_cursor` est OPAQUE : on le renvoie tel quel, jamais on ne l'interprète.
 *  `total` est le nombre de cas correspondant au filtre — pas le nombre chargé : c'est lui qui
 *  permet d'écrire « 40 sur 2 000 » plutôt que de laisser croire la liste complète. */
export interface PageCas { items: CaseSummary[]; next_cursor: string | null; total: number }

export interface CaseSummary {
  id: number; title: string; module: string; module_id: number | null; project_id: number | null
  // Spécification propriétaire (séparation 2026-07-19). ⚠️ `angle` a été retiré : ce champ
  // n'existe pas dans TestRail, et `type` + le titre disent déjà ce qu'il prétendait dire.
  group_id: number | null; group_title: string | null
  // Métadonnées non versionnées (0022 n°3b) : elles ne changent pas ce que le test vérifie.
  refs: string; estimate: string
  // Type (ce que le cas vérifie) et État (où en est le document). Ils remplacent l'ancien
  // `validation_status`, qui était dérivé des exécutions et qu'aucun humain ne pouvait poser.
  type: string       // fonctionnel | non_fonctionnel
  etat: string       // new | design | ready | obsolete
  /** Statut de LECTURE calculé par le SERVEUR (2026-07-24) — plus jamais dérivé ici : la règle
   *  vivait en TypeScript, et filtrer côté serveur aurait exigé de la réécrire en SQL. */
  statut: string
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
/** Le document métier proposé par l'IA pour UN cas, à valider ou corriger (décision 0022 n°5).
 * Liste PLATE depuis l'étape 3 (2026-08-07) : `user_story` est un simple repère de LECTURE (la
 * story dont ce cas est issu, jamais une Section imposée). Pas de `group_id` par cas ici (étape
 * 3bis, 2026-08-07) : la Section est choisie UNE FOIS, avant même la génération
 * (`api.addCase`), pas cas par cas sur cet écran. */
export interface MetierDraft {
  title: string; preconditions: string; steps: string[]
  expected_result: string
  user_story?: string
}
export interface GenerationJob {
  // running | awaiting_metier | done | failed
  // ⚠️ `awaiting_metier` n'est PAS une attente technique : le job est ARRÊTÉ et n'ira nulle part
  // tant qu'un humain n'a pas validé l'ENSEMBLE des cas proposés. Traiter cet état comme
  // « en cours » ferait tourner le formulaire dans le vide indéfiniment.
  job_id: string; status: string; case_ids: number[]; error: string
  cases?: MetierDraft[] | null
}
export interface VersionOut {
  id: number; version_number: number; feature_content: string; steps_content: string
  spec_hash: string; created_at: string
  // Contenu MÉTIER figé dans cette version (décision 0022 n°10). `test_steps` = liste JSON.
  title: string; preconditions: string; test_steps: string; expected_result: string
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
  // Raison d'un plantage AVANT tout scénario (migration 11) — vide sur un run normal.
  error_message?: string
  // CONTRE QUOI ce test a tourné (migration 20) — vide sur les exécutions antérieures à elle.
  // Jamais le mot de passe.
  target_url?: string; target_database?: string; target_username?: string
  // Statut de LECTURE calculé par le serveur (passed/failed/retest/blocked/untested) — TOUJOURS
  // présent (défaut `"untested"` côté Pydantic), jamais absent de la réponse.
  statut: string
}
export interface CaseDetail {
  case: CaseSummary; project: Ref | null; module: Ref | null; current_version_id: number | null
  versions: VersionOut[]; reviews: ReviewOut[]; executions: ExecutionSummary[]; gate: GateOut | null
}
// Un step de la bibliothèque partagée référencé par le `.feature` d'une version (Phase 2, script
// consultable) — `code` est le décorateur + corps complet, relu depuis son fichier source.
export interface SharedStepOut {
  keyword: string; label: string; source: string; note: string; code: string
}
export interface ScriptEffectifOut {
  feature_content: string; steps_content: string
  shared_steps: SharedStepOut[]
  // `steps_content` + le code des steps partagés résolus, groupé par fichier d'origine.
  steps_effectif: string
}
export interface ScenarioResultOut {
  scenario_name: string; execution_status: string; functional_status: string
  cause_category: string; failure_type: string; error_summary: string
  // Statut de LECTURE calculé par le serveur — TOUJOURS présent (défaut `"untested"`).
  statut: string
  // Le step en échec — exposé pour rendre `cause_category` auditable (décision 0015).
  step_text?: string
}
export interface ExecutionDetail extends ExecutionSummary { scenarios: ScenarioResultOut[] }
export interface RunResponse { execution_id: number; status: string }
/** Une pièce jointe d'un résultat (2026-08-05) — la preuve visuelle qu'un test manuel a
 *  réellement été joué. `filename` est le nom d'ORIGINE (affichage seulement) : le nom sur
 *  disque est généré côté serveur et n'apparaît jamais ici. */
export interface AttachmentOut {
  id: number
  filename: string
  content_type: string
  size_bytes: number
}

/** Un résultat du registre. ⚠️ Les deux axes sont VIDES sur un résultat MANUEL : ils viennent
 *  de l'exécution, et un résultat manuel n'en a aucune. On n'invente rien pour remplir. */
export interface ResultOut {
  id: number
  mode: string                // manuelle | automatique
  statut: string              // étiquette de lecture, calculée par le serveur
  statut_manuel: string
  comment: string
  created_by: string
  created_at: string
  execution_id: number | null
  execution_status: string | null
  functional_status: string | null
  // VIDE par défaut : la grande majorité des résultats n'en portent aucune, et le serveur ne
  // fait pas payer une jointure supplémentaire pour un tableau vide.
  attachments: AttachmentOut[]
}
/** Un réglage d'instance, sa valeur EFFECTIVE et d'où elle vient. */
export interface SettingOut {
  key: string; value: string; source: string; description: string
  // Écriture réservée à l'Admin (2026-08-11) — la lecture reste ouverte à tous.
  admin_only: boolean
  // `value` est alors un masque fixe (ou vide) — jamais le vrai secret (2026-08-12).
  secret: boolean
}
export interface ReviewResponse { decision: string; gate: GateOut }
export interface TestReport {
  module_name: string; title: string; version_number: number
  execution_status: string; functional_status: string; execution_label: string; functional_label: string
  scenarios_total: number; scenarios_passed: number; scenarios_failed: number
  scenarios: Array<{ name: string; execution_status: string; functional_status: string; cause_label: string; error: string }>
  repairs: Array<{ cause_label: string; defect_origin: string; confirmation_status: string; requires_human_confirmation: boolean; what_was_tried: string }>
  cost_usd: number; cost_source: string; iterations: number; duration_seconds: number
  needs_human_confirmation: boolean
  // CONTRE QUOI ce verdict a été rendu (migration 20) — vide sur les exécutions antérieures à
  // elle : « on ne sait pas » est la vérité, jamais une cible reconstituée. Jamais le mot de passe.
  target_url?: string; target_database?: string; target_username?: string
}
