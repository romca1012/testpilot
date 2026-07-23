<script setup lang="ts">
// Modale réutilisable (overlay + panneau centré), thème sombre. Extraite pour ne plus dupliquer
// le markup de superposition à chaque formulaire (création projet, édition, création module…).
// Ferme au clic sur le fond et à Échap. Rien n'est rendu quand `open` est faux — un consommateur
// peut donc en poser plusieurs sans que leurs champs cohabitent dans le DOM.
import { onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  subtitle?: string
  maxWidth?: string   // classe Tailwind de largeur max (défaut : lg)
}>(), { title: '', subtitle: '', maxWidth: 'max-w-lg' })

const emit = defineEmits<{ (e: 'close'): void }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-40 grid place-items-center bg-black/50 p-4"
       @click.self="emit('close')">
    <div class="w-full rounded-xl border border-border bg-card shadow-2xl" :class="maxWidth" role="dialog" aria-modal="true">
      <header v-if="title || $slots.header" class="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div class="min-w-0">
          <slot name="header">
            <h2 class="text-lg font-semibold tracking-tight">{{ title }}</h2>
            <p v-if="subtitle" class="mt-1 text-xs text-muted-foreground">{{ subtitle }}</p>
          </slot>
        </div>
        <button class="shrink-0 rounded-md p-1 text-muted-foreground/60 transition-colors hover:bg-accent hover:text-foreground"
                aria-label="Fermer" @click="emit('close')">
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </header>

      <div class="px-5 py-4">
        <slot />
      </div>

      <footer v-if="$slots.footer" class="flex items-center justify-end gap-3 border-t border-border px-5 py-4">
        <slot name="footer" />
      </footer>
    </div>
  </div>
</template>
