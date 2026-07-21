<script setup lang="ts">
// Détail d'un run — VRAIES données. Statuts « façon TestRail » DÉRIVÉS des deux axes réels
// (Passed/Failed/Retest/Blocked/Untested) — le détail 2 axes reste visible via le déroulement.
// Donut + complétion depuis les scénarios réels ; scénarios GROUPÉS par section. Barre d'outils
// tri/filtre/colonnes affichée mais « à venir » (cohérent avec Jalon/Assignation). OPTION 1.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ExecutionDetail, type ScenarioResultOut } from '../lib/api'
import { executionView, testStatusCode, testStatusMeta, TEST_STATUS_ORDER, type TestStatusCode } from '../lib/status'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const runId = computed(() => Number(route.params.id))
const tab = computed(() => (route.query.tab as string) || 'tests')

const run = ref<ExecutionDetail | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true; error.value = ''
  try { run.value = await api.getExecution(runId.value) }
  catch { error.value = 'Impossible de charger cette exécution.' }
  finally { loading.value = false }
}
onMounted(load)
watch(runId, load)

function statusOf(s: ScenarioResultOut): TestStatusCode {
  return testStatusCode(s.execution_status, s.functional_status)
}

// Répartition RÉELLE par statut TestRail dérivé.
const dist = computed<Record<TestStatusCode, number>>(() => {
  const d = { passed: 0, failed: 0, retest: 0, blocked: 0, untested: 0 }
  for (const s of run.value?.scenarios || []) d[statusOf(s)]++
  return d
})
const total = computed(() => Object.values(dist.value).reduce((a, b) => a + b, 0))
const passPct = computed(() => total.value ? Math.round((dist.value.passed / total.value) * 100) : 0)
function pct(k: TestStatusCode) { return total.value ? Math.round((dist.value[k] / total.value) * 100) : 0 }

// Donut : un segment par statut non nul, dans l'ordre canonique.
const R = 42, C = 2 * Math.PI * 42
const segments = computed(() => {
  let acc = 0
  return TEST_STATUS_ORDER.filter((k) => dist.value[k] > 0).map((k) => {
    const len = (dist.value[k] / total.value) * C
    const s = { key: k, dash: `${len} ${C - len}`, rot: (acc / total.value) * 360, color: testStatusMeta(k).color }
    acc += dist.value[k]
    return s
  })
})

// Scénarios GROUPÉS par section (le run est mono-cas → une section : son module/cas).
const sections = computed(() => {
  const name = run.value?.module_name || run.value?.case_title || 'Sans section'
  const rows = run.value?.scenarios || []
  const passed = rows.filter((s) => statusOf(s) === 'passed').length
  return rows.length ? [{ name, rows, passed, pct: Math.round((passed / rows.length) * 100) }] : []
})

const subtabs = [
  { key: 'tests', label: 'Tests & Résultats', ready: true },
  { key: 'activite', label: 'Activité', ready: false },
  { key: 'progression', label: 'Progression', ready: false },
  { key: 'defauts', label: 'Défauts', ready: false },
]
function back() { router.push({ name: 'executions', params: { pid: pid.value } }) }
function comingSoon(w: string) { window.alert(`${w} — à venir.`) }
</script>

<template>
  <div v-if="loading" class="space-y-3">
    <div class="h-8 w-64 rounded bg-secondary animate-pulse"></div>
    <div class="h-40 rounded bg-secondary animate-pulse"></div>
  </div>
  <div v-else-if="error" class="text-center py-10">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <button class="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:border-primary/40" @click="load">Réessayer</button>
  </div>

  <div v-else-if="run">
    <!-- La sous-nav (Tests & Résultats / Activité / …) vit dans la barre latérale du shell, sous
         « Exécutions et résultats de test » — ici on ne rend que le CONTENU de l'onglet actif. -->
    <div class="min-w-0">
      <!-- En-tête -->
      <div class="flex items-center gap-3 flex-wrap">
        <span class="rounded-full bg-[hsl(262_52%_55%)] text-white text-sm font-semibold px-3 py-1 tabular-nums">R{{ run.id }}</span>
        <h1 class="text-2xl font-semibold tracking-tight truncate">{{ run.case_title || `Exécution #${run.id}` }}</h1>
        <div class="ml-auto flex items-center gap-1.5 text-muted-foreground">
          <button class="hover:text-foreground p-1" title="Partager" @click="comingSoon('Partager')"><svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8M16 6l-4-4-4 4M12 2v14"/></svg></button>
          <button class="rounded-md border border-border px-3 py-1.5 text-sm flex items-center gap-1.5 hover:border-primary/40 text-primary" @click="comingSoon('Relancer')">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>Relancer</button>
        </div>
      </div>
      <button class="mt-1 text-primary/90 text-sm hover:underline" @click="back">Exécutions et résultats de test</button>

      <template v-if="tab === 'tests'">
        <!-- Stats : donut + complétion -->
        <div class="mt-5 grid md:grid-cols-2 gap-4">
          <div class="rounded-lg border border-border bg-surface-raised/40 p-4 flex items-center gap-5">
            <svg viewBox="0 0 100 100" class="w-28 h-28 shrink-0 -rotate-90">
              <circle cx="50" cy="50" :r="R" fill="none" stroke="hsl(var(--border))" stroke-width="12" />
              <circle v-for="s in segments" :key="s.key" cx="50" cy="50" :r="R" fill="none"
                      :stroke="`hsl(${s.color})`" stroke-width="12"
                      :stroke-dasharray="s.dash" :transform="`rotate(${s.rot} 50 50)`" />
            </svg>
            <ul class="space-y-1.5 text-sm">
              <li v-for="k in TEST_STATUS_ORDER" :key="k" class="flex items-center gap-2">
                <span class="h-2.5 w-2.5 rounded-full" :style="{ background: `hsl(${testStatusMeta(k).color})` }"></span>
                <span class="font-semibold tabular-nums">{{ dist[k] }} {{ testStatusMeta(k).label }}</span>
                <span class="text-xs text-muted-foreground">· {{ pct(k) }} %</span>
              </li>
            </ul>
          </div>
          <div class="rounded-lg border border-border bg-surface-raised/40 p-4 flex flex-col items-center justify-center">
            <div class="text-4xl font-bold tabular-nums">{{ passPct }} %</div>
            <div class="text-sm text-muted-foreground mt-1">Passed</div>
            <div class="text-xs text-muted-foreground mt-2">{{ total - dist.passed }} / {{ total }} non Passed</div>
          </div>
        </div>

        <!-- Barre d'outils (UI seule — « à venir », cohérent avec Jalon/Assignation) -->
        <div class="mt-6 flex items-center gap-4 text-xs text-muted-foreground border-b border-border pb-2">
          <span>Trier : <button class="text-foreground border-b border-dotted border-muted-foreground" @click="comingSoon('Tri')">Section</button></span>
          <span>Filtre : <button class="text-foreground border-b border-dotted border-muted-foreground" @click="comingSoon('Filtre')">Aucun</button> <span class="text-muted">(à venir)</span></span>
          <span class="flex-1"></span>
          <button class="flex items-center gap-1.5 hover:text-foreground" @click="comingSoon('Colonnes')">
            <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>Colonnes <span class="text-muted">(à venir)</span>
          </button>
        </div>

        <!-- Scénarios groupés par section -->
        <h2 class="mt-4 font-bold italic tracking-tight">Scénarios</h2>
        <div v-for="sec in sections" :key="sec.name" class="mt-3">
          <div class="flex items-center gap-2.5 py-1.5">
            <span class="font-semibold">{{ sec.name }}</span>
            <span class="rounded-full bg-primary/15 text-primary text-[11px] font-semibold px-2.5 py-0.5">{{ sec.rows.length }}</span>
            <div class="w-24 h-1.5 rounded-full bg-border overflow-hidden">
              <div class="h-full rounded-full bg-success" :style="{ width: sec.pct + '%' }"></div>
            </div>
            <span class="text-xs text-muted-foreground tabular-nums">{{ sec.pct }} %</span>
          </div>
          <div v-for="(s, i) in sec.rows" :key="i" class="flex items-start gap-4 py-3 border-b border-border/40">
            <span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold shrink-0" :class="testStatusMeta(statusOf(s)).badge">
              {{ testStatusMeta(statusOf(s)).label }}
            </span>
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium">{{ s.scenario_name }}</div>
              <div class="text-xs text-muted-foreground mt-0.5">Déroulement : {{ executionView(s.execution_status).label }}<span v-if="s.cause_category"> · {{ s.cause_category }}</span></div>
              <p v-if="s.error_summary" class="mt-1.5 text-xs text-muted-foreground bg-surface-raised/60 border border-border/60 rounded-md p-2 whitespace-pre-wrap break-words line-clamp-3">{{ s.error_summary }}</p>
            </div>
          </div>
        </div>
      </template>

      <div v-else class="mt-10 rounded-lg border border-dashed border-border p-12 text-center">
        <div class="text-lg font-medium">{{ subtabs.find((t) => t.key === tab)?.label }}</div>
        <p class="mt-2 text-sm text-muted-foreground">Cette section sera disponible prochainement.</p>
      </div>
    </div>
  </div>
</template>
