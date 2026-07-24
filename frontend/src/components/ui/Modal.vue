<script setup lang="ts">
// Modale réutilisable (overlay + panneau centré), thème sombre. Extraite pour ne plus dupliquer
// le markup de superposition à chaque formulaire (création projet, édition, création module…).
// Ferme au clic sur le fond et à Échap. Rien n'est rendu quand `open` est faux — un consommateur
// peut donc en poser plusieurs sans que leurs champs cohabitent dans le DOM.
//
// ── PIÈGE DE FOCUS (lot D, 2026-07-24) ────────────────────────────────────────────────────────
// Sans lui, `Tab` sort de la modale et va parcourir la page qui est DERRIÈRE, masquée par le
// fond noir : l'utilisateur au clavier se retrouve à naviguer dans un écran qu'il ne voit plus,
// sans aucun moyen de comprendre où il est. C'est le défaut d'accessibilité le plus courant des
// fenêtres modales, et le plus désorientant.
//
// Trois gestes, indissociables : donner le focus à l'ouverture, l'enfermer tant que la modale
// vit, et le RENDRE à l'élément qui l'avait — sinon on ferme et le focus repart au début de la
// page, ce qui oblige à tout re-parcourir.
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  subtitle?: string
  maxWidth?: string   // classe Tailwind de largeur max (défaut : lg)
}>(), { title: '', subtitle: '', maxWidth: 'max-w-lg' })

const emit = defineEmits<{ (e: 'close'): void }>()

const panneau = ref<HTMLElement | null>(null)
let avant: HTMLElement | null = null

const FOCUSABLES = 'a[href], button:not([disabled]), input:not([disabled]), '
  + 'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function elementsFocusables(): HTMLElement[] {
  // ⚠️ Pas de filtre sur `offsetParent` : il vaut TOUJOURS null hors d'un vrai navigateur, et
  // le piège se retrouvait alors sans aucune cible — un filtre qui supprime tout ne protège
  // rien. On s'en tient aux critères portables et vérifiables.
  return Array.from(panneau.value?.querySelectorAll<HTMLElement>(FOCUSABLES) || [])
    .filter((el) => !el.hasAttribute('disabled') && el.getAttribute('aria-hidden') !== 'true')
}

function onKey(e: KeyboardEvent) {
  if (!props.open) return
  if (e.key === 'Escape') { emit('close'); return }
  if (e.key !== 'Tab') return

  const cibles = elementsFocusables()
  if (!cibles.length) return
  const premier = cibles[0]
  const dernier = cibles[cibles.length - 1]
  const actif = document.activeElement as HTMLElement | null

  // Le focus BOUCLE dans la modale : après le dernier élément on revient au premier, et
  // inversement avec Maj+Tab. C'est ce qui empêche d'en sortir sans le vouloir.
  if (!e.shiftKey && (actif === dernier || !panneau.value?.contains(actif))) {
    e.preventDefault()
    premier.focus()
  } else if (e.shiftKey && (actif === premier || !panneau.value?.contains(actif))) {
    e.preventDefault()
    dernier.focus()
  }
}

watch(() => props.open, async (ouvert) => {
  if (ouvert) {
    avant = document.activeElement as HTMLElement | null
    await nextTick()
    // ⚠️ Le premier CHAMP, pas le premier élément focusable : dans l'ordre du DOM, le bouton
    // « Fermer » de l'en-tête vient en premier. Ouvrir une modale de saisie avec le focus sur
    // sa croix de fermeture oblige à tabuler pour commencer à écrire — et suggère surtout qu'on
    // propose d'abord de renoncer. On ouvre une modale pour y saisir quelque chose.
    const cibles = elementsFocusables()
    const champ = cibles.find((el) => ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))
    ;(champ || cibles[0])?.focus()
  } else {
    avant?.focus()   // rendre le focus à celui qui a ouvert
    avant = null
  }
})

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-40 grid place-items-center bg-black/50 p-4"
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
