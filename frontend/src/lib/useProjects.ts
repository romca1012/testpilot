// État partagé léger des projets (sans Pinia). Charge la liste une fois, expose le
// projet courant dérivé de l'URL (:pid). Sert au sélecteur de la sidebar.
import { ref } from 'vue'
import { api, type ProjectSummary } from './api'

const projects = ref<ProjectSummary[]>([])
const loaded = ref(false)
const loading = ref(false)

async function ensureLoaded(force = false) {
  if (loading.value) return
  if (loaded.value && !force) return
  loading.value = true
  try {
    projects.value = await api.listProjects()
    loaded.value = true
  } finally {
    loading.value = false
  }
}

function projectById(id: number | string | undefined) {
  const n = Number(id)
  return projects.value.find((p) => p.id === n)
}

export function useProjects() {
  return { projects, loaded, loading, ensureLoaded, projectById }
}
