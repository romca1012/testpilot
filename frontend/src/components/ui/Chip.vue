<script setup lang="ts">
// Pastille de statut : icône SVG + mot + couleur (jamais la couleur seule).
import Icon from './Icon.vue'
defineProps<{ icon: string; label: string; cls: string }>()
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap"
    :class="cls"
  >
    <Icon :name="icon" class="h-3.5 w-3.5" />
    <span>{{ label }}</span>
  </span>
</template>
