<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, type TestReport } from '../lib/api'
import { formatCost, formatDuration } from '../lib/format'
import Card from '../components/ui/Card.vue'
import Spinner from '../components/ui/Spinner.vue'
import Chip from '../components/ui/Chip.vue'
import Hint from '../components/ui/Hint.vue'
import Icon from '../components/ui/Icon.vue'
import StatTile from '../components/StatTile.vue'
import StatusPair from '../components/StatusPair.vue'
import {
  functionalView, executionView, toneClasses,
  defectOriginView, costSourceLabel,
} from '../lib/status'

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
</script>

<template>
  <div class="space-y-6">
    <RouterLink :to="`/projects/${route.params.pid}/executions`"
                class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <Icon name="chevron" class="h-3.5 w-3.5 rotate-180" /> Exécution
    </RouterLink>

    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground text-sm">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>

    <template v-else-if="report">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">{{ report.title }}</h1>
        <p class="mt-1 text-sm text-muted-foreground">Rapport d'exécution · v{{ report.version_number }}</p>
      </div>

      <!-- Verdict à deux axes, en tête -->
      <Card>
        <StatusPair :execution-status="report.execution_status" :functional-status="report.functional_status" layout="row" />
      </Card>

      <!-- Métriques (langage StatTile partagé) -->
      <section class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="Scénarios conformes" :value="`${report.scenarios_passed}/${report.scenarios_total}`" tone="success" icon="check" />
        <StatTile label="Échecs" :value="report.scenarios_failed" tone="destructive" icon="x" />
        <StatTile label="Durée" :value="formatDuration(report.duration_seconds)" tone="muted" icon="dot" />
        <StatTile :label="`Coût (${costSourceLabel(report.cost_source)})`" :value="formatCost(report.cost_usd)" tone="primary" icon="dot" />
      </section>

      <!-- Scénarios : deux axes par carte + cause racine -->
      <Card title="Scénarios">
        <ul class="space-y-2">
          <li v-for="(s, i) in report.scenarios" :key="i"
              class="rounded-lg border border-border bg-surface/40 p-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="font-medium text-sm">{{ s.name }}</div>
                <div v-if="s.error" class="mt-1 text-xs text-muted-foreground font-mono break-all">{{ s.error }}</div>
              </div>
              <div class="flex items-center gap-2 shrink-0">
                <Chip :icon="executionView(s.execution_status).icon" :label="executionView(s.execution_status).label"
                      :cls="toneClasses(executionView(s.execution_status).tone)" />
                <Chip :icon="functionalView(s.functional_status).icon" :label="functionalView(s.functional_status).label"
                      :cls="toneClasses(functionalView(s.functional_status).tone)" />
              </div>
            </div>
            <div v-if="s.cause_label" class="mt-2 text-xs text-muted-foreground">
              Cause racine : {{ s.cause_label }}
            </div>
          </li>
          <li v-if="!report.scenarios.length" class="text-sm text-muted-foreground">Aucun scénario exécuté.</li>
        </ul>
      </Card>

      <!-- Origine des défauts (vocabulaire utilisateur — jamais de valeur d'enum brute) -->
      <Card v-if="report.repairs.length" title="Origine des défauts">
        <ul class="divide-y divide-border text-sm">
          <li v-for="(d, i) in report.repairs" :key="i" class="py-2.5">
            <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center gap-2">
              <span class="text-muted-foreground">{{ d.cause_label || 'Cause indéterminée' }}</span>
              <span class="text-muted-foreground/50">·</span>
              <Chip
                :icon="defectOriginView(d.defect_origin).icon"
                :label="defectOriginView(d.defect_origin).label"
                :cls="toneClasses(defectOriginView(d.defect_origin).tone)"
              />
              <Hint v-if="defectOriginView(d.defect_origin).hint" :text="defectOriginView(d.defect_origin).hint!" />
            </div>
            </div>
            <!-- Ce que l'agent DIT avoir changé (0014). Sans ça, la réparation serait une
                 boîte noire : « v2 » sans savoir ce qui a bougé. -->
            <p v-if="d.what_was_tried" class="mt-1.5 text-xs text-muted-foreground">
              <span class="text-foreground/70">Réparation tentée :</span> {{ d.what_was_tried }}
            </p>
          </li>
        </ul>
      </Card>
    </template>
  </div>
</template>
