<script setup lang="ts">
// Détail d'un RUN (campagne, décision 0022 n°8) — ses cas et leur résultat DANS CE run.
//
// ⚠️ Ce que cette page montrait avant : une `execution` mono-cas et ses scénarios. Le modèle a
// changé — un run REGROUPE des cas. Le rapport détaillé d'un cas reste accessible en cliquant sa
// ligne (il pointe vers l'exécution qui l'a produit).
//
// Le statut d'un cas est DÉRIVÉ des deux axes réels (Passed/Failed/Retest/Blocked/Untested) :
// jamais un badge unique qui masque l'un des deux (§4.1). Un cas sans exécution dans ce run est
// « Untested » — on ne fabrique aucun résultat.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type RunDetail as RunDetailDto, type RunCaseResult } from '../lib/api'
import { testStatusCode, testStatusMeta, TEST_STATUS_ORDER, type TestStatusCode } from '../lib/status'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const runId = computed(() => Number(route.params.id))

const detail = ref<RunDetailDto | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true; error.value = ''
  try { detail.value = await api.getRun(runId.value) }
  catch { error.value = 'Impossible de charger cette exécution.' }
  finally { loading.value = false }
}
onMounted(load)
watch(runId, load)

function statusOf(c: RunCaseResult): TestStatusCode {
  return testStatusCode(c.execution_status, c.functional_status)
}

// Répartition RÉELLE des cas du run par statut dérivé.
const dist = computed<Record<TestStatusCode, number>>(() => {
  const d = { passed: 0, failed: 0, retest: 0, blocked: 0, untested: 0 }
  for (const c of detail.value?.cases || []) d[statusOf(c)]++
  return d
})
const total = computed(() => detail.value?.cases.length || 0)
const tested = computed(() => total.value - dist.value.untested)
const pct = computed(() => (total.value ? Math.round((tested.value / total.value) * 100) : 0))

const STATUS_RUN: Record<string, { label: string; cls: string }> = {
  draft: { label: 'Brouillon', cls: 'bg-secondary text-muted-foreground' },
  running: { label: 'En cours', cls: 'bg-warning/15 text-warning' },
  completed: { label: 'Terminé', cls: 'bg-success/15 text-success' },
}

// Cliquer un cas : vers son RAPPORT s'il a été exécuté ici, sinon vers le cas lui-même.
function openCase(c: RunCaseResult) {
  if (c.execution_id) {
    router.push({ name: 'report', params: { pid: pid.value, id: String(c.execution_id) } })
  } else {
    router.push({ name: 'case-detail', params: { pid: pid.value, id: String(c.id) } })
  }
}
function backToList() { router.push({ name: 'executions', params: { pid: pid.value } }) }
</script>

<template>
  <div v-if="loading" class="space-y-3">
    <div class="h-8 w-64 rounded bg-secondary animate-pulse"></div>
    <div class="h-32 rounded bg-secondary animate-pulse"></div>
  </div>

  <div v-else-if="error" class="text-center py-10">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <button class="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:border-primary/40" @click="load">Réessayer</button>
  </div>

  <div v-else-if="detail">
    <!-- En-tête -->
    <div class="flex items-center gap-3 flex-wrap">
      <span class="rounded-full bg-[hsl(262_52%_55%)] text-white text-sm font-semibold px-3 py-1 tabular-nums">R{{ detail.run.id }}</span>
      <h1 class="text-2xl font-semibold tracking-tight truncate">{{ detail.run.name }}</h1>
      <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold"
            :class="(STATUS_RUN[detail.run.status] || STATUS_RUN.draft).cls">
        {{ (STATUS_RUN[detail.run.status] || STATUS_RUN.draft).label }}
      </span>
    </div>
    <button class="mt-1 text-primary/90 text-sm hover:underline" @click="backToList">Exécutions et résultats de test</button>

    <p v-if="detail.description" class="mt-3 text-sm text-foreground/85 whitespace-pre-wrap">{{ detail.description }}</p>
    <p v-if="detail.refs" class="mt-1 text-xs text-muted-foreground">Références : {{ detail.refs }}</p>

    <!-- Avancement -->
    <div class="mt-6 flex flex-wrap items-center gap-6 rounded-lg border border-border bg-surface/60 p-4">
      <div>
        <div class="text-3xl font-semibold tabular-nums">{{ pct }} %</div>
        <div class="text-xs text-muted-foreground mt-0.5">{{ tested }} / {{ total }} cas testés</div>
      </div>
      <div class="flex-1 min-w-[200px]">
        <div class="h-2 rounded-full bg-border overflow-hidden flex">
          <div v-for="k in TEST_STATUS_ORDER" :key="k" class="h-full"
               :style="{ width: (total ? (dist[k] / total) * 100 : 0) + '%',
                         background: testStatusMeta(k).color }"></div>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          <span v-for="k in TEST_STATUS_ORDER" :key="k" class="flex items-center gap-1.5">
            <span class="h-2.5 w-2.5 rounded-sm" :style="{ background: testStatusMeta(k).color }"></span>
            {{ testStatusMeta(k).label }} : {{ dist[k] }}
          </span>
        </div>
      </div>
    </div>

    <!-- Les cas du run -->
    <h2 class="mt-8 font-semibold pb-2 border-b border-border">
      Cas de test <span class="text-muted-foreground font-normal">({{ total }})</span>
    </h2>
    <p v-if="!total" class="mt-3 text-sm text-muted-foreground">
      Cette exécution ne contient aucun cas.
    </p>
    <table v-else class="w-full border-collapse mt-1">
      <tbody>
        <tr v-for="c in detail.cases" :key="c.id"
            class="group border-b border-border/40 hover:bg-accent/30 cursor-pointer"
            @click="openCase(c)">
          <td class="py-3 pl-1 w-16 font-bold tabular-nums whitespace-nowrap text-muted-foreground">C{{ c.id }}</td>
          <td class="py-3 px-2.5 text-primary group-hover:underline leading-snug">{{ c.title }}</td>
          <td class="py-3 px-2.5 w-44 text-right">
            <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[12.5px] font-semibold"
                  :class="testStatusMeta(statusOf(c)).badge">
              {{ testStatusMeta(statusOf(c)).label }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-else class="text-sm text-muted-foreground">Exécution introuvable.</div>
</template>
