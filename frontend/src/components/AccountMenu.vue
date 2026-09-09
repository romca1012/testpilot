<script setup lang="ts">
import { ref } from 'vue'
import { api, LIBELLE_ROLE } from '../lib/api'
import { useSession } from '../lib/useSession'
import ChangePasswordModal from './ChangePasswordModal.vue'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const { session } = useSession()
const open = ref(false)
// Accessible à TOUT rôle connecté — voir ChangePasswordModal.vue et
// `access.py::_ECRITURES_TOUJOURS_AUTORISEES` : sécuriser son propre compte n'est jamais un geste
// à restreindre par rôle, même pour Lecture seule.
const showChangePassword = ref(false)

async function logout() {
  open.value = false
  try { await api.logout() } catch { /* une session déjà expirée aboutit au même résultat */ }
  window.location.reload()
}
</script>

<template>
  <div v-if="session?.authenticated" class="relative">
    <button type="button" class="flex min-h-11 items-center gap-2 rounded-md px-2 text-left hover:bg-accent"
            :aria-expanded="open" aria-haspopup="menu" @click="open = !open">
      <span class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-primary/15 text-sm font-semibold text-primary">{{ session.name.charAt(0).toUpperCase() }}</span>
      <span v-if="!compact" class="min-w-0"><span class="block max-w-40 truncate text-sm font-medium">{{ session.name }}</span><span class="block text-xs text-muted-foreground">{{ LIBELLE_ROLE[session.role] || session.role }}</span></span>
      <svg class="h-4 w-4 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
    </button>
    <!-- `max-h-[...] overflow-y-auto` (même garde que Modal.vue/PaletteCommandes.vue) : sans lui,
         un menu ouvert près du haut d'une fenêtre COURTE déborde de la zone visible sans aucun
         moyen de faire défiler pour voir la suite — « Se déconnecter » paraît tronqué alors que
         rien n'est cassé, juste inatteignable (constaté en pratique, audit 2026-09-09). -->
    <div v-if="open" role="menu" class="absolute right-0 z-40 mt-1 max-h-[calc(100dvh-5rem)] w-56 overflow-y-auto rounded-md border border-border bg-surface-overlay p-1 shadow-xl">
      <div class="border-b border-border px-3 py-2"><div class="truncate text-sm font-medium">{{ session.name }}</div><div class="text-xs text-muted-foreground">{{ LIBELLE_ROLE[session.role] || session.role }}</div></div>
      <RouterLink v-if="session.role === 'admin'" to="/admin/projects" role="menuitem" class="mt-1 block rounded px-3 py-2 text-sm hover:bg-accent" @click="open = false">Administration</RouterLink>
      <button role="menuitem" class="mt-1 block w-full rounded px-3 py-2 text-left text-sm hover:bg-accent" @click="open = false; showChangePassword = true">Changer mon mot de passe</button>
      <button role="menuitem" class="block w-full rounded px-3 py-2 text-left text-sm text-destructive hover:bg-destructive/10" @click="logout">Se déconnecter</button>
    </div>
  </div>
  <ChangePasswordModal :open="showChangePassword" @close="showChangePassword = false" />
</template>
