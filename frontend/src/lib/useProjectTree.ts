// État partagé de l'arbre Modules → Cas (sans Pinia), sur le patron de `useProjects`.
//
// L'arbre vit dans la barre latérale de l'application (sous les onglets), pas dans une seconde
// colonne : deux bandeaux de navigation côte à côte gaspillaient l'espace. C'est donc `AppShell`
// qui le rend — d'où cet état partagé plutôt qu'un état local de page.
//
// Aucun endpoint nouveau : `listModules` + `listCases` existaient déjà, le groupage est local.
import { ref } from 'vue'
import { api, type CaseSummary, type ModuleSummary } from './api'

const modules = ref<ModuleSummary[]>([])
const cases = ref<CaseSummary[]>([])
const loading = ref(false)
const error = ref('')
const expanded = ref<number[]>([])

let loadedPid: string | null = null

const storageKey = (pid: string) => `tp.tree.expanded.${pid}`

/** L'état de dépliage survit au rechargement : tout replier à chaque visite ferait perdre à
 *  l'arbre son rôle de repère dans un projet à beaucoup de modules. */
function loadExpanded(pid: string) {
  try {
    const raw = localStorage.getItem(storageKey(pid))
    expanded.value = raw ? JSON.parse(raw) : []
  } catch {
    expanded.value = []   // stockage illisible/indisponible : l'arbre marche quand même
  }
}

function saveExpanded(pid: string) {
  try {
    localStorage.setItem(storageKey(pid), JSON.stringify(expanded.value))
  } catch { /* jamais bloquer la navigation pour une préférence d'affichage */ }
}

/**
 * Charge modules + cas du projet.
 * `silent` : rafraîchissement de fond (navigation interne, cas ajouté) — sans lui, le squelette
 * remplacerait l'arbre à chaque clic, or l'arbre doit rester un repère stable.
 */
async function load(pid: string, { silent = false } = {}) {
  if (loadedPid !== pid) {
    loadExpanded(pid)
    loadedPid = pid
    silent = false
  }
  if (!silent) loading.value = true
  error.value = ''
  try {
    // Scopé projet des deux côtés — aucun mélange inter-projets (invariant 4.8).
    const [m, c] = await Promise.all([api.listModules(pid), api.listCases(pid)])
    modules.value = m
    cases.value = c
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
}

function toggle(pid: string, moduleId: number) {
  expanded.value = expanded.value.includes(moduleId)
    ? expanded.value.filter((id) => id !== moduleId)
    : [...expanded.value, moduleId]
  saveExpanded(pid)
}

function expandAll(pid: string) {
  expanded.value = modules.value.map((m) => m.id)
  saveExpanded(pid)
}

function collapseAll(pid: string) {
  expanded.value = []
  saveExpanded(pid)
}

/** Déplie le module d'un cas ouvert par lien direct : arriver sans voir où l'on se trouve dans
 *  l'arbre irait contre le repère qu'il est censé donner. */
function revealCase(pid: string, caseId: number) {
  const found = cases.value.find((c) => c.id === caseId)
  const moduleId = found?.module_id
  if (moduleId != null && !expanded.value.includes(moduleId)) {
    expanded.value = [...expanded.value, moduleId]
    saveExpanded(pid)
  }
}

function revealModule(pid: string, moduleId: number) {
  if (!expanded.value.includes(moduleId)) {
    expanded.value = [...expanded.value, moduleId]
    saveExpanded(pid)
  }
}

export function useProjectTree() {
  return { modules, cases, loading, error, expanded,
           load, toggle, expandAll, collapseAll, revealCase, revealModule }
}
