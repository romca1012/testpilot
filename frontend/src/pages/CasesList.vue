<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type CaseSummary } from '../lib/api'
import { formatDate } from '../lib/format'
import StatusPair from '../components/StatusPair.vue'
import ValidationBadge from '../components/ValidationBadge.vue'
import Spinner from '../components/ui/Spinner.vue'

const router = useRouter()
const cases = ref<CaseSummary[]>([])
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    cases.value = await api.listCases()
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
      <h1 class="text-xl font-semibold">Gestion des cas de tests</h1>
      <p class="text-sm text-muted-foreground">Référentiel des cas — statut de validation et deux derniers axes du verdict.</p>
    </div>

    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground text-sm">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>
    <p v-else-if="!cases.length" class="text-sm text-muted-foreground">Aucun cas de test pour l'instant.</p>

    <div v-else class="overflow-x-auto rounded-xl border border-border">
      <table class="w-full text-sm">
        <thead class="text-[11px] uppercase tracking-wide text-muted-foreground bg-surface/60">
          <tr>
            <th class="text-left font-medium px-4 py-3">Cas</th>
            <th class="text-left font-medium px-4 py-3">Validation</th>
            <th class="text-left font-medium px-4 py-3">Dernier verdict (2 axes)</th>
            <th class="text-left font-medium px-4 py-3">Dernière exécution</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="c in cases" :key="c.id"
            class="border-t border-border hover:bg-accent/40 cursor-pointer transition-colors"
            @click="router.push(`/cases/${c.id}`)"
          >
            <td class="px-4 py-3">
              <div class="font-medium">{{ c.title }}</div>
              <div class="text-xs text-muted-foreground">{{ c.module }}</div>
            </td>
            <td class="px-4 py-3"><ValidationBadge :status="c.validation_status" /></td>
            <td class="px-4 py-3">
              <StatusPair :execution-status="c.last_execution_status" :functional-status="c.last_functional_status" />
            </td>
            <td class="px-4 py-3 text-muted-foreground">{{ formatDate(c.last_executed_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
