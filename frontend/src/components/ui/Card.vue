<script setup lang="ts">
// `dense` = variante compacte (audit DA 2026-08-12) : avant, les blocs denses (fiches, panneaux
// latéraux) recodaient leur propre carte avec un padding choisi au hasard (`p-3`, `p-4`…) plutôt
// que de réutiliser Card.vue, faute d'une variante plus resserrée que le `p-5` par défaut.
withDefaults(defineProps<{ title?: string; dense?: boolean }>(), { dense: false })
</script>

<template>
  <section class="rounded-xl border border-border bg-card">
    <header
      v-if="title || $slots.header"
      class="flex items-center justify-between border-b border-border"
      :class="dense ? 'px-4 py-2.5' : 'px-5 py-3'"
    >
      <h2 class="text-sm font-semibold">{{ title }}</h2>
      <slot name="header" />
    </header>
    <div :class="dense ? 'p-4' : 'p-5'">
      <slot />
    </div>
  </section>
</template>
