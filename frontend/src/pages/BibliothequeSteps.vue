<script setup lang="ts">
// Bibliothèque de steps partagés (2026-08-11) — jusqu'ici visible SEULEMENT du prompt système de
// l'agent de génération (`steps_library.as_prompt_section`) : aucun humain ne pouvait la
// consulter sans lire le code Python. Lecture pour tous les rôles — un catalogue technique de
// référence, rien de sensible ni de projet-spécifique (une seule bibliothèque pour l'instance).
import { computed, onMounted, ref } from 'vue'
import { api, type SharedStepOut } from '../lib/api'

const steps = ref<SharedStepOut[]>([])
const loading = ref(true)
const erreur = ref('')
const recherche = ref('')

const LIBELLE_MOT_CLE: Record<string, string> = {
  given: 'Soit', when: 'Quand', then: 'Alors', step: 'Soit / Quand / Alors',
}
const ORDRE_MOTS_CLES = ['given', 'when', 'then', 'step']

async function charger() {
  loading.value = true
  erreur.value = ''
  try {
    steps.value = await api.listSharedSteps()
  } catch (e: any) {
    erreur.value = e?.message || 'Impossible de charger la bibliothèque de steps.'
  } finally {
    loading.value = false
  }
}
onMounted(charger)

const filtres = computed(() => {
  const q = recherche.value.trim().toLowerCase()
  if (!q) return steps.value
  return steps.value.filter((s) =>
    s.label.toLowerCase().includes(q) || s.note.toLowerCase().includes(q)
    || s.source.toLowerCase().includes(q))
})

const groupes = computed(() => {
  const map = new Map<string, SharedStepOut[]>()
  for (const s of filtres.value) {
    if (!map.has(s.keyword)) map.set(s.keyword, [])
    map.get(s.keyword)!.push(s)
  }
  // Ordre Gherkin fixe (Soit → Quand → Alors), pas l'ordre d'arrivée du serveur.
  return ORDRE_MOTS_CLES
    .filter((k) => map.has(k))
    .map((k) => ({ keyword: k, libelle: LIBELLE_MOT_CLE[k] || k, steps: map.get(k)! }))
})
</script>

<template>
  <div class="mx-auto max-w-4xl p-6">
    <RouterLink to="/" class="text-sm text-primary hover:underline">← Retour</RouterLink>
    <h1 class="mt-3 text-xl font-semibold">Bibliothèque de steps partagés</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Ce que l'agent de génération réutilise au lieu de réinventer à chaque cas — jusqu'ici visible
      seulement dans son prompt. Un step listé ici, copié mot pour mot dans un <code>.feature</code>,
      est reconnu automatiquement par Behave.
    </p>

    <input v-model="recherche" type="search" placeholder="Rechercher un step, une note, un fichier…"
           class="mt-4 h-9 w-full max-w-md rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />

    <p v-if="erreur" class="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {{ erreur }}
    </p>
    <p v-if="loading" class="mt-6 text-sm text-muted-foreground">Chargement…</p>

    <template v-else>
      <p v-if="!filtres.length" class="mt-6 text-sm text-muted-foreground">
        {{ recherche ? 'Aucun step ne correspond à cette recherche.' : 'Bibliothèque vide.' }}
      </p>

      <section v-for="g in groupes" :key="g.keyword" class="mt-8">
        <h2 class="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          {{ g.libelle }} <span class="text-xs font-normal normal-case">({{ g.steps.length }})</span>
        </h2>
        <ul class="mt-2 divide-y divide-border/60 rounded-lg border border-border">
          <li v-for="s in g.steps" :key="g.keyword + '·' + s.label" class="p-3">
            <code class="block break-words font-mono text-sm text-foreground/90">{{ s.label }}</code>
            <p v-if="s.note" class="mt-1 text-xs text-muted-foreground">→ {{ s.note }}</p>
            <p class="mt-1 text-[11px] text-muted-foreground/60">{{ s.source }}</p>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
