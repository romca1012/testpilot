<script setup lang="ts">
import { computed } from 'vue'
import Chip from './ui/Chip.vue'
import { validationView, toneClasses } from '../lib/status'

const props = defineProps<{ status: string | null }>()
const view = computed(() => validationView(props.status))
</script>

<template>
  <Chip :icon="view.icon" :label="view.label" :cls="toneClasses(view.tone)" />
</template>
