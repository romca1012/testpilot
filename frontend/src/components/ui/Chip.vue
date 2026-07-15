<script setup lang="ts">
// Pastille de statut générique : icône + mot + couleur (jamais la couleur seule).
defineProps<{ icon: string; label: string; cls: string }>()
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap"
    :class="cls"
  >
    <span aria-hidden="true">{{ icon }}</span>
    <span>{{ label }}</span>
  </span>
</template>
