<script setup lang="ts">
import Spinner from './Spinner.vue'

withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  loading?: boolean
}>(), { variant: 'secondary', size: 'md', disabled: false, loading: false })

const VARIANTS = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary/90 border-transparent',
  secondary: 'bg-surface-raised text-foreground hover:bg-accent border-border',
  ghost: 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-accent/50 border-transparent',
  danger: 'bg-transparent text-destructive hover:bg-destructive/10 border-destructive/40',
}

// Trois hauteurs pour toute l'appli (audit DA 2026-08-12) : avant, Button.vue n'avait qu'une
// seule taille, ce qui a poussé chaque écran à improviser son propre `px-4 py-2` pour un bouton
// « plus important » ou plus discret. `md` reste strictement inchangé (comportement historique).
const SIZES = {
  sm: 'h-8 px-2.5 text-xs',
  md: 'h-9 px-3 text-sm',
  lg: 'h-10 px-4 text-sm',
}
</script>

<template>
  <button
    :disabled="disabled || loading"
    class="inline-flex items-center justify-center gap-2 rounded-md border font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    :class="[VARIANTS[variant], SIZES[size]]"
  >
    <Spinner v-if="loading" class="h-4 w-4" />
    <slot />
  </button>
</template>
