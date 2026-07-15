<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, type TestReport } from '../lib/api'
import { formatCost, formatDuration } from '../lib/format'
import Card from '../components/ui/Card.vue'
import Spinner from '../components/ui/Spinner.vue'
import StatusPair from '../components/StatusPair.vue'
import { functionalView, executionView, toneClasses } from '../lib/status'

const route = useRoute()
const report = ref<TestReport | null>(null)
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    report.value = await api.getReport(route.params.id as string)
  } catch (e: any) {
    error.value = e?.message || 'Rapport indisponible'
  } finally {
    loading.value = false
  }
})

function scenarioTone(exec: string, func: string) {
  // On montre les deux axes du scénario ; la teinte de ligne suit l'axe fonctionnel s'il tranche.
  return func === 'non_conforme' ? toneClasses('destructive')
    : exec === 'technical_error' ? toneClasses('warning')
    : func === 'conforme' ? toneClasses('success') : toneClasses('muted')
}
</script>

<template>
  <div class="space-y-6">
    <RouterLink to="/executions" class="text-xs text-muted-foreground hover:text-foreground">← Exécution</RouterLink>

    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground text-sm">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>

    <template v-else-if="report">
      <div>
        <h1 class="text-xl font-semibold">{{ report.title }}</h1>
        <p class="text-sm text-muted-foreground">Rapport d'exécution · v{{ report.version_number }}</p>
      </div>

      <div v-if="report.needs_human_confirmation"
           class="rounded-lg border-l-4 border-warning bg-warning/10 text-warning px-4 py-3 text-sm">
        ⚠ Confirmation humaine requise : au moins une origine de défaut attend une validation.
      </div>

      <!-- Les deux axes en tête -->
      <Card>
        <StatusPair :execution-status="report.execution_status" :functional-status="report.functional_status" layout="row" />
      </Card>

      <!-- Métriques -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div class="rounded-lg border border-border p-3">
          <div class="text-xs text-muted-foreground">Scénarios conformes</div>
          <div class="text-lg font-semibold">{{ report.scenarios_passed }}/{{ report.scenarios_total }}</div>
        </div>
        <div class="rounded-lg border border-border p-3">
          <div class="text-xs text-muted-foreground">Échecs</div>
          <div class="text-lg font-semibold">{{ report.scenarios_failed }}</div>
        </div>
        <div class="rounded-lg border border-border p-3">
          <div class="text-xs text-muted-foreground">Durée</div>
          <div class="text-lg font-semibold">{{ formatDuration(report.duration_seconds) }}</div>
        </div>
        <div class="rounded-lg border border-border p-3">
          <div class="text-xs text-muted-foreground">Coût ({{ report.cost_source }})</div>
          <div class="text-lg font-semibold">{{ formatCost(report.cost_usd) }}</div>
        </div>
      </div>

      <!-- Scénarios : deux axes par ligne + cause racine -->
      <Card title="Scénarios">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="text-[11px] uppercase tracking-wide text-muted-foreground">
              <tr>
                <th class="text-left font-medium px-3 py-2">Scénario</th>
                <th class="text-left font-medium px-3 py-2">Exécution</th>
                <th class="text-left font-medium px-3 py-2">Fonctionnel</th>
                <th class="text-left font-medium px-3 py-2">Cause racine</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(s, i) in report.scenarios" :key="i" class="border-t border-border align-top">
                <td class="px-3 py-2">
                  <div>{{ s.name }}</div>
                  <div v-if="s.error" class="text-xs text-muted-foreground font-mono mt-1">{{ s.error }}</div>
                </td>
                <td class="px-3 py-2">
                  <span class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs" :class="toneClasses(executionView(s.execution_status).tone)">
                    {{ executionView(s.execution_status).icon }} {{ executionView(s.execution_status).label }}
                  </span>
                </td>
                <td class="px-3 py-2">
                  <span class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs" :class="toneClasses(functionalView(s.functional_status).tone)">
                    {{ functionalView(s.functional_status).icon }} {{ functionalView(s.functional_status).label }}
                  </span>
                </td>
                <td class="px-3 py-2 text-muted-foreground">{{ s.cause_label || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      <!-- Origine des défauts -->
      <Card v-if="report.repairs.length" title="Origine des défauts">
        <ul class="divide-y divide-border text-sm">
          <li v-for="(d, i) in report.repairs" :key="i" class="flex flex-wrap items-center justify-between gap-2 py-2">
            <span>{{ d.cause_label || '—' }} · <span class="text-muted-foreground">{{ d.defect_origin }}</span></span>
            <span class="text-xs" :class="d.requires_human_confirmation ? 'text-warning' : 'text-muted-foreground'">
              {{ d.requires_human_confirmation ? 'confirmation humaine requise' : d.confirmation_status }}
            </span>
          </li>
        </ul>
      </Card>
    </template>
  </div>
</template>
