<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseDetail } from '../lib/api'
import { formatDate, formatDuration } from '../lib/format'
import { prettyModule } from '../lib/status'
import Button from '../components/ui/Button.vue'
import Spinner from '../components/ui/Spinner.vue'
import Icon from '../components/ui/Icon.vue'
import StatusPair from '../components/StatusPair.vue'
import ValidationBadge from '../components/ValidationBadge.vue'
import ReviewGate from '../components/ReviewGate.vue'
import GherkinView from '../components/GherkinView.vue'

const route = useRoute()
const router = useRouter()
const caseId = Number(route.params.id)
const pid = computed(() => route.params.pid as string)

const detail = ref<CaseDetail | null>(null)
const loading = ref(true)
const error = ref('')
const running = ref(false)
const runError = ref('')
let pollTimer: number | undefined

// Versions les plus récentes d'abord (la courante en tête).
const versionsDesc = computed(() =>
  [...(detail.value?.versions || [])].sort((a, b) => b.version_number - a.version_number),
)
function reviewsFor(versionId: number) {
  return (detail.value?.reviews || []).filter((r) => r.version_id === versionId)
}
function executionsFor(versionId: number) {
  return (detail.value?.executions || []).filter((e) => e.version_id === versionId)
}
function reviewerLabel(reviewer: string) {
  return reviewer === 'cli' ? 'ligne de commande' : reviewer || '—'
}

async function load() {
  try {
    detail.value = await api.getCase(caseId)
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
}

async function launch() {
  runError.value = ''
  running.value = true
  try {
    const { execution_id } = await api.runCase(caseId)
    poll(execution_id)
  } catch (e: any) {
    running.value = false
    runError.value = e?.message || 'Échec du lancement'
  }
}

function poll(execId: number) {
  pollTimer = window.setInterval(async () => {
    try {
      const exec = await api.getExecution(execId)
      if (!exec.running) {
        stopPoll(); running.value = false
        router.push(`/projects/${pid.value}/executions/${execId}`)
      }
    } catch {
      stopPoll(); running.value = false
      runError.value = 'Suivi de l\'exécution interrompu'
    }
  }, 1500)
}
function stopPoll() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = undefined
}

onMounted(load)
onBeforeUnmount(stopPoll)
</script>

<template>
  <div class="space-y-6">
    <!-- Fil d'Ariane Projet › Module › Cas (§7) -->
    <nav class="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <RouterLink to="/projects" class="hover:text-foreground">Projets</RouterLink>
      <template v-if="detail?.project">
        <Icon name="chevron" class="h-3 w-3 opacity-40" />
        <RouterLink :to="`/projects/${detail.project.id}/cases`" class="hover:text-foreground">
          {{ detail.project.name }}
        </RouterLink>
      </template>
      <template v-if="detail?.module">
        <Icon name="chevron" class="h-3 w-3 opacity-40" />
        <span>{{ detail.module.name }}</span>
      </template>
      <template v-if="detail">
        <Icon name="chevron" class="h-3 w-3 opacity-40" />
        <span class="text-foreground">{{ detail.case.title }}</span>
      </template>
    </nav>

    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground text-sm">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>

    <template v-else-if="detail">
      <!-- En-tête du cas (racine de l'arbre) -->
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="flex items-center gap-3">
          <div class="grid h-10 w-10 place-items-center rounded-lg border border-border bg-surface font-mono text-xs text-muted-foreground">
            {{ detail.case.module.slice(0, 2).toUpperCase() }}
          </div>
          <div>
            <h1 class="text-xl font-semibold tracking-tight">{{ detail.case.title }}</h1>
            <p class="text-sm text-muted-foreground">{{ prettyModule(detail.case.module) }}</p>
          </div>
        </div>
        <ValidationBadge :status="detail.case.validation_status" />
      </div>
      <StatusPair
        :execution-status="detail.case.last_execution_status"
        :functional-status="detail.case.last_functional_status"
      />

      <!-- Arbre : versions et, sous chacune, ses relectures / Gherkin / exécutions -->
      <div class="tree-branch space-y-6 pt-2">
        <div v-for="v in versionsDesc" :key="v.id" class="tree-node">
          <!-- Nœud version -->
          <div class="flex flex-wrap items-center gap-2">
            <span class="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-raised px-2.5 py-1 text-sm font-medium">
              <Icon name="dot" class="h-3 w-3 text-primary" /> Version {{ v.version_number }}
            </span>
            <span v-if="v.id === detail.current_version_id"
                  class="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] text-primary">courante</span>
            <span class="text-xs text-muted-foreground">créée le {{ formatDate(v.created_at) }}</span>
          </div>

          <!-- Enfants de la version -->
          <div class="tree-branch mt-4 space-y-4">
            <!-- Action : gate + lancement, rattaché à la VERSION COURANTE -->
            <div v-if="v.id === detail.current_version_id" class="tree-node rounded-lg border border-border bg-card p-4">
              <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-3">Relecture &amp; exécution</div>
              <ReviewGate :case-id="caseId" :gate="detail.gate" @reviewed="load" />
              <div class="mt-4 flex items-center gap-3 border-t border-border pt-3">
                <Button variant="primary" :loading="running" :disabled="!detail.gate?.allowed" @click="launch">
                  Lancer une exécution
                </Button>
                <span v-if="running" class="text-xs text-muted-foreground">Exécution en cours…</span>
                <span v-else-if="!detail.gate?.allowed" class="text-xs text-muted-foreground">
                  Approuvez la version pour pouvoir la lancer.
                </span>
              </div>
              <p v-if="runError" class="mt-2 text-xs text-destructive">{{ runError }}</p>
            </div>

            <!-- Contenu généré (Gherkin), repliable -->
            <details class="tree-node group rounded-lg border border-border bg-card" open>
              <summary class="flex cursor-pointer list-none items-center gap-2 px-4 py-2.5 text-sm">
                <Icon name="chevron" class="h-3.5 w-3.5 text-muted-foreground transition-transform group-open:rotate-90" />
                Contenu généré (Gherkin)
              </summary>
              <div class="px-4 pb-4">
                <GherkinView :content="v.feature_content" />
              </div>
            </details>

            <!-- Relectures de cette version -->
            <div class="tree-node">
              <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Relectures</div>
              <p v-if="!reviewsFor(v.id).length" class="text-sm text-muted-foreground">Aucune relecture.</p>
              <ul v-else class="space-y-1.5">
                <li v-for="r in reviewsFor(v.id)" :key="r.id" class="flex items-center gap-2 text-sm">
                  <Icon :name="r.decision === 'approved' ? 'check' : 'x'" class="h-3.5 w-3.5"
                        :class="r.decision === 'approved' ? 'text-success' : 'text-destructive'" />
                  <span>{{ r.decision === 'approved' ? 'Approuvée' : 'Rejetée' }}</span>
                  <span class="text-muted-foreground">par {{ reviewerLabel(r.reviewer) }} · {{ formatDate(r.decided_at) }}</span>
                </li>
              </ul>
            </div>

            <!-- Exécutions de cette version -->
            <div class="tree-node">
              <div class="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Exécutions</div>
              <p v-if="!executionsFor(v.id).length" class="text-sm text-muted-foreground">Aucune exécution pour cette version.</p>
              <ul v-else class="space-y-2">
                <li v-for="e in executionsFor(v.id)" :key="e.id"
                    class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface/40 px-3 py-2.5 cursor-pointer hover:bg-accent/40 transition-colors"
                    @click="router.push(`/projects/${pid}/executions/${e.id}`)">
                  <StatusPair :execution-status="e.execution_status" :functional-status="e.functional_status" />
                  <span class="flex items-center gap-2 text-xs text-muted-foreground">
                    {{ formatDate(e.started_at) }} · {{ formatDuration(e.duration_seconds) }}
                    <Icon name="chevron" class="h-3.5 w-3.5 text-muted-foreground/40" />
                  </span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
