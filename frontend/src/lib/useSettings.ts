// Réglages d'instance, PARTAGÉS (sans Pinia) — même patron que `useProjects.ts`. Un seul fetch
// pour toute l'app : sans lui, un `RefsList` sur chaque ligne d'une liste redemanderait
// `/api/settings` en boucle (2026-08-11, références cliquables).
import { ref } from 'vue'
import { api, type SettingOut } from './api'

const settings = ref<SettingOut[]>([])
const loaded = ref(false)
const loading = ref(false)

async function ensureLoaded(force = false) {
  if (loading.value) return
  if (loaded.value && !force) return
  loading.value = true
  try {
    settings.value = await api.listSettings()
    loaded.value = true
  } finally {
    loading.value = false
  }
}

function get(key: string): string {
  return settings.value.find((s) => s.key === key)?.value || ''
}

/** Lecture synchrone pour les utilitaires transverses (titre, formatage des dates). */
export function settingValue(key: string, fallback = ''): string {
  return get(key) || fallback
}

export function useSettings() {
  return { settings, loaded, loading, ensureLoaded, get }
}
