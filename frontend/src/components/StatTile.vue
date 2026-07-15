<script setup lang="ts">
import Icon from './ui/Icon.vue'
import type { Tone } from '../lib/status'

withDefaults(defineProps<{ label: string; value: number | string; tone?: Tone; icon?: string }>(),
  { tone: 'muted', icon: 'dot' })

const ACCENT: Record<Tone, string> = {
  success: 'text-success',
  destructive: 'text-destructive',
  warning: 'text-warning',
  primary: 'text-primary',
  muted: 'text-muted-foreground',
}
</script>

<template>
  <div class="relative overflow-hidden rounded-xl border border-border bg-surface/60 p-4">
    <div class="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-border to-transparent" />
    <div class="flex items-center justify-between">
      <span class="text-xs text-muted-foreground">{{ label }}</span>
      <Icon :name="icon" class="h-3.5 w-3.5" :class="ACCENT[tone]" />
    </div>
    <div class="mt-2 text-2xl font-semibold tabular-nums tracking-tight">{{ value }}</div>
  </div>
</template>
