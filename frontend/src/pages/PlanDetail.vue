<script setup lang="ts">
// Fiche d'un Plan de test (migration 43) — ses campagnes assignées, groupées par MODE.
//
// ⚠️ **Jamais un chiffre unique fusionnant manuel et automatique** (exigence du porteur). Une
// campagne automatique prouve quelque chose par la machine ; une campagne manuelle vaut ce que
// vaut la personne qui l'a jouée. Les mélanger dans un seul taux de réussite ferait dire au Plan
// « 80 % » sans que personne ne puisse savoir quelle part vient de qui — d'où deux sections
// distinctes, jamais une moyenne commune.
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { roleSuffisant, type RunSummary } from '../lib/api'
import { useSession } from '../lib/useSession'
import { useProjects } from '../lib/useProjects'
import { useUnPlan, useRuns, useAssignerRunAuPlan, useRetirerRunDuPlan } from '../lib/donnees'
import Button from '../components/ui/Button.vue'
import Modal from '../components/ui/Modal.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const planId = computed(() => route.params.id as string)
const { session } = useSession()
const { projectById } = useProjects()
const peutModifier = computed(() => roleSuffisant(projectById(pid.value)?.effective_role || session.value?.role || '', 'testeur'))

const { data: detail, isLoading, error: erreurDetail, refetch } = useUnPlan(planId)
const plan = computed(() => detail.value?.plan)
const runs = computed<RunSummary[]>(() => detail.value?.runs ?? [])
const loading = computed(() => isLoading.value && !detail.value)
const error = computed(() => (erreurDetail.value ? 'Impossible de charger ce plan de test.' : ''))

function completion(r: RunSummary) {
  return r.case_count ? Math.round((r.tested_count / r.case_count) * 100) : 0
}
const STATUS: Record<string, { label: string; cls: string }> = {
  draft: { label: 'Brouillon', cls: 'bg-secondary text-muted-foreground' },
  running: { label: 'En cours', cls: 'bg-warning/15 text-warning' },
  completed: { label: 'Terminé', cls: 'bg-success/15 text-success' },
}
function statusOf(r: RunSummary) { return STATUS[r.status] || STATUS.draft }

const automatiques = computed(() => runs.value.filter((r) => r.mode !== 'manuelle'))
const manuelles = computed(() => runs.value.filter((r) => r.mode === 'manuelle'))

function openRun(id: number) {
  router.push({ name: 'run-detail', params: { pid: pid.value, id: String(id) } })
}
function goBack() { router.push({ name: 'plans', params: { pid: pid.value } }) }

// ── Retirer une campagne du plan ────────────────────────────────────────────────────────────
const retirer = useRetirerRunDuPlan(pid)
async function retirerRun(r: RunSummary) {
  if (!plan.value) return
  if (!window.confirm(`Retirer « ${r.name} » de ce plan ? La campagne elle-même n'est pas touchée.`)) return
  try {
    await retirer.mutateAsync({ planId: plan.value.id, runId: r.id })
  } catch (e: any) {
    window.alert(e?.message || 'Retrait impossible.')
  }
}

// ── Assigner une campagne EXISTANTE du projet ───────────────────────────────────────────────
// Toutes les campagnes du projet, pas seulement celles hors plan : rattacher une campagne déjà
// dans un AUTRE plan la déplace simplement (une campagne n'appartient qu'à un plan à la fois),
// ce que le champ affiche explicitement pour ne surprendre personne.
const showAssign = ref(false)
const { data: toutesLesRuns } = useRuns(computed(() => plan.value?.project_id))
const candidats = computed(() =>
  (toutesLesRuns.value ?? []).filter((r) => r.plan_id !== plan.value?.id))
const assigner = useAssignerRunAuPlan(pid)
const assignError = ref('')
async function assignerRun(r: RunSummary) {
  if (!plan.value) return
  assignError.value = ''
  try {
    await assigner.mutateAsync({ planId: plan.value.id, runId: r.id })
    showAssign.value = false
  } catch (e: any) {
    assignError.value = e?.message || 'Assignation impossible.'
  }
}
</script>

<template>
  <div>
    <button class="text-sm text-muted-foreground hover:text-foreground flex items-center gap-1" @click="goBack">
      <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg>
      Plans de test
    </button>

    <div v-if="loading" class="mt-4 space-y-2">
      <div class="h-8 w-1/3 rounded-md bg-secondary animate-pulse"></div>
      <div v-for="i in 3" :key="i" class="h-14 rounded-md bg-secondary animate-pulse"></div>
    </div>
    <div v-else-if="error" class="mt-8 text-center">
      <p class="text-sm text-muted-foreground">{{ error }}</p>
      <Button variant="secondary" class="mt-3" @click="() => refetch()">Réessayer</Button>
    </div>

    <template v-else-if="plan">
      <div class="mt-2 flex items-start justify-between gap-4">
        <div class="min-w-0">
          <h1 class="text-2xl font-semibold tracking-tight truncate">{{ plan.name }}</h1>
          <p v-if="plan.description" class="mt-1 text-sm text-muted-foreground">{{ plan.description }}</p>
          <p v-if="plan.refs" class="mt-1 text-xs text-muted-foreground">Réfs. {{ plan.refs }}</p>
        </div>
        <Button v-if="peutModifier" variant="primary" class="shrink-0" @click="showAssign = true">
          + Ajouter une exécution
        </Button>
      </div>

      <p v-if="!runs.length" class="mt-10 text-center text-sm text-muted-foreground">
        Aucune campagne assignée à ce plan pour l'instant.
      </p>

      <!-- ── Automatique et Manuelle : DEUX sections, jamais un chiffre commun. ── -->
      <div v-if="automatiques.length" class="mt-6">
        <h2 class="text-sm font-semibold text-muted-foreground flex items-center gap-2">
          <span class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium border border-success/30 bg-success/15 text-success">Automatique</span>
          {{ automatiques.length }} campagne(s) — jouée(s) par la machine
        </h2>
        <div class="mt-2 divide-y divide-border/40 border-t border-border/40">
          <div v-for="r in automatiques" :key="r.id" class="flex items-center gap-4 py-3 px-2 -mx-2 hover:bg-accent/30 rounded-md">
            <button type="button" class="flex items-center gap-4 min-w-0 flex-1 text-left" @click="openRun(r.id)">
              <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold shrink-0" :class="statusOf(r).cls">
                {{ statusOf(r).label }}
              </span>
              <div class="min-w-0 flex-1">
                <div class="text-sm text-primary truncate">R{{ r.id }} — {{ r.name }}</div>
                <div class="text-xs text-muted-foreground mt-0.5">{{ r.tested_count }}/{{ r.case_count }} cas testés</div>
              </div>
            </button>
            <span class="text-xs tabular-nums text-muted-foreground shrink-0 w-10 text-right">{{ completion(r) }} %</span>
            <Button v-if="peutModifier" variant="ghost" size="sm" class="shrink-0 text-destructive" @click="retirerRun(r)">Retirer</Button>
          </div>
        </div>
      </div>

      <div v-if="manuelles.length" class="mt-6">
        <h2 class="text-sm font-semibold text-muted-foreground flex items-center gap-2">
          <span class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium border border-warning/40 bg-warning/15 text-warning">Manuelle</span>
          {{ manuelles.length }} campagne(s) — jouée(s) à la main
        </h2>
        <div class="mt-2 divide-y divide-border/40 border-t border-border/40">
          <div v-for="r in manuelles" :key="r.id" class="flex items-center gap-4 py-3 px-2 -mx-2 hover:bg-accent/30 rounded-md">
            <button type="button" class="flex items-center gap-4 min-w-0 flex-1 text-left" @click="openRun(r.id)">
              <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold shrink-0" :class="statusOf(r).cls">
                {{ statusOf(r).label }}
              </span>
              <div class="min-w-0 flex-1">
                <div class="text-sm text-primary truncate">R{{ r.id }} — {{ r.name }}</div>
                <div class="text-xs text-muted-foreground mt-0.5">{{ r.tested_count }}/{{ r.case_count }} cas testés</div>
              </div>
            </button>
            <span class="text-xs tabular-nums text-muted-foreground shrink-0 w-10 text-right">{{ completion(r) }} %</span>
            <Button v-if="peutModifier" variant="ghost" size="sm" class="shrink-0 text-destructive" @click="retirerRun(r)">Retirer</Button>
          </div>
        </div>
      </div>
    </template>

    <!-- ════════ Assigner une campagne existante ════════ -->
    <Modal :open="showAssign" title="Ajouter une exécution au plan"
           subtitle="Rattacher une campagne déjà créée — rien n'est relancé ni modifié."
           @close="showAssign = false">
      <p v-if="!candidats.length" class="text-sm text-muted-foreground">
        Aucune autre campagne disponible dans ce projet.
      </p>
      <div v-else class="max-h-80 overflow-y-auto divide-y divide-border/40 -mx-1">
        <button v-for="r in candidats" :key="r.id" type="button"
                class="w-full text-left flex items-center gap-3 py-2.5 px-1 hover:bg-accent/30 rounded-md"
                @click="assignerRun(r)">
          <span class="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium shrink-0"
                :class="r.mode === 'manuelle' ? 'border border-warning/40 bg-warning/15 text-warning' : 'border border-success/30 bg-success/15 text-success'">
            {{ r.mode === 'manuelle' ? 'Manuelle' : 'Automatique' }}
          </span>
          <span class="min-w-0 flex-1 truncate text-sm">R{{ r.id }} — {{ r.name }}</span>
          <span v-if="r.plan_id" class="text-xs text-muted-foreground shrink-0">déjà dans un autre plan</span>
        </button>
      </div>
      <p v-if="assignError" class="mt-2 text-sm text-destructive">{{ assignError }}</p>
    </Modal>
  </div>
</template>
