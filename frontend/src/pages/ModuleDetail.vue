<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseSummary, type ModuleDetail } from '../lib/api'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Icon from '../components/ui/Icon.vue'
import Spinner from '../components/ui/Spinner.vue'
import StatTile from '../components/StatTile.vue'
import CaseRow from '../components/CaseRow.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const mid = computed(() => route.params.mid as string)

const detail = ref<ModuleDetail | null>(null)
const cases = ref<CaseSummary[]>([])
const loading = ref(true)
const error = ref('')

// Ajout d'un cas = fournir une SPEC (jamais une coquille vide).
const showForm = ref(false)
const specContent = ref('')
const newTitle = ref('')
const generating = ref(false)
const genError = ref('')
const genStatus = ref('')
let pollTimer: number | undefined

const stats = computed(() => {
  const by = (s: string) => cases.value.filter((c) => c.validation_status === s).length
  return { total: cases.value.length, validated: by('validated'),
           toReview: by('to_review'), never: by('never_executed') }
})

async function load() {
  try {
    const [d, c] = await Promise.all([api.getModule(mid.value), api.listCases(pid.value)])
    detail.value = d
    cases.value = c.filter((x) => x.module_id === Number(mid.value))
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
}

async function submitSpec() {
  if (!specContent.value.trim()) return
  generating.value = true
  genError.value = ''
  genStatus.value = 'Analyse de la spécification puis génération…'
  try {
    const job = await api.addCase(mid.value, specContent.value, newTitle.value)
    poll(job.job_id)
  } catch (e: any) {
    generating.value = false
    genError.value = e?.message || 'Ajout impossible'
  }
}

function poll(jobId: string) {
  pollTimer = window.setInterval(async () => {
    try {
      const job = await api.getGenerationJob(jobId)
      if (job.status === 'running') return
      stopPoll()
      generating.value = false
      if (job.status === 'done' && job.case_id) {
        showForm.value = false
        specContent.value = ''
        newTitle.value = ''
        await load()
        // Le cas est généré mais PAS encore relu : on emmène vers le gate.
        router.push(`/projects/${pid.value}/cases/${job.case_id}`)
      } else {
        genError.value = job.error || 'Génération échouée'
      }
    } catch {
      stopPoll()
      generating.value = false
      genError.value = 'Suivi de la génération interrompu'
    }
  }, 2000)
}
function stopPoll() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = undefined
}

onMounted(load)
onBeforeUnmount(stopPoll)
</script>

<template>
  <div class="space-y-8">
    <nav class="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
      <RouterLink to="/projects" class="hover:text-foreground">Projets</RouterLink>
      <template v-if="detail">
        <Icon name="chevron" class="h-3 w-3 opacity-40" />
        <RouterLink :to="`/projects/${pid}/cases`" class="hover:text-foreground">{{ detail.project.name }}</RouterLink>
        <Icon name="chevron" class="h-3 w-3 opacity-40" />
        <span class="text-foreground">{{ detail.module.name }}</span>
      </template>
    </nav>

    <div v-if="loading" class="flex items-center gap-2 text-sm text-muted-foreground">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>

    <template v-else-if="detail">
      <header class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 class="text-2xl font-semibold tracking-tight">{{ detail.module.name }}</h1>
          <p class="mt-1 text-sm text-muted-foreground">
            Cas de test du module — triés par priorité de lecture, puis par titre.
          </p>
        </div>
        <Button variant="primary" @click="showForm = !showForm">+ Ajouter un cas</Button>
      </header>

      <section class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatTile label="Cas de test" :value="stats.total" tone="primary" icon="dot" />
        <StatTile label="Validés" :value="stats.validated" tone="success" icon="check" />
        <StatTile label="À relire" :value="stats.toReview" tone="warning" icon="half" />
        <StatTile label="Non validés" :value="stats.never" tone="muted" icon="circle" />
      </section>

      <!-- Ajout : toujours à partir d'une SPÉCIFICATION -->
      <Card v-if="showForm" title="Ajouter un cas à partir d'une spécification">
        <form class="space-y-3" @submit.prevent="submitSpec">
          <p class="text-xs text-muted-foreground">
            Un cas naît toujours d'une spécification : elle est analysée, le Gherkin et les steps
            sont générés, puis la version passe en relecture avant toute exécution.
          </p>
          <input v-model="newTitle" placeholder="Titre du cas (ex. Retour matériel)"
                 class="h-9 w-full rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />
          <textarea v-model="specContent" rows="8" placeholder="Colle ici la spécification fonctionnelle…"
                    class="w-full rounded-md border border-border bg-surface-raised p-3 font-mono text-xs outline-none focus:border-primary/50" />
          <div class="flex items-center gap-3">
            <Button type="submit" variant="primary" :loading="generating" :disabled="!specContent.trim()">
              Analyser et générer
            </Button>
            <span v-if="generating" class="text-xs text-muted-foreground">{{ genStatus }}</span>
          </div>
          <p v-if="genError" class="text-xs text-destructive">{{ genError }}</p>
        </form>
      </Card>

      <section class="rounded-xl border border-border bg-card">
        <div class="flex items-center justify-between px-5 py-3 border-b border-border">
          <h2 class="text-sm font-semibold">Cas</h2>
          <span class="text-xs text-muted-foreground">{{ cases.length }} au total</span>
        </div>

        <div v-if="!cases.length" class="flex flex-col items-center gap-3 px-5 py-14 text-center">
          <div class="grid h-12 w-12 place-items-center rounded-full border border-border bg-surface text-muted-foreground">
            <Icon name="circle" class="h-5 w-5" />
          </div>
          <p class="text-sm text-muted-foreground">Aucun cas dans ce module.</p>
        </div>

        <ul v-else>
          <CaseRow v-for="c in cases" :key="c.id" :item="c" :project-id="pid" @changed="load" />
        </ul>
      </section>
    </template>
  </div>
</template>
