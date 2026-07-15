<script setup lang="ts">
// LES DEUX AXES DU §5, JAMAIS FUSIONNÉS. Chaque axe a son étiquette explicite et sa
// propre pastille (icône + mot + couleur) — on ne produit jamais un unique badge « OK/KO ».
import { computed } from 'vue'
import Chip from './ui/Chip.vue'
import { executionView, functionalView, toneClasses } from '../lib/status'

const props = withDefaults(defineProps<{
  executionStatus: string | null
  functionalStatus: string | null
  layout?: 'row' | 'stack'
}>(), { layout: 'row' })

const exec = computed(() => executionView(props.executionStatus))
const func = computed(() => functionalView(props.functionalStatus))
</script>

<template>
  <div class="flex gap-4" :class="layout === 'stack' ? 'flex-col' : 'flex-wrap items-center'">
    <div class="flex items-center gap-2">
      <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Exécution</span>
      <Chip :icon="exec.icon" :label="exec.label" :cls="toneClasses(exec.tone)" />
    </div>
    <div class="flex items-center gap-2">
      <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Fonctionnel</span>
      <Chip :icon="func.icon" :label="func.label" :cls="toneClasses(func.tone)" />
    </div>
  </div>
</template>
