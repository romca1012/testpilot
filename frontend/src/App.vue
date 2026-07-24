<script setup lang="ts">
// SHELL UNIQUE : « Cas de test » (disposition TestRail). L'ancien AppShell est retiré (décision
// du porteur 2026-07-20) — sa nav « Gestion des cas / Exécution » est remplacée par la nav TestRail
// (Cas de test / Exécutions et résultats de test / …). La page projets (hors contexte projet) reste
// hors shell : on ne peut pas afficher une barre latérale de projet quand aucun n'est sélectionné.
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import CasesShell from './components/CasesShell.vue'
import LoginScreen from './pages/LoginScreen.vue'
import { api, setUnauthorizedHandler } from './lib/api'

const route = useRoute()
// Routes SANS contexte projet (accueil, liste des projets) : pas de shell projet.
const NO_SHELL = ['home', 'projects']
const useShell = computed(() => !NO_SHELL.includes(String(route.name)))

// ⚠️ UN SEUL <RouterView>, enveloppé conditionnellement — jamais deux en parallèle.
// Deux <RouterView> frères (un dans le shell, un hors) se disputaient la même vue pendant une
// transition shell↔hors-shell (ex. …/cases → /projects → …/cases via « Gérer les projets ») :
// le DOM de l'ancienne page restait empilé et CasesShell rendait des liens avec `pid` indéfini
// → « Missing required param "pid" » puis « emitsOptions null », qui corrompait l'interface.
// `<component :is>` déplace la MÊME vue entre le shell et un simple conteneur : plus de doublon.
const layout = computed(() => (useShell.value ? CasesShell : 'div'))

// ── Verrou d'instance (2026-07-24) ─────────────────────────────────────────────
// Trois états, et pas deux : tant que la session n'est pas connue, on n'affiche NI l'application
// NI l'écran de connexion. Afficher l'application « en attendant » la ferait clignoter puis
// disparaître ; afficher le formulaire ferait ressaisir un mot de passe à qui était déjà connecté.
const sessionConnue = ref(false)
const doitSeConnecter = ref(false)

async function verifierSession() {
  try {
    const s = await api.getSession()
    doitSeConnecter.value = s.lock_enabled && !s.authenticated
  } catch {
    // API injoignable : on laisse passer plutôt que de bloquer derrière un formulaire qui ne
    // servirait à rien — les écrans afficheront leur propre erreur de chargement, qui est le
    // diagnostic utile.
    doitSeConnecter.value = false
  } finally {
    sessionConnue.value = true
  }
}

onMounted(() => {
  setUnauthorizedHandler(() => { doitSeConnecter.value = true })
  verifierSession()
})
</script>

<template>
  <LoginScreen v-if="sessionConnue && doitSeConnecter" @connected="doitSeConnecter = false" />
  <component :is="layout" v-else-if="sessionConnue">
    <RouterView />
  </component>
</template>
