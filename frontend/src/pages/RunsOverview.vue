<script setup lang="ts">
// « Exécutions et résultats de test » — Aperçu des RUNS (campagnes, décision 0022 n°8).
//
// Auparavant, cette page listait les `execution` (des runs MONO-cas) faute de modèle de campagne.
// Elle liste maintenant les vrais `test_run`. Les exécutions mono-cas héritées restent en base
// et gardent leur rapport ; elles n'ont simplement pas de campagne — on ne les mélange plus ici.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type RunSummary } from '../lib/api'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)

const runs = ref<RunSummary[]>([])
const loading = ref(true)
const error = ref('')
const sortBy = computed(() => (route.query.sort as string) || 'date')

async function load() {
  loading.value = true; error.value = ''
  try {
    runs.value = await api.listRuns(pid.value)
  } catch {
    error.value = 'Impossible de charger les exécutions.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(pid, load)

// % de complétion = cas ayant un résultat / cas du run (note fonctionnelle, écran Aperçu).
function completion(r: RunSummary) {
  return r.case_count ? Math.round((r.tested_count / r.case_count) * 100) : 0
}
const STATUS: Record<string, { label: string; cls: string }> = {
  draft: { label: 'Brouillon', cls: 'bg-secondary text-muted-foreground' },
  running: { label: 'En cours', cls: 'bg-warning/15 text-warning' },
  completed: { label: 'Terminé', cls: 'bg-success/15 text-success' },
}
function statusOf(r: RunSummary) { return STATUS[r.status] || STATUS.draft }

// Archivés SÉPARÉS des actifs (note fonctionnelle) : l'historique ne doit pas polluer la vue de
// travail. Repliés par défaut — visibles, mais pas au premier plan.
const actifs = computed(() => runs.value.filter((r) => !r.is_archived))
const archives = computed(() => runs.value.filter((r) => r.is_archived))
const showArchived = ref(false)

const sorted = computed(() => {
  const arr = [...actifs.value]
  if (sortBy.value === 'name') arr.sort((a, b) => a.name.localeCompare(b.name))
  else if (sortBy.value === 'pass') arr.sort((a, b) => completion(b) - completion(a))
  else arr.sort((a, b) => b.created_at.localeCompare(a.created_at))
  return arr
})
function monthLabel(iso: string) {
  const s = new Date(iso).toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' })
  return s.charAt(0).toUpperCase() + s.slice(1)
}
const groups = computed(() => {
  const map = new Map<string, RunSummary[]>()
  for (const r of sorted.value) {
    const k = monthLabel(r.created_at)
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(r)
  }
  return [...map.entries()].map(([month, rows]) => ({ month, rows }))
})

function openRun(id: number) {
  router.push({ name: 'run-detail', params: { pid: pid.value, id: String(id) } })
}
function goNew() { router.push({ name: 'run-new', params: { pid: pid.value } }) }
</script>

<template>
  <div>
    <div class="flex-1 min-w-0">
      <div class="flex items-center justify-between">
        <h1 class="text-[26px] font-semibold tracking-tight">Exécutions et résultats de test</h1>
        <button class="rounded-md bg-primary text-white font-semibold px-3 py-1.5 text-sm hover:bg-primary/90"
                @click="goNew">+ Ajouter une exécution</button>
      </div>

      <div v-if="loading" class="mt-6 space-y-2">
        <div v-for="i in 4" :key="i" class="h-12 rounded-md bg-secondary animate-pulse"></div>
      </div>
      <div v-else-if="error" class="mt-8 text-center">
        <p class="text-sm text-muted-foreground">{{ error }}</p>
        <button class="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:border-primary/40" @click="load">Réessayer</button>
      </div>
      <p v-else-if="!runs.length" class="mt-10 text-center text-sm text-muted-foreground">
        Aucune exécution pour ce projet. Créez-en une avec « Ajouter une exécution ».
      </p>

      <div v-for="g in groups" :key="g.month" class="mt-5">
        <div class="text-sm font-medium text-muted-foreground border-b border-border/60 pb-1">{{ g.month }}</div>
        <button v-for="r in g.rows" :key="r.id"
                class="w-full text-left flex items-center gap-4 py-3 border-b border-border/40 hover:bg-accent/30 rounded-md px-2 -mx-2"
                @click="openRun(r.id)">
          <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[12px] font-semibold shrink-0" :class="statusOf(r).cls">
            {{ statusOf(r).label }}
          </span>
          <div class="min-w-0 flex-1">
            <div class="text-sm text-primary truncate">R{{ r.id }} — {{ r.name }}</div>
            <div class="text-xs text-muted-foreground mt-0.5">
              {{ r.tested_count }}/{{ r.case_count }} cas testés ·
              {{ r.selection_mode === 'all' ? 'tous les cas (vivante)' : 'sélection figée' }}
            </div>
          </div>
          <div class="shrink-0 w-28 hidden sm:block">
            <div class="flex items-center gap-2">
              <div class="flex-1 h-1.5 rounded-full bg-border overflow-hidden">
                <div class="h-full rounded-full bg-success" :style="{ width: completion(r) + '%' }"></div>
              </div>
              <span class="text-xs tabular-nums text-muted-foreground">{{ completion(r) }} %</span>
            </div>
          </div>
        </button>
      </div>

      <!-- Archivées : repliées par défaut. Rien n'est caché — juste rangé. -->
      <div v-if="archives.length" class="mt-8">
        <button class="flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
                @click="showArchived = !showArchived">
          <svg class="w-3.5 h-3.5 transition-transform" :class="showArchived ? 'rotate-90' : ''" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5l8 7-8 7z"/></svg>
          Archivées ({{ archives.length }})
        </button>
        <div v-if="showArchived" class="mt-2">
          <button v-for="r in archives" :key="r.id"
                  class="w-full text-left flex items-center gap-4 py-3 border-b border-border/40 hover:bg-accent/30 rounded-md px-2 -mx-2 opacity-75"
                  @click="openRun(r.id)">
            <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[12px] font-semibold shrink-0 bg-secondary text-muted-foreground">
              Archivée
            </span>
            <div class="min-w-0 flex-1">
              <div class="text-sm text-primary truncate">R{{ r.id }} — {{ r.name }}</div>
              <div class="text-xs text-muted-foreground mt-0.5">{{ r.tested_count }}/{{ r.case_count }} cas testés</div>
            </div>
            <span class="text-xs tabular-nums text-muted-foreground shrink-0">{{ completion(r) }} %</span>
          </button>
        </div>
      </div>

      <!-- Plans de test : conteneur de runs, non construit (incrément 2) — dit, jamais fabriqué. -->
      <div class="mt-8 rounded-lg border border-dashed border-border p-5">
        <div class="text-sm font-medium">Plans de test</div>
        <p class="mt-1 text-xs text-muted-foreground">
          Un plan regroupera plusieurs exécutions (par exemple une par configuration).
          Pas encore construit — aucun plan n'existe.
        </p>
      </div>
    </div>
  </div>
</template>
