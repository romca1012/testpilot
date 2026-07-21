<script setup lang="ts">
// « Exécutions et résultats de test » — Aperçu (disposition TestRail, palette sombre).
// OPTION 1 (porteur, 2026-07-20) : liste bâtie sur les VRAIES exécutions (ce sont des runs
// mono-cas). Les concepts absents du modèle — Plans de test, jalons, assignation, configurations
// — sont affichés « à venir », JAMAIS fabriqués (règle « affiché ≠ réel »).
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ExecutionSummary } from '../lib/api'
import { testStatusView } from '../lib/status'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)

const runs = ref<ExecutionSummary[]>([])
const loading = ref(true)
const error = ref('')
// Tri porté par l'URL, piloté depuis la SIDEBAR contextuelle du shell (état partagé).
const sortBy = computed(() => (route.query.sort as string) || 'date')

async function load() {
  loading.value = true; error.value = ''
  try {
    runs.value = await api.listExecutions(pid.value, 100)
  } catch {
    error.value = 'Impossible de charger les exécutions.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(pid, load)

function title(r: ExecutionSummary) { return r.case_title || `Exécution #${r.id}` }
function passPct(r: ExecutionSummary) {
  return r.scenarios_total ? Math.round((r.scenarios_passed / r.scenarios_total) * 100) : 0
}
function monthLabel(iso: string) {
  const s = new Date(iso).toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })
  return s.charAt(0).toUpperCase() + s.slice(1)
}

const sorted = computed(() => {
  const arr = [...runs.value]
  if (sortBy.value === 'name') arr.sort((a, b) => title(a).localeCompare(title(b)))
  else if (sortBy.value === 'pass') arr.sort((a, b) => passPct(b) - passPct(a))
  else arr.sort((a, b) => b.started_at.localeCompare(a.started_at))
  return arr
})
// Groupés par mois (comme TestRail groupe par date/statut).
const groups = computed(() => {
  const map = new Map<string, ExecutionSummary[]>()
  for (const r of sorted.value) {
    const k = monthLabel(r.started_at)
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(r)
  }
  return [...map.entries()].map(([month, rows]) => ({ month, rows }))
})

function openRun(id: number) {
  router.push({ name: 'run-detail', params: { pid: pid.value, id: String(id) } })
}
function comingSoon(w: string) { window.alert(`${w} — à venir.`) }
</script>

<template>
  <!-- Les actions (Ajouter run/plan) et les filtres (Grouper/Trier) vivent dans la SIDEBAR
       contextuelle du shell — ici, uniquement le titre et la liste. -->
  <div>
    <div class="flex-1 min-w-0">
      <div class="flex items-center justify-between">
        <h1 class="text-[26px] font-semibold tracking-tight">Exécutions et résultats de test</h1>
        <div class="flex items-center gap-3 text-muted-foreground">
          <button title="Afficher les données de test (à venir)" class="hover:text-foreground" @click="comingSoon('Afficher les données de test')">
            <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 118 0v4"/></svg>
          </button>
        </div>
      </div>

      <div v-if="loading" class="mt-6 space-y-2">
        <div v-for="i in 4" :key="i" class="h-12 rounded-md bg-secondary animate-pulse"></div>
      </div>
      <div v-else-if="error" class="mt-8 text-center">
        <p class="text-sm text-muted-foreground">{{ error }}</p>
        <button class="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:border-primary/40" @click="load">Réessayer</button>
      </div>
      <p v-else-if="!runs.length" class="mt-10 text-center text-sm text-muted-foreground">
        Aucune exécution pour ce projet. Créez-en une avec « Ajouter une exécution de test ».
      </p>

      <div v-for="g in groups" :key="g.month" class="mt-5">
        <div class="text-sm font-medium text-muted-foreground border-b border-border/60 pb-1">{{ g.month }}</div>
        <button v-for="r in g.rows" :key="r.id"
                class="w-full text-left flex items-center gap-4 py-3 border-b border-border/40 hover:bg-accent/30 rounded-md px-2 -mx-2"
                @click="openRun(r.id)">
          <span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold shrink-0" :class="testStatusView(r.execution_status, r.functional_status).badge">
            {{ testStatusView(r.execution_status, r.functional_status).label }}
          </span>
          <div class="min-w-0 flex-1">
            <div class="text-sm text-primary truncate">R{{ r.id }} — {{ title(r) }}</div>
            <div class="text-xs text-muted-foreground mt-0.5">
              {{ r.scenarios_passed }}/{{ r.scenarios_total }} scénarios Passed · Cas unique — aucun plan
            </div>
          </div>
          <div class="shrink-0 w-28 hidden sm:block">
            <div class="flex items-center gap-2">
              <div class="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
                <div class="h-full rounded-full bg-success" :style="{ width: passPct(r) + '%' }"></div>
              </div>
              <span class="text-xs tabular-nums text-muted-foreground">{{ passPct(r) }} %</span>
            </div>
          </div>
        </button>
      </div>

      <!-- Plans de test : concept non construit → « à venir », jamais fabriqué -->
      <div class="mt-8 rounded-lg border border-dashed border-border p-5">
        <div class="text-sm font-medium">Plans de test</div>
        <p class="mt-1 text-xs text-muted-foreground">
          Un plan regroupe plusieurs exécutions (une par configuration). Cette fonctionnalité
          arrivera avec l'Exécution nommée transverse — aucun plan n'existe encore.
        </p>
      </div>
    </div>
  </div>
</template>
