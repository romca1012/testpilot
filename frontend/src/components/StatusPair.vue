<script setup lang="ts">
// LES DEUX AXES DU §5, JAMAIS FUSIONNÉS — composant verdict « signature ».
// Étiquettes d'axe compréhensibles sans le brief (+ infobulle « i »). Chaque axe :
// micro-étiquette + pastille (icône SVG + mot + couleur). Séparateur = deux jugements.
import { computed } from 'vue'
import Chip from './ui/Chip.vue'
import Hint from './ui/Hint.vue'
import { AXIS, executionView, functionalView, toneClasses } from '../lib/status'

const props = withDefaults(defineProps<{
  executionStatus: string | null
  functionalStatus: string | null
  layout?: 'row' | 'stack'
}>(), { layout: 'row' })

const exec = computed(() => executionView(props.executionStatus))
const func = computed(() => functionalView(props.functionalStatus))
</script>

<template>
  <div
    class="inline-flex rounded-lg border border-border bg-surface/50"
    :class="layout === 'stack' ? 'flex-col divide-y divide-border' : 'items-stretch divide-x divide-border'"
  >
    <div class="flex flex-col items-start gap-1 px-3 py-2">
      <span class="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {{ AXIS.execution.label }}<Hint :text="AXIS.execution.hint" />
      </span>
      <span class="flex items-center gap-1">
        <Chip :icon="exec.icon" :label="exec.label" :cls="toneClasses(exec.tone)" />
        <Hint v-if="exec.hint" :text="exec.hint" />
      </span>
    </div>
    <div class="flex flex-col items-start gap-1 px-3 py-2">
      <span class="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        {{ AXIS.functional.label }}<Hint :text="AXIS.functional.hint" />
      </span>
      <span class="flex items-center gap-1">
        <Chip :icon="func.icon" :label="func.label" :cls="toneClasses(func.tone)" />
        <Hint v-if="func.hint" :text="func.hint" />
      </span>
    </div>
  </div>
</template>
