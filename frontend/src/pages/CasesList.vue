<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type CaseSummary } from '../lib/api'
import { formatDate } from '../lib/format'
import { AXIS, prettyModule } from '../lib/status'
import AxisChip from '../components/AxisChip.vue'
import ValidationBadge from '../components/ValidationBadge.vue'
import StatTile from '../components/StatTile.vue'
import Icon from '../components/ui/Icon.vue'
import Hint from '../components/ui/Hint.vue'

const router = useRouter()
const cases = ref<CaseSummary[]>([])
const loading = ref(true)
const error = ref('')

const stats = computed(() => {
  const by = (s: string) => cases.value.filter((c) => c.validation_status === s).length
  return { total: cases.value.length, validated: by('validated'), toReview: by('to_review'), never: by('never_executed') }
})

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
  <div class="space-y-8">
    <header>
      <h1 class="text-2xl font-semibold tracking-tight">Gestion des cas de tests</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Référentiel des cas — statut de validation et verdict à deux axes du dernier run.
      </p>
    </header>

    <section class="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <StatTile label="Cas de test" :value="stats.total" tone="primary" icon="dot" />
      <StatTile label="Validés" :value="stats.validated" tone="success" icon="check" />
      <StatTile label="À relire" :value="stats.toReview" tone="warning" icon="half" />
      <StatTile label="Jamais exécutés" :value="stats.never" tone="muted" icon="circle" />
    </section>

    <section class="rounded-xl border border-border bg-card">
      <div class="flex items-center justify-between px-5 py-3 border-b border-border">
        <h2 class="text-sm font-semibold">Cas</h2>
        <span class="text-xs text-muted-foreground">{{ cases.length }} au total</span>
      </div>

      <!-- Skeleton -->
      <div v-if="loading" class="divide-y divide-border">
        <div v-for="i in 3" :key="i" class="flex items-center gap-4 px-5 py-4">
          <div class="h-9 w-9 rounded-md bg-secondary animate-pulse" />
          <div class="flex-1 space-y-2">
            <div class="h-3 w-40 rounded bg-secondary animate-pulse" />
            <div class="h-2.5 w-24 rounded bg-secondary/70 animate-pulse" />
          </div>
          <div class="h-6 w-48 rounded bg-secondary animate-pulse" />
        </div>
      </div>

      <p v-else-if="error" class="px-5 py-8 text-sm text-destructive">{{ error }}</p>

      <div v-else-if="!cases.length" class="flex flex-col items-center gap-3 px-5 py-16 text-center">
        <div class="grid h-12 w-12 place-items-center rounded-full border border-border bg-surface text-muted-foreground">
          <Icon name="circle" class="h-5 w-5" />
        </div>
        <p class="text-sm text-muted-foreground">Aucun cas de test pour l'instant.</p>
      </div>

      <!-- Table à COLONNES FIXES (largeurs alignées sur toute la liste) -->
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[760px] table-fixed border-collapse">
          <colgroup>
            <col />
            <col style="width: 8.5rem" />
            <col style="width: 13rem" />
            <col style="width: 13rem" />
            <col style="width: 11rem" />
          </colgroup>
          <thead>
            <tr class="text-[11px] uppercase tracking-wide text-muted-foreground align-bottom">
              <th class="text-left font-medium px-5 pb-2 pt-1">Cas</th>
              <th class="text-left font-medium px-3 pb-2 pt-1">Validation</th>
              <th class="text-left font-medium px-3 pb-2 pt-1">
                <span class="inline-flex items-center gap-1">{{ AXIS.execution.label }}<Hint :text="AXIS.execution.hint" /></span>
              </th>
              <th class="text-left font-medium px-3 pb-2 pt-1">
                <span class="inline-flex items-center gap-1">{{ AXIS.functional.label }}<Hint :text="AXIS.functional.hint" /></span>
              </th>
              <th class="text-left font-medium px-5 pb-2 pt-1">Dernière exécution</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="c in cases" :key="c.id"
              class="group border-t border-border cursor-pointer transition-colors hover:bg-accent/40"
              @click="router.push(`/cases/${c.id}`)"
            >
              <td class="px-5 py-4 align-middle">
                <div class="flex items-center gap-3 min-w-0">
                  <div class="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-border bg-surface font-mono text-xs text-muted-foreground">
                    {{ c.module.slice(0, 2).toUpperCase() }}
                  </div>
                  <div class="min-w-0">
                    <div class="font-medium truncate">{{ c.title }}</div>
                    <div class="text-xs text-muted-foreground truncate">{{ prettyModule(c.module) }}</div>
                  </div>
                </div>
              </td>
              <td class="px-3 py-4 align-middle"><ValidationBadge :status="c.validation_status" /></td>
              <td class="px-3 py-4 align-middle"><AxisChip kind="execution" :status="c.last_execution_status" /></td>
              <td class="px-3 py-4 align-middle"><AxisChip kind="functional" :status="c.last_functional_status" /></td>
              <td class="px-5 py-4 align-middle whitespace-nowrap text-muted-foreground">
                <span class="inline-flex items-center gap-2">
                  {{ formatDate(c.last_executed_at) }}
                  <Icon name="chevron" class="h-4 w-4 text-muted-foreground/30 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
