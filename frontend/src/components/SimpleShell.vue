<script setup lang="ts">
import ThemeSwitch from './ThemeSwitch.vue'
import AccountMenu from './AccountMenu.vue'
</script>

<template>
  <div class="min-h-screen">
    <!-- Une vraie ligne réservée au thème : aucun positionnement flottant ne peut recouvrir
         l'action principale des pages hors contexte projet. -->
    <header class="flex min-h-16 items-center justify-between gap-3 border-b border-border bg-surface/70 px-4 backdrop-blur-sm sm:px-6">
      <RouterLink to="/projects" class="font-semibold tracking-tight">TestPilot</RouterLink>
      <div class="flex items-center gap-3"><ThemeSwitch /><AccountMenu /></div>
    </header>
    <slot />
  </div>
</template>
