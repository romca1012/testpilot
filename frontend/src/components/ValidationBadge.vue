<script setup lang="ts">
import { computed } from 'vue'
import Chip from './ui/Chip.vue'
import Hint from './ui/Hint.vue'
import { validationView, toneClasses } from '../lib/status'

const props = defineProps<{ status: string | null }>()
const view = computed(() => validationView(props.status))
</script>

<template>
  <span class="inline-flex items-center gap-1">
    <Chip :icon="view.icon" :label="view.label" :cls="toneClasses(view.tone)" />
    <Hint v-if="view.hint" :text="view.hint" />
  </span>
</template>
