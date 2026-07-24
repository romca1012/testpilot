<script setup lang="ts">
// En-tête partagé d'un cas (Détails / Tests & Résultats / Défauts / Historique) — pastille ID,
// titre, fil d'Ariane spécification, actions. Boutons non couverts par ce lot → « à venir ».
import type { CaseSummary } from '../../lib/api'

// `canAutomate` = cas MANUEL sans test technique → on propose de le générer. `automating` =
// génération en cours. Un cas déjà automatisé ne montre pas ce bouton (rien à générer).
// `prevId`/`nextId` = cas voisins dans le module (null = extrémité → bouton désactivé).
defineProps<{ c: CaseSummary; canAutomate?: boolean; automating?: boolean
  prevId?: number | null; nextId?: number | null }>()
const emit = defineEmits<{ (e: 'back'): void; (e: 'edit'): void; (e: 'delete'): void
  (e: 'automate'): void; (e: 'go', id: number): void }>()
</script>

<template>
  <div>
    <div class="flex items-center gap-3 flex-wrap">
      <span class="rounded-full bg-[hsl(262_52%_55%)] text-white text-sm font-semibold px-3 py-1 tabular-nums">C{{ c.id }}</span>
      <h1 class="text-2xl font-semibold tracking-tight truncate">{{ c.title }}</h1>
      <div class="flex items-center gap-1.5 ml-auto text-muted-foreground">
        <button class="hover:text-foreground p-1 disabled:opacity-30 disabled:cursor-not-allowed" title="Cas précédent" :disabled="!prevId" @click="prevId && emit('go', prevId)" aria-label="Cas précédent"><svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 6l-6 6 6 6"/></svg></button>
        <button class="hover:text-foreground p-1 disabled:opacity-30 disabled:cursor-not-allowed" title="Cas suivant" :disabled="!nextId" @click="nextId && emit('go', nextId)" aria-label="Cas suivant"><svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg></button>
        <button v-if="canAutomate" class="rounded-md border border-border px-3 py-1.5 text-sm flex items-center gap-1.5 hover:border-primary/40 text-primary disabled:opacity-60"
                :disabled="automating" title="Générer le test technique à partir du contenu métier saisi" @click="emit('automate')">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15l-1.9-4.1L5.5 9l4.6-1.4z"/></svg>
          {{ automating ? 'Génération…' : 'Automatiser avec l\'IA' }}</button>
        <button class="rounded-md border border-border px-3 py-1.5 text-sm flex items-center gap-1.5 hover:border-primary/40 text-primary" @click="emit('edit')">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>Modifier</button>
        <button class="rounded-md border border-border px-3 py-1.5 text-sm flex items-center gap-1.5 hover:border-destructive/40 hover:text-destructive text-muted-foreground" title="Supprimer ce cas" @click="emit('delete')">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 7h12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-7 0v11a2 2 0 002 2h4a2 2 0 002-2V7"/></svg>Supprimer</button>
      </div>
    </div>
    <button class="mt-1 text-primary/90 text-sm hover:underline" @click="emit('back')">{{ c.group_title || c.module }}</button>
  </div>
</template>
