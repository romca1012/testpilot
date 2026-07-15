<script setup lang="ts">
import Spinner from './Spinner.vue'

withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  disabled?: boolean
  loading?: boolean
}>(), { variant: 'secondary', disabled: false, loading: false })

const VARIANTS = {
  primary: 'bg-primary text-primary-foreground hover:bg-primary/90 border-transparent',
  secondary: 'bg-surface-raised text-foreground hover:bg-accent border-border',
  ghost: 'bg-transparent text-muted-foreground hover:text-foreground hover:bg-accent/50 border-transparent',
  danger: 'bg-transparent text-destructive hover:bg-destructive/10 border-destructive/40',
}
</script>

<template>
  <button
    :disabled="disabled || loading"
    class="inline-flex items-center justify-center gap-2 rounded-md border px-3 h-9 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    :class="VARIANTS[variant]"
  >
    <Spinner v-if="loading" class="h-4 w-4" />
    <slot />
  </button>
</template>
