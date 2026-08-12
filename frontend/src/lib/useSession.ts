// Session courante, PARTAGÉE (sans Pinia) — même patron que `useSectionCreate.ts`. Un seul
// fetch pour toute l'app : `App.vue` (garde de connexion) et `CasesShell.vue` (rôle affiché,
// lien Admin) lisent le MÊME état, plutôt que d'interroger `/api/auth/session` chacun de son
// côté (2026-08-07, comptes utilisateurs).
import { ref } from 'vue'
import { api, type Session } from './api'

const session = ref<Session | null>(null)

export function useSession() {
  async function charger() {
    try {
      session.value = await api.getSession()
    } catch {
      session.value = null
    }
  }
  function oublier() {
    session.value = null
  }
  return { session, charger, oublier }
}
