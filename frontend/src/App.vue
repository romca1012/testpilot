<script setup lang="ts">
// SHELL UNIQUE : « Cas de test » (disposition TestRail). L'ancien AppShell est retiré (décision
// du porteur 2026-07-20) — sa nav « Gestion des cas / Exécution » est remplacée par la nav TestRail
// (Cas de test / Exécutions et résultats de test / …). La page projets (hors contexte projet) reste
// hors shell : on ne peut pas afficher une barre latérale de projet quand aucun n'est sélectionné.
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import CasesShell from './components/CasesShell.vue'

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
</script>

<template>
  <component :is="layout">
    <RouterView />
  </component>
</template>
