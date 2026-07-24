<script setup lang="ts">
// Priorité de LECTURE d'un cas — éditable au clic. L'infobulle dit explicitement ce que
// cette étiquette n'est PAS : un ordre d'exécution (décision 0006).
import { computed, ref } from 'vue'
import Chip from './ui/Chip.vue'
import Hint from './ui/Hint.vue'
import { priorityView, toneClasses } from '../lib/status'
import { api } from '../lib/api'

const props = defineProps<{ caseId: number; priority: string; editable?: boolean }>()
const emit = defineEmits<{ (e: 'updated', priority: string): void }>()

const open = ref(false)
const busy = ref(false)
const view = computed(() => priorityView(props.priority))
const LEVELS = ['high', 'medium', 'low'] as const

async function choose(level: string) {
  open.value = false
  if (level === props.priority) return
  busy.value = true
  try {
    await api.setCasePriority(props.caseId, level)
    emit('updated', level)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <span class="relative inline-flex items-center gap-1">
    <button v-if="editable" :disabled="busy" class="disabled:opacity-50"
            :aria-label="`Changer la priorité (actuellement ${view.label})`"
            :aria-expanded="open" @click.stop="open = !open">
      <Chip :icon="view.icon" :label="view.label" :cls="toneClasses(view.tone)" />
    </button>
    <Chip v-else :icon="view.icon" :label="view.label" :cls="toneClasses(view.tone)" />
    <Hint :text="view.hint!" />

    <div v-if="open"
         class="absolute left-0 top-full z-40 mt-1 w-32 rounded-md border border-border bg-surface-overlay py-1 shadow-xl">
      <button v-for="lvl in LEVELS" :key="lvl"
              class="block w-full px-3 py-1.5 text-left text-xs hover:bg-accent/60"
              :class="lvl === priority ? 'text-primary' : 'text-foreground'"
              @click.stop="choose(lvl)">
        {{ priorityView(lvl).label }}
      </button>
    </div>
  </span>
</template>
