<script setup lang="ts">
// SHELL UNIQUE : « Cas de test » (disposition TestRail). L'ancien AppShell est retiré (décision
// du porteur 2026-07-20) — sa nav « Gestion des cas / Exécution » est remplacée par la nav TestRail
// (Cas de test / Exécutions et résultats de test / …). La page projets (hors contexte projet) reste
// hors shell : on ne peut pas afficher une barre latérale de projet quand aucun n'est sélectionné.
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import CasesShell from './components/CasesShell.vue'
import LoginScreen from './pages/LoginScreen.vue'
import PaletteCommandes from './components/PaletteCommandes.vue'
import { setUnauthorizedHandler } from './lib/api'
import { ROUTES_SANS_SHELL } from './lib/shell'
import { useSession } from './lib/useSession'

const route = useRoute()
// Routes SANS contexte projet : pas de shell projet. La liste vit dans `lib/shell.ts`, où un
// test la compare aux routes déclarées — en oublier une rend la page entièrement blanche.
const NO_SHELL = ROUTES_SANS_SHELL
const useShell = computed(() => !NO_SHELL.includes(String(route.name)))

// ⚠️ UN SEUL <RouterView>, enveloppé conditionnellement — jamais deux en parallèle.
// Deux <RouterView> frères (un dans le shell, un hors) se disputaient la même vue pendant une
// transition shell↔hors-shell (ex. …/cases → /projects → …/cases via « Gérer les projets ») :
// le DOM de l'ancienne page restait empilé et CasesShell rendait des liens avec `pid` indéfini
// → « Missing required param "pid" » puis « emitsOptions null », qui corrompait l'interface.
// `<component :is>` déplace la MÊME vue entre le shell et un simple conteneur : plus de doublon.
const layout = computed(() => (useShell.value ? CasesShell : 'div'))

// ── Connexion obligatoire — comptes utilisateurs (2026-08-07) ─────────────────
// Trois états, et pas deux : tant que la session n'est pas connue, on n'affiche NI l'application
// NI l'écran de connexion. Afficher l'application « en attendant » la ferait clignoter puis
// disparaître ; afficher le formulaire ferait ressaisir un mot de passe à qui était déjà connecté.
const { session, charger: chargerSession } = useSession()
const sessionConnue = ref(false)
const doitSeConnecter = ref(false)

async function verifierSession() {
  await chargerSession()
  doitSeConnecter.value = !session.value?.authenticated
  sessionConnue.value = true
}

onMounted(() => {
  setUnauthorizedHandler(() => { doitSeConnecter.value = true })
  verifierSession()
})
</script>

<template>
  <LoginScreen v-if="sessionConnue && doitSeConnecter" @connected="doitSeConnecter = false" />
  <template v-else-if="sessionConnue">
    <component :is="layout">
      <RouterView />
    </component>
    <!-- Montée au niveau de l'application : la palette doit répondre à Ctrl+K depuis N'IMPORTE
         quel écran. La poser dans le shell la rendrait muette sur les pages hors shell. -->
    <PaletteCommandes />
  </template>
</template>
