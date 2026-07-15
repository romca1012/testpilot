<script setup lang="ts">
// Pastille d'UN axe (exécution OU fonctionnel) + infobulle de valeur si présente.
// Utilisé en colonnes de table (les étiquettes d'axe vivent dans les en-têtes).
import { computed } from 'vue'
import Chip from './ui/Chip.vue'
import Hint from './ui/Hint.vue'
import { executionView, functionalView, toneClasses } from '../lib/status'

const props = defineProps<{ kind: 'execution' | 'functional'; status: string | null }>()
const view = computed(() => (props.kind === 'execution' ? executionView : functionalView)(props.status))
</script>

<template>
  <span class="inline-flex items-center gap-1">
    <Chip :icon="view.icon" :label="view.label" :cls="toneClasses(view.tone)" />
    <Hint v-if="view.hint" :text="view.hint" />
  </span>
</template>
