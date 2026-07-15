<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type ExecutionSummary } from '../lib/api'
import { formatDate, formatDuration } from '../lib/format'
import StatusPair from '../components/StatusPair.vue'
import Spinner from '../components/ui/Spinner.vue'

const router = useRouter()
const runs = ref<ExecutionSummary[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    runs.value = await api.listExecutions()
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-xl font-semibold">Exécution</h1>
      <p class="text-sm text-muted-foreground">Historique des exécutions — verdict à deux axes de chaque run.</p>
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground text-sm">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>
    <p v-else-if="!runs.length" class="text-sm text-muted-foreground">Aucune exécution enregistrée.</p>

    <ul v-else class="rounded-xl border border-border divide-y divide-border">
      <li v-for="r in runs" :key="r.id"
          class="flex flex-wrap items-center justify-between gap-3 px-4 py-3 cursor-pointer hover:bg-accent/40 transition-colors"
          @click="router.push(`/executions/${r.id}`)">
        <div class="flex items-center gap-3">
          <Spinner v-if="r.running" class="h-4 w-4 text-primary" />
          <StatusPair :execution-status="r.execution_status" :functional-status="r.functional_status" />
        </div>
        <span class="text-xs text-muted-foreground">
          #{{ r.id }} · {{ formatDuration(r.duration_seconds) }} · {{ formatDate(r.started_at) }}
        </span>
      </li>
    </ul>
  </div>
</template>
