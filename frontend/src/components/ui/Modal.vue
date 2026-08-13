<script setup lang="ts">
// Modale réutilisable (overlay + panneau centré), thème sombre. Extraite pour ne plus dupliquer
// le markup de superposition à chaque formulaire (création projet, édition, création module…).
// Ferme au clic sur le fond et à Échap. Rien n'est rendu quand `open` est faux — un consommateur
// peut donc en poser plusieurs sans que leurs champs cohabitent dans le DOM.
//
// Piège de focus et verrouillage du scroll : composables partagés (`lib/useFocusTrap`,
// `lib/scrollLock`) — ConfirmDialog.vue et PaletteCommandes.vue les réutilisent aussi, plutôt que
// chacune sa propre copie divergente (audit DA 2026-08-12 : 3 overlays, une seule vraiment
// complète).
import { toRef, watch } from 'vue'
import { useFocusTrap } from '../../lib/useFocusTrap'
import { verrouillerScroll, deverrouillerScroll } from '../../lib/scrollLock'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  subtitle?: string
  maxWidth?: string   // classe Tailwind de largeur max (défaut : lg)
}>(), { title: '', subtitle: '', maxWidth: 'max-w-lg' })

const emit = defineEmits<{ (e: 'close'): void }>()

const { panneau } = useFocusTrap(toRef(props, 'open'), () => emit('close'))

watch(toRef(props, 'open'), (v) => (v ? verrouillerScroll() : deverrouillerScroll()))
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-40 grid place-items-center bg-overlay/80 p-4"
       @click.self="emit('close')">
    <div ref="panneau" class="w-full rounded-xl border border-border bg-card shadow-2xl"
         :class="maxWidth" role="dialog" aria-modal="true"
         :aria-label="title || undefined">
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
