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
</script>

<template>
  <CasesShell v-if="useShell">
    <RouterView />
  </CasesShell>
  <RouterView v-else />
</template>
