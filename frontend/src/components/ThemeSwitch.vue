<script setup lang="ts">
import { useTheme, type Theme } from '../lib/useTheme'

const { theme, appliquerTheme } = useTheme()
const OPTIONS: { value: Theme; label: string; path: string }[] = [
  { value: 'light', label: 'Clair', path: 'M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364-.707.707M6.343 17.657l-.707.707m12.728 0-.707-.707M6.343 6.343l-.707-.707M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z' },
  { value: 'dark', label: 'Sombre', path: 'M20.25 15.25A8.5 8.5 0 0 1 8.75 3.75a8.5 8.5 0 1 0 11.5 11.5Z' },
]
</script>

<template>
  <div class="inline-flex rounded-lg border border-border bg-surface-raised p-1 shadow-sm"
       role="group" aria-label="Thème de l’interface">
    <button v-for="option in OPTIONS" :key="option.value" type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors"
            :class="theme === option.value
              ? 'bg-surface-overlay text-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-accent/60 hover:text-foreground'"
            :aria-pressed="theme === option.value"
            :aria-label="`Utiliser le thème ${option.label.toLowerCase()}`"
            @click="appliquerTheme(option.value)">
      <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path :d="option.path" />
      </svg>
      <span class="hidden sm:inline">{{ option.label }}</span>
    </button>
  </div>
</template>
