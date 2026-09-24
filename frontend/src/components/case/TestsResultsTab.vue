<script setup lang="ts">
// Onglet « Tests & Résultats » — vraies données. Graphique dérivé + liste (Exécutions /
// Résultats & commentaires) groupée par mois. Deux axes du §5 sur chaque ligne.
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import type { ExecutionSummary, ScenarioResultOut } from '../../lib/api'
import { causeLabel, executionView, testStatusMeta } from '../../lib/status'
import TestActivityChart from './TestActivityChart.vue'

const props = defineProps<{
  pid: string
  executions: ExecutionSummary[]
  scenarios: ScenarioResultOut[]
}>()
const router = useRouter()
const mode = ref<'executions' | 'results'>('executions')

function monthKey(iso: string) {
  const d = new Date(iso)
  return d.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })
}
function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })
}
function cap(s: string) { return s.charAt(0).toUpperCase() + s.slice(1) }

// Exécutions groupées par mois (les plus récentes d'abord).
const execGroups = computed(() => {
  const map = new Map<string, ExecutionSummary[]>()
  for (const e of [...props.executions].sort((a, b) => b.started_at.localeCompare(a.started_at))) {
    const k = monthKey(e.started_at)
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(e)
  }
  return [...map.entries()].map(([month, rows]) => ({ month: cap(month), rows }))
})

function openExec(id: number) {
  router.push({ name: 'report', params: { pid: props.pid, id: String(id) } })
}
// Rapport du PLAN de test (Exécution nommée transverse, §7). Ce rapport dédié n'existe pas encore ;
// on ouvre le rapport de l'exécution — meilleur disponible — jusqu'à sa livraison.
function openPlan(e: ExecutionSummary) {
  router.push({ name: 'report', params: { pid: props.pid, id: String(e.id) } })
}
</script>

<template>
  <div class="space-y-8">
    <TestActivityChart :executions="executions" />

    <section>
      <div class="flex items-center justify-between border-b border-border pb-2">
        <h2 class="text-lg font-semibold">Tests et résultats</h2>
        <div class="flex items-center gap-3 text-xs font-semibold uppercase tracking-wider">
          <button :class="mode === 'executions' ? 'text-foreground border-b-2 border-primary pb-0.5' : 'text-muted-foreground hover:text-foreground'" @click="mode = 'executions'">Exécutions</button>
          <span class="text-border">|</span>
          <button :class="mode === 'results' ? 'text-foreground border-b-2 border-primary pb-0.5' : 'text-muted-foreground hover:text-foreground'" @click="mode = 'results'">Résultats et commentaires</button>
        </div>
      </div>

      <!-- EXÉCUTIONS -->
      <div v-if="mode === 'executions'">
        <p v-if="!executions.length" class="py-10 text-center text-sm text-muted-foreground">
          Aucune exécution pour ce cas de test.<br>
          <span class="text-xs text-muted">Les exécutions apparaissent après un lancement depuis l'onglet « Exécutions et résultats de test ».</span>
        </p>
        <div v-for="g in execGroups" :key="g.month" class="mt-5">
          <div class="text-sm font-medium text-muted-foreground border-b border-border/60 pb-1">{{ g.month }}</div>
          <button v-for="e in g.rows" :key="e.id"
                  class="w-full text-left flex items-center gap-4 py-3 border-b border-border/40 hover:bg-accent/30 transition-colors rounded-md px-2 -mx-2"
                  @click="openExec(e.id)">
            <span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold shrink-0" :class="testStatusMeta(e.statut).badge">
              {{ testStatusMeta(e.statut).label }}
            </span>
            <div class="min-w-0 flex-1">
              <div class="text-sm">
                <span class="text-muted-foreground tabular-nums">E{{ e.id }}</span>
                <span class="text-muted-foreground"> — </span>
                <span class="text-foreground/90">{{ e.case_title || `Exécution #${e.id}` }}</span>
              </div>
              <div class="text-xs text-muted-foreground mt-0.5">
                Déroulement : {{ executionView(e.execution_status).label }} · {{ e.scenarios_passed }}/{{ e.scenarios_total }} scénarios · {{ Math.round(e.duration_seconds) }} s
              </div>
              <!-- La cible du run : un verdict ne veut rien dire sans l'application qu'il a jugée. -->
              <div v-if="e.target_url" class="text-[11px] text-muted-foreground/70 mt-0.5 truncate">
                contre {{ e.target_url }}<template v-if="e.target_database"> · {{ e.target_database }}</template>
              </div>
            </div>
            <div class="text-right shrink-0 hidden sm:block">
              <!-- Plan de test = Exécution nommée transverse (§7). Le nom quand il existe, un lien
                   vers son rapport ; sinon « Cas unique » (l'exécution n'appartient à aucun plan). -->
              <button v-if="e.suite_name" class="text-xs text-primary hover:underline" @click.stop="openPlan(e)">
                Plan : {{ e.suite_name }}
              </button>
              <span v-else class="text-xs text-muted-foreground">Cas unique — aucun plan</span>
              <div class="text-xs text-muted-foreground mt-0.5">{{ fmtDate(e.started_at) }}</div>
            </div>
          </button>
        </div>
      </div>

      <!-- RÉSULTATS ET COMMENTAIRES (scénarios du dernier run) -->
      <div v-else>
        <p v-if="!scenarios.length" class="py-10 text-center text-sm text-muted-foreground">
          Aucun résultat détaillé pour ce cas de test.
        </p>
        <div v-for="(s, i) in scenarios" :key="i" class="flex items-start gap-4 py-3 border-b border-border/40">
          <span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-semibold shrink-0" :class="testStatusMeta(s.statut).badge">
            {{ testStatusMeta(s.statut).label }}
          </span>
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium">{{ s.scenario_name }}</div>
            <div class="text-xs text-muted-foreground mt-0.5">Déroulement : {{ executionView(s.execution_status).label }}<span v-if="s.cause_category"> · {{ causeLabel(s.cause_category) }}</span></div>
            <p v-if="s.error_summary" class="mt-1.5 text-xs text-muted-foreground bg-surface-raised/60 border border-border/60 rounded-md p-2 whitespace-pre-wrap break-words line-clamp-3">{{ s.error_summary }}</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
