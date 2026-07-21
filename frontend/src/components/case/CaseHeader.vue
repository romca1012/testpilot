<script setup lang="ts">
// En-tête partagé d'un cas (Détails / Tests & Résultats / Défauts / Historique) — pastille ID,
// titre, fil d'Ariane spécification, actions. Boutons non couverts par ce lot → « à venir ».
import type { CaseSummary } from '../../lib/api'

defineProps<{ c: CaseSummary }>()
const emit = defineEmits<{ (e: 'back'): void; (e: 'edit'): void }>()
function soon(what: string) { window.alert(`${what} — à venir.`) }
</script>

<template>
  <div>
    <div class="flex items-center gap-3 flex-wrap">
      <span class="rounded-full bg-[hsl(262_52%_55%)] text-white text-sm font-semibold px-3 py-1 tabular-nums">C{{ c.id }}</span>
      <h1 class="text-2xl font-semibold tracking-tight truncate">{{ c.title }}</h1>
      <div class="flex items-center gap-1.5 ml-auto text-muted-foreground">
        <button class="hover:text-foreground p-1" title="Précédent" @click="soon('Cas précédent')"><svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <button class="hover:text-foreground p-1" title="Suivant" @click="soon('Cas suivant')"><svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg></button>
        <button class="hover:text-foreground p-1" title="Imprimer" @click="soon('Imprimer')"><svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2M6 14h12v8H6z"/></svg></button>
        <button class="rounded-md border border-border px-3 py-1.5 text-sm flex items-center gap-1.5 hover:border-primary/40 text-primary" @click="soon('Automatiser avec l\'IA')">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15l-1.9-4.1L5.5 9l4.6-1.4z"/></svg>Automatiser avec l'IA</button>
        <button class="rounded-md border border-border px-3 py-1.5 text-sm flex items-center gap-1.5 hover:border-primary/40 text-primary" @click="emit('edit')">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>Modifier</button>
      </div>
    </div>
    <button class="mt-1 text-primary/90 text-sm hover:underline" @click="emit('back')">{{ c.group_title || c.module }}</button>
  </div>
</template>
