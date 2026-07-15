<script setup lang="ts">
// Coque applicative — la séparation §8 est STRUCTURELLE : deux onglets de premier niveau,
// « Gestion des cas » et « Exécution ». Sidebar dense (md+), barre horizontale (mobile).
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const nav = [
  { to: '/cases', label: 'Gestion des cas', match: '/cases',
    icon: 'M4 6a2 2 0 012-2h12a2 2 0 012 2v2H4V6zM4 10h16v8a2 2 0 01-2 2H6a2 2 0 01-2-2v-8z' },
  { to: '/executions', label: 'Exécution', match: '/executions',
    icon: 'M14.752 11.168l-5.197-3.03A1 1 0 008 9.002v5.996a1 1 0 001.555.832l5.197-3.03a1 1 0 000-1.632z' },
]

function isActive(match: string) {
  return route.path === match || route.path.startsWith(match + '/')
}
const activeSection = computed(() => (isActive('/executions') ? 'Exécution' : 'Gestion des cas'))
</script>

<template>
  <div class="app-bg min-h-screen flex flex-col md:flex-row">
    <!-- Nav : sidebar sur md+, barre horizontale en mobile -->
    <aside class="shrink-0 md:w-60 border-b md:border-b-0 md:border-r border-border bg-surface/60 backdrop-blur-sm">
      <div class="h-14 flex items-center gap-2 px-4 border-b border-border">
        <div class="h-6 w-6 rounded-md bg-primary/15 grid place-items-center">
          <span class="h-2 w-2 rounded-full bg-primary" />
        </div>
        <span class="font-semibold tracking-tight">Test<span class="text-primary">Pilot</span></span>
      </div>
      <nav class="flex md:flex-col gap-1 p-3">
        <RouterLink
          v-for="item in nav" :key="item.to" :to="item.to"
          class="group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors"
          :class="isActive(item.match)
            ? 'bg-primary/15 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.3)]'
            : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'"
        >
          <svg class="w-4 h-4 shrink-0" :class="isActive(item.match) && 'text-primary'"
               fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="item.icon" />
          </svg>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <!-- Colonne principale -->
    <div class="flex-1 flex flex-col min-w-0">
      <header class="h-14 flex items-center px-5 border-b border-border bg-surface/40 backdrop-blur-sm">
        <span class="text-sm text-muted-foreground">{{ activeSection }}</span>
      </header>
      <main class="flex-1 overflow-y-auto">
        <div class="mx-auto max-w-5xl p-5 md:p-8 animate-fade-in">
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>
