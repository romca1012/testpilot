<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseDetail } from '../lib/api'
import { formatDate, formatDuration } from '../lib/format'
import { prettyModule } from '../lib/status'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Spinner from '../components/ui/Spinner.vue'
import Icon from '../components/ui/Icon.vue'
import StatusPair from '../components/StatusPair.vue'
import ValidationBadge from '../components/ValidationBadge.vue'
import ReviewGate from '../components/ReviewGate.vue'
import CodeView from '../components/CodeView.vue'
import FieldFallbackNotice from '../components/FieldFallbackNotice.vue'

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

// Onglet du contenu généré : Gherkin (.feature) / Steps (_steps.py).
const codeTab = ref<'gherkin' | 'steps'>('gherkin')

const currentVersion = computed(() =>
  detail.value?.versions.find((v) => v.id === detail.value?.current_version_id) || detail.value?.versions[0],
)
// Exécutions les plus récentes d'abord (vraie liste chronologique).
const executionsDesc = computed(() =>
  [...(detail.value?.executions || [])].sort((a, b) => b.id - a.id))
const lastExecution = computed(() => executionsDesc.value[0])
const currentReview = computed(() =>
  (detail.value?.reviews || []).find((r) => r.version_id === detail.value?.current_version_id))

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
    <!-- Fil d'Ariane Projet › Module › Cas -->
    <nav class="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <RouterLink to="/projects" class="hover:text-foreground">Projets</RouterLink>
      <template v-if="detail?.project">
        <Icon name="chevron" class="h-3 w-3 opacity-40" />
        <RouterLink :to="`/projects/${detail.project.id}/cases`" class="hover:text-foreground">{{ detail.project.name }}</RouterLink>
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
      <!-- Titre + état de validation (question « ce cas est-il prouvé ? », distincte du run) -->
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="flex items-center gap-3">
          <div class="grid h-10 w-10 place-items-center rounded-lg border border-border bg-surface font-mono text-xs text-muted-foreground">
            {{ (detail.module?.name || detail.case.title).slice(0, 2).toUpperCase() }}
          </div>
          <div>
            <h1 class="text-2xl font-semibold tracking-tight">{{ detail.case.title }}</h1>
            <p class="text-sm text-muted-foreground">{{ prettyModule(detail.module?.name || '') }}</p>
          </div>
        </div>
        <div class="flex flex-col items-end gap-1">
          <span class="text-[10px] uppercase tracking-wider text-muted-foreground">État du cas</span>
          <ValidationBadge :status="detail.case.validation_status" />
        </div>
      </div>

      <!-- 1. DERNIER RÉSULTAT — le résumé, en premier, explicitement labellisé -->
      <Card>
        <template #header>
          <span class="text-[11px] uppercase tracking-wide text-muted-foreground">Dernier résultat</span>
        </template>
        <div v-if="lastExecution" class="flex flex-wrap items-center justify-between gap-4">
          <StatusPair :execution-status="lastExecution.execution_status" :functional-status="lastExecution.functional_status" />
          <div class="flex items-center gap-3 text-xs text-muted-foreground">
            <span>Exécuté le {{ formatDate(lastExecution.started_at) }} · {{ formatDuration(lastExecution.duration_seconds) }}</span>
            <RouterLink :to="`/projects/${pid}/executions/${lastExecution.id}`"
                        class="inline-flex items-center gap-1 text-primary hover:underline">
              Voir le rapport <Icon name="chevron" class="h-3 w-3" />
            </RouterLink>
          </div>
        </div>
        <p v-else class="text-sm text-muted-foreground">Pas encore exécuté.</p>

        <!-- Repli de champ du dernier run (0007 B+) : non-bloquant, affiché même sur un run vert. -->
        <FieldFallbackNotice :fallbacks="lastExecution?.field_fallbacks || []" class="mt-3" />
      </Card>

      <!-- 2. RELECTURE (validation humaine du contenu généré) — bloc distinct -->
      <Card title="Relecture">
        <div class="space-y-3">
          <ReviewGate :case-id="caseId" :gate="detail.gate" @reviewed="load" />
          <p v-if="currentReview" class="text-xs text-muted-foreground">
            Dernière décision : {{ currentReview.decision === 'approved' ? 'approuvée' : 'rejetée' }}
            par {{ reviewerLabel(currentReview.reviewer) }} · {{ formatDate(currentReview.decided_at) }}
          </p>
        </div>
      </Card>

      <!-- 3. EXÉCUTION (lancer un run réel) — bloc distinct -->
      <Card title="Exécution">
        <div class="flex flex-wrap items-center gap-3">
          <Button variant="primary" :loading="running" :disabled="!detail.gate?.allowed" @click="launch">
            Lancer une exécution
          </Button>
          <span v-if="running" class="text-xs text-muted-foreground">Exécution en cours…</span>
          <span v-else-if="!detail.gate?.allowed" class="text-xs text-muted-foreground">
            Approuvez la version en relecture pour pouvoir la lancer.
          </span>
        </div>
        <p v-if="runError" class="mt-2 text-xs text-destructive">{{ runError }}</p>
      </Card>

      <!-- 4. CONTENU GÉNÉRÉ — onglets Gherkin / Steps -->
      <Card title="Contenu généré">
        <template #header>
          <div class="flex rounded-md border border-border p-0.5">
            <button
              v-for="t in (['gherkin','steps'] as const)" :key="t"
              class="rounded px-3 py-1 text-xs font-medium transition-colors"
              :class="codeTab === t ? 'bg-primary/15 text-foreground' : 'text-muted-foreground hover:text-foreground'"
              @click="codeTab = t"
            >{{ t === 'gherkin' ? 'Gherkin (.feature)' : 'Steps (_steps.py)' }}</button>
          </div>
        </template>
        <template v-if="currentVersion">
          <CodeView v-if="codeTab === 'gherkin'" :content="currentVersion.feature_content" lang="gherkin" />
          <CodeView v-else :content="currentVersion.steps_content" lang="python" />
        </template>
        <p v-else class="text-sm text-muted-foreground">Aucune version générée.</p>
      </Card>

      <!-- 5. HISTORIQUE DES EXÉCUTIONS — vraie liste chronologique (pas le résumé du haut) -->
      <Card title="Historique des exécutions">
        <p v-if="!executionsDesc.length" class="text-sm text-muted-foreground">Aucune exécution.</p>
        <ul v-else class="divide-y divide-border">
          <li v-for="e in executionsDesc" :key="e.id"
              class="group flex flex-wrap items-center justify-between gap-3 py-3 cursor-pointer hover:bg-accent/30 -mx-2 px-2 rounded"
              @click="router.push(`/projects/${pid}/executions/${e.id}`)">
            <span class="text-xs text-muted-foreground w-44 shrink-0">
              {{ formatDate(e.started_at) }} · {{ formatDuration(e.duration_seconds) }}
            </span>
            <StatusPair :execution-status="e.execution_status" :functional-status="e.functional_status" />
            <!-- Pastille de repli (0007 B+) : UNIQUEMENT sur les runs qui en portent un — jamais
                 par défaut. Le signal doit survivre au run suivant, sinon la détection a
                 posteriori d'un champ renommé rouvrirait un angle mort dans le temps. -->
            <span v-if="e.field_fallbacks?.length"
                  class="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[11px] text-warning"
                  :title="`Champ résolu par son libellé, pas par son nom technique :\n${e.field_fallbacks.join('\n')}`">
              ⚠ Repli de champ
            </span>
            <Icon name="chevron" class="h-4 w-4 text-muted-foreground/30 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
          </li>
        </ul>
      </Card>

      <!-- Versions (historique du contenu) — dit CE QUI A CHANGÉ, pas seulement « v2 ».
           Une réparation crée une version (0014) : sans son résumé, elle serait une boîte
           noire et l'humain ratifierait à l'aveugle. -->
      <Card title="Versions">
        <ul class="divide-y divide-border text-sm">
          <li v-for="v in detail.versions" :key="v.id" class="py-2.5">
            <div class="flex items-center justify-between gap-3">
              <span class="flex items-center gap-2">
                v{{ v.version_number }}
                <span v-if="v.id === detail.current_version_id" class="text-xs text-primary">courante</span>
                <span v-if="v.created_by === 'repair-agent'"
                      class="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[11px] text-warning">
                  ⚠ réparation automatique
                </span>
              </span>
              <span class="shrink-0 text-xs text-muted-foreground">{{ formatDate(v.created_at) }}</span>
            </div>
            <p v-if="v.change_summary" class="mt-1 text-xs text-muted-foreground">
              {{ v.change_summary }}
            </p>
          </li>
        </ul>
      </Card>
    </template>
  </div>
</template>
