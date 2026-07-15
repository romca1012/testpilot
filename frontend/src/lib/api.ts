// Client API — base configurable, sans auth (usage interne). En dev, Vite (:5173) appelle
// FastAPI (:8000) ; en prod, le front est servi par FastAPI (même origine → base relative).
const API_BASE = import.meta.env.DEV ? 'http://localhost:8000' : ''

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const body = await resp.json()
      if (body?.detail) detail = body.detail
    } catch { /* réponse non-JSON */ }
    throw new ApiError(resp.status, detail)
  }
  return resp.status === 204 ? (undefined as T) : resp.json()
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

export const api = {
  // Projets / modules (hiérarchie §7)
  listProjects: () => request<ProjectSummary[]>('/api/projects'),
  createProject: (payload: ProjectInput) =>
    request<ProjectSummary>('/api/projects', { method: 'POST', body: JSON.stringify(payload) }),
  renameProject: (id: number | string, name: string, description = '') =>
    request<ProjectSummary>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify({ name, description }) }),
  deleteProject: (id: number | string) =>
    request<void>(`/api/projects/${id}`, { method: 'DELETE' }),
  listModules: (projectId: number | string) => request<ModuleSummary[]>(`/api/projects/${projectId}/modules`),
  getModule: (id: number | string) => request<ModuleDetail>(`/api/modules/${id}`),
  // Ajouter un cas = fournir une SPEC → analyse/génération/gate (jamais une coquille vide).
  addCase: (moduleId: number | string, spec_content: string, title = '') =>
    request<GenerationJob>(`/api/modules/${moduleId}/cases`, {
      method: 'POST', body: JSON.stringify({ spec_content, title }),
    }),
  getGenerationJob: (jobId: string) => request<GenerationJob>(`/api/modules/jobs/${jobId}`),
  setCasePriority: (id: number | string, priority: string) =>
    request<CaseSummary>(`/api/cases/${id}`, { method: 'PATCH', body: JSON.stringify({ priority }) }),
  getCaseScenarios: (id: number | string) => request<ScenarioResultOut[]>(`/api/cases/${id}/scenarios`),

  // Cas — toujours scopés par projet (jamais de mélange inter-projets)
  listCases: (projectId: number | string) => request<CaseSummary[]>(`/api/cases?project_id=${projectId}`),
  getCase: (id: number | string) => request<CaseDetail>(`/api/cases/${id}`),
  runCase: (id: number | string) => request<RunResponse>(`/api/cases/${id}/runs`, { method: 'POST' }),
  reviewCase: (id: number | string, approved: boolean, comment = '') =>
    request<ReviewResponse>(`/api/cases/${id}/review`, {
      method: 'POST',
      body: JSON.stringify({ approved, comment }),
    }),

  // Exécutions — scopées par projet
  listExecutions: (projectId: number | string, limit = 50) =>
    request<ExecutionSummary[]>(`/api/executions?project_id=${projectId}&limit=${limit}`),
  getExecution: (id: number | string) => request<ExecutionDetail>(`/api/executions/${id}`),
  getReport: (id: number | string) => request<TestReport>(`/api/executions/${id}/report`),
}

// ── Types (miroir des DTO backend) ──────────────────────────────────────────
export interface ProjectSummary {
  id: number; name: string; description: string
  connector_type: string; base_url: string; database: string; username: string
  module_count: number; case_count: number
}
export interface ProjectInput {
  name: string; description?: string
  connector_type: string; base_url: string; database: string; username: string; password: string
}
export interface ModuleSummary {
  id: number; project_id: number; name: string; description: string; case_count: number
}
export interface Ref { id: number; name: string }

export interface CaseSummary {
  id: number; title: string; module: string; module_id: number | null; project_id: number | null
  validation_status: string
  priority: string   // étiquette de lecture (low|medium|high) — aucun ordre d'exécution
  last_execution_status: string | null; last_functional_status: string | null
  last_executed_at: string | null
}
export interface ModuleDetail { module: ModuleSummary; project: Ref }
export interface GenerationJob {
  job_id: string; status: string; case_id: number | null; error: string
}
export interface VersionOut {
  id: number; version_number: number; feature_content: string; steps_content: string
  spec_hash: string; created_at: string
}
export interface ReviewOut {
  id: number; version_id: number; decision: string; reviewer: string; comment: string; decided_at: string
}
export interface GateOut { allowed: boolean; needs_review: boolean; reason: string }
export interface ExecutionSummary {
  id: number; test_case_id: number; version_id: number
  execution_status: string; functional_status: string
  scenarios_total: number; scenarios_passed: number; scenarios_failed: number
  cost_usd: number; iterations: number; duration_seconds: number; started_at: string; running: boolean
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
  repairs: Array<{ cause_label: string; defect_origin: string; confirmation_status: string; requires_human_confirmation: boolean }>
  cost_usd: number; cost_source: string; iterations: number; duration_seconds: number
  needs_human_confirmation: boolean
}
