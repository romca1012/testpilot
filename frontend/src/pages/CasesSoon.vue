<script setup lang="ts">
// Page « à venir » — pour les onglets de nav non couverts par ce lot (Aperçu, Tâche à faire,
// Jalons, Rapports). Volontairement minimal : un titre + une note, sous le shell TestRail.
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const LABELS: Record<string, string> = {
  apercu: 'Aperçu', todo: 'Tâche à faire', jalons: 'Jalons', rapports: 'Rapports',
}
const label = computed(() => LABELS[route.query.tab as string] || 'Section')
</script>

<template>
  <div>
    <h1 class="text-2xl font-semibold tracking-tight">{{ label }}</h1>
    <div class="mt-6 rounded-lg border border-dashed border-border p-12 text-center">
      <p class="text-sm text-muted-foreground">Cette section sera disponible prochainement.</p>
    </div>
  </div>
</template>
