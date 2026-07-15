<script setup lang="ts">
defineProps<{ title?: string }>()
</script>

<template>
  <section class="rounded-xl border border-border bg-card">
    <header v-if="title || $slots.header" class="flex items-center justify-between px-5 py-3 border-b border-border">
      <h2 class="text-sm font-semibold">{{ title }}</h2>
      <slot name="header" />
    </header>
    <div class="p-5">
      <slot />
    </div>
  </section>
</template>
