<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ExecutionSummary } from '../lib/api'
import { formatDate, formatDuration } from '../lib/format'
import StatusPair from '../components/StatusPair.vue'
import StatTile from '../components/StatTile.vue'
import Spinner from '../components/ui/Spinner.vue'
import Icon from '../components/ui/Icon.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const runs = ref<ExecutionSummary[]>([])
const loading = ref(true)
const error = ref('')

const stats = computed(() => ({
  total: runs.value.length,
  conformes: runs.value.filter((r) => r.functional_status === 'conforme').length,
  nonConformes: runs.value.filter((r) => r.functional_status === 'non_conforme').length,
  technical: runs.value.filter((r) => r.execution_status === 'technical_error').length,
}))

// Nom affiché : nom de la suite (Exécution nommée §7, à venir) sinon le cas qui a tourné.
function title(r: ExecutionSummary) {
  return r.suite_name || r.case_title || `Exécution #${r.id}`
}
// Porte ouverte à l'Exécution nommée transverse : badge mono / multi-module.
function isMulti(r: ExecutionSummary) {
  return !!r.suite_name
}

onMounted(async () => {
  try {
    runs.value = await api.listExecutions(pid.value)
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-8">
    <header>
      <h1 class="text-2xl font-semibold tracking-tight">Exécutions et résultats de test</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Historique des exécutions — verdict à deux axes de chaque run.
      </p>
    </header>

    <section class="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatTile label="Exécutions" :value="stats.total" tone="primary" icon="dot" />
      <StatTile label="Conformes" :value="stats.conformes" tone="success" icon="check" />
      <StatTile label="Non conformes" :value="stats.nonConformes" tone="destructive" icon="x" />
      <StatTile label="Erreurs techniques" :value="stats.technical" tone="warning" icon="half" />
    </section>

    <section class="rounded-xl border border-border bg-card">
      <div class="flex items-center justify-between px-5 py-3 border-b border-border">
        <h2 class="text-sm font-semibold">Runs récents</h2>
        <span class="text-xs text-muted-foreground">{{ runs.length }} au total</span>
      </div>

      <!-- Skeleton -->
      <div v-if="loading" class="divide-y divide-border">
        <div v-for="i in 3" :key="i" class="flex items-center gap-4 px-5 py-4">
          <div class="h-9 w-9 rounded-md bg-secondary animate-pulse" />
          <div class="flex-1 space-y-2">
            <div class="h-3 w-48 rounded bg-secondary animate-pulse" />
            <div class="h-2.5 w-28 rounded bg-secondary/70 animate-pulse" />
          </div>
          <div class="h-8 w-56 rounded bg-secondary animate-pulse" />
        </div>
      </div>

      <p v-else-if="error" class="px-5 py-8 text-sm text-destructive">{{ error }}</p>

      <div v-else-if="!runs.length" class="flex flex-col items-center gap-3 px-5 py-16 text-center">
        <div class="grid h-12 w-12 place-items-center rounded-full border border-border bg-surface text-muted-foreground">
          <Icon name="dot" class="h-5 w-5" />
        </div>
        <p class="text-sm text-muted-foreground">Aucune exécution enregistrée.</p>
      </div>

      <ul v-else class="divide-y divide-border">
        <li
          v-for="r in runs" :key="r.id"
          class="group flex flex-wrap items-center gap-4 px-5 py-4 cursor-pointer transition-colors hover:bg-accent/40"
          @click="router.push(`/projects/${pid}/executions/${r.id}`)"
        >
          <div class="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-border bg-surface">
            <Spinner v-if="r.running" class="h-4 w-4 text-primary" />
            <Icon v-else name="dot" class="h-3.5 w-3.5 text-muted-foreground" />
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="font-medium truncate">{{ title(r) }}</span>
              <span class="shrink-0 rounded-full border px-2 py-0.5 text-[10px] font-medium"
                    :class="isMulti(r) ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border bg-secondary text-muted-foreground'">
                {{ isMulti(r) ? 'Suite transverse' : 'Cas unique' }}
              </span>
            </div>
            <div class="text-xs text-muted-foreground truncate">
              <template v-if="r.module_name">{{ r.module_name }} · </template>{{ formatDate(r.started_at) }} · {{ formatDuration(r.duration_seconds) }}
            </div>
          </div>

          <StatusPair :execution-status="r.execution_status" :functional-status="r.functional_status" />
          <Icon name="chevron" class="h-4 w-4 shrink-0 text-muted-foreground/30 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
        </li>
      </ul>
    </section>
  </div>
</template>
