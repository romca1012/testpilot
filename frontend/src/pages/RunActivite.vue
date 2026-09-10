<script setup lang="ts">
// Sous-onglet ACTIVITÉ d'une campagne — le fil de ce qui s'est passé, jour par jour.
//
// ⚠️ **Ce que la vue « Tests & Résultats » ne dit pas.** Elle montre l'ÉTAT actuel : un statut par
// cas, le dernier. Elle ne dit ni quand les résultats sont tombés, ni qui les a posés, ni qu'un
// cas a été rejoué trois fois. Une recette se pilote pourtant sur ce rythme-là — « rien depuis
// jeudi » est une information que l'écran d'état est structurellement incapable de donner.
//
// Chaque ligne redit le MODE d'exécution : sur un fil chronologique plus encore qu'ailleurs, un
// « Passed » manuel et un « Passed » automatique ne racontent pas la même chose.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, type RunActivite } from '../lib/api'
import { libelleActeur, testStatusMeta } from '../lib/status'
import { cleJour, jourLong } from '../lib/format'
import CourbeResultats from '../components/CourbeResultats.vue'
import ResultMode from '../components/ResultMode.vue'
import Button from '../components/ui/Button.vue'

const route = useRoute()
const pid = computed(() => route.params.pid as string)
const runId = computed(() => Number(route.params.id))

const activite = ref<RunActivite | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true; error.value = ''
  try { activite.value = await api.getRunActivite(runId.value) }
  catch { error.value = 'Impossible de charger l\'activité de cette campagne.' }
  finally { loading.value = false }
}
load()
watch(runId, load)

const events = computed(() => activite.value?.events || [])

/** Groupé par JOUR, du plus récent au plus ancien — l'ordre dans lequel on cherche « et depuis
 *  hier ? ». Les événements arrivent déjà triés du serveur : on ne retrie pas ici. */
const parJour = computed(() => {
  const groupes = new Map<string, typeof events.value>()
  for (const e of events.value) {
    const cle = cleJour(e.created_at)
    if (!groupes.has(cle)) groupes.set(cle, [])
    groupes.get(cle)!.push(e)
  }
  return [...groupes.entries()].map(([cle, lignes]) => ({ cle, titre: jourLong(cle), lignes }))
})

function heure(iso: string): string { return (iso || '').slice(11, 16) }
</script>

<template>
  <div v-if="loading" class="space-y-3">
    <div class="h-8 w-64 rounded bg-secondary animate-pulse"></div>
    <div class="h-40 rounded bg-secondary animate-pulse"></div>
  </div>

  <div v-else-if="error" class="text-center py-10">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <Button variant="secondary" class="mt-3" @click="load">Réessayer</Button>
  </div>

  <div v-else-if="activite">
    <h1 class="text-2xl font-semibold tracking-tight truncate">Activité</h1>
    <RouterLink :to="{ name: 'run-detail', params: { pid, id: String(runId) } }"
                class="mt-1 inline-block text-primary text-sm hover:underline">{{ activite.run_name }}</RouterLink>

    <CourbeResultats class="mt-5" :events="events" :jours="14" />

    <h2 class="mt-8 font-semibold pb-2 border-b border-border">
      Historique <span class="text-muted-foreground font-normal">({{ events.length }})</span>
    </h2>
    <!-- ⚠️ « Aucun résultat » et non « rien à afficher » : une campagne sans activité est une
         campagne qu'on n'a pas encore jouée, pas un écran en panne. -->
    <p v-if="!events.length" class="mt-3 text-sm text-muted-foreground italic">
      Aucun résultat n'a encore été posé dans cette campagne.
    </p>

    <section v-for="jour in parJour" :key="jour.cle" class="mt-6">
      <h3 class="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{{ jour.titre }}</h3>
      <ul class="mt-2 divide-y divide-border/40 rounded-lg border border-border">
        <li v-for="(e, i) in jour.lignes" :key="i"
            class="flex flex-wrap items-center gap-3 px-3 py-2.5 text-sm">
          <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold shrink-0"
                :class="testStatusMeta(e.statut).badge">{{ testStatusMeta(e.statut).label }}</span>
          <!-- Le titre mène au TEST dans CETTE campagne (pas au cas du référentiel) : c'est de
               ce résultat-ci qu'on vient de lire la ligne. -->
          <RouterLink :to="{ name: 'run-test', params: { pid, id: String(runId), caseId: String(e.case_id) } }"
                      class="text-primary hover:underline truncate min-w-0">{{ e.case_title }}</RouterLink>
          <ResultMode :mode="e.mode" :created-by="e.created_by" :at="e.created_at" />
          <span class="ml-auto text-xs text-muted-foreground shrink-0">
            Testé par {{ libelleActeur(e.created_by) }} · {{ heure(e.created_at) }}
          </span>
        </li>
      </ul>
    </section>
  </div>
</template>
