<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseDetail } from '../lib/api'
import { formatDate, formatDuration } from '../lib/format'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Spinner from '../components/ui/Spinner.vue'
import StatusPair from '../components/StatusPair.vue'
import ValidationBadge from '../components/ValidationBadge.vue'
import ReviewGate from '../components/ReviewGate.vue'
import GherkinView from '../components/GherkinView.vue'

const route = useRoute()
const router = useRouter()
const caseId = Number(route.params.id)

const detail = ref<CaseDetail | null>(null)
const loading = ref(true)
const error = ref('')
const running = ref(false)
const runError = ref('')
let pollTimer: number | undefined

const currentVersion = computed(() =>
  detail.value?.versions.find((v) => v.id === detail.value?.current_version_id) || detail.value?.versions[0],
)

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
    runError.value = e?.message || "Échec du lancement"
  }
}

function poll(execId: number) {
  pollTimer = window.setInterval(async () => {
    try {
      const exec = await api.getExecution(execId)
      if (!exec.running) {
        stopPoll()
        running.value = false
        router.push(`/executions/${execId}`)
      }
    } catch {
      stopPoll()
      running.value = false
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
    <RouterLink to="/cases" class="text-xs text-muted-foreground hover:text-foreground">← Gestion des cas</RouterLink>

    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground text-sm">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>

    <template v-else-if="detail">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 class="text-xl font-semibold">{{ detail.case.title }}</h1>
          <p class="text-sm text-muted-foreground">{{ detail.case.module }}</p>
        </div>
        <ValidationBadge :status="detail.case.validation_status" />
      </div>

      <StatusPair
        :execution-status="detail.case.last_execution_status"
        :functional-status="detail.case.last_functional_status"
      />

      <!-- Gate de relecture actionnable + lancement -->
      <Card title="Relecture & exécution">
        <div class="space-y-4">
          <ReviewGate :case-id="caseId" :gate="detail.gate" @reviewed="load" />
          <div class="flex items-center gap-3 pt-1 border-t border-border">
            <Button variant="primary" :loading="running" :disabled="!detail.gate?.allowed" @click="launch">
              Lancer une exécution
            </Button>
            <span v-if="running" class="text-xs text-muted-foreground">Exécution en cours…</span>
            <span v-else-if="!detail.gate?.allowed" class="text-xs text-muted-foreground">
              Approuvez la version pour pouvoir lancer une exécution.
            </span>
          </div>
          <p v-if="runError" class="text-xs text-destructive">{{ runError }}</p>
        </div>
      </Card>

      <!-- Gherkin de la version courante -->
      <Card title="Gherkin (version courante)">
        <GherkinView v-if="currentVersion" :content="currentVersion.feature_content" />
        <p v-else class="text-sm text-muted-foreground">Aucune version générée.</p>
      </Card>

      <!-- Versions -->
      <Card title="Versions">
        <ul class="divide-y divide-border text-sm">
          <li v-for="v in detail.versions" :key="v.id" class="flex items-center justify-between py-2">
            <span>v{{ v.version_number }}
              <span v-if="v.id === detail.current_version_id" class="ml-2 text-xs text-primary">courante</span>
            </span>
            <span class="text-xs text-muted-foreground">{{ formatDate(v.created_at) }}</span>
          </li>
        </ul>
      </Card>

      <!-- Décisions de relecture -->
      <Card title="Décisions de relecture">
        <p v-if="!detail.reviews.length" class="text-sm text-muted-foreground">Aucune relecture enregistrée.</p>
        <ul v-else class="divide-y divide-border text-sm">
          <li v-for="r in detail.reviews" :key="r.id" class="flex items-center justify-between py-2">
            <span>
              <span :class="r.decision === 'approved' ? 'text-success' : 'text-destructive'">
                {{ r.decision === 'approved' ? 'Approuvée' : 'Rejetée' }}
              </span>
              <span class="text-muted-foreground"> · v{{ r.version_id }} · {{ r.reviewer || '—' }}</span>
            </span>
            <span class="text-xs text-muted-foreground">{{ formatDate(r.decided_at) }}</span>
          </li>
        </ul>
      </Card>

      <!-- Exécutions du cas -->
      <Card title="Exécutions">
        <p v-if="!detail.executions.length" class="text-sm text-muted-foreground">Aucune exécution.</p>
        <ul v-else class="divide-y divide-border">
          <li v-for="e in detail.executions" :key="e.id"
              class="flex flex-wrap items-center justify-between gap-3 py-3 cursor-pointer hover:bg-accent/30 -mx-2 px-2 rounded"
              @click="router.push(`/executions/${e.id}`)">
            <StatusPair :execution-status="e.execution_status" :functional-status="e.functional_status" />
            <span class="text-xs text-muted-foreground">
              {{ formatDuration(e.duration_seconds) }} · {{ formatDate(e.started_at) }}
            </span>
          </li>
        </ul>
      </Card>
    </template>
  </div>
</template>
