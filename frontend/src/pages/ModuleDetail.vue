<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseSummary, type ModuleDetail } from '../lib/api'
import { useProjectTree } from '../lib/useProjectTree'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Icon from '../components/ui/Icon.vue'
import Hint from '../components/ui/Hint.vue'
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
const tree = useProjectTree()   // pour que l'arbre suive l'ordre après un glissement

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

// ── Réorganisation manuelle (décision 0009) ──────────────────────────────────
// Ordre d'AFFICHAGE seulement : il n'ordonne PAS l'exécution (celle-ci suit l'ordre des
// scénarios du .feature). Drag HTML5 natif — la manipulation est simple (une liste, un niveau),
// une dépendance de drag & drop serait disproportionnée.
const dragIndex = ref<number | null>(null)
const overIndex = ref<number | null>(null)
const orderError = ref('')

function onDragStart(index: number, event: DragEvent) {
  dragIndex.value = index
  orderError.value = ''
  event.dataTransfer!.effectAllowed = 'move'
  // Firefox exige une donnée pour amorcer le glissement.
  event.dataTransfer!.setData('text/plain', String(index))
}

function onDragOver(index: number) {
  if (dragIndex.value !== null) overIndex.value = index
}

async function onDrop(index: number) {
  const from = dragIndex.value
  dragIndex.value = null
  overIndex.value = null
  if (from === null || from === index) return

  const avant = [...cases.value]            // pour revenir en arrière si le serveur refuse
  const reordonne = [...cases.value]
  const [deplace] = reordonne.splice(from, 1)
  reordonne.splice(index, 0, deplace)
  cases.value = reordonne                   // retour visuel immédiat

  try {
    // Le serveur RECALCULE les positions et renvoie la liste : on affiche sa vérité, pas la
    // nôtre — sinon l'écran pourrait diverger de la base (« affiché ≠ réel »).
    cases.value = await api.reorderCases(mid.value, reordonne.map((c) => c.id))
    // L'arbre honore le même ordre : sans ce rafraîchissement, il garderait l'ancien tant qu'on
    // ne change pas de route — deux vues de la même page se contrediraient à l'écran.
    tree.load(pid.value, { silent: true })
  } catch (e: any) {
    cases.value = avant
    orderError.value = e?.message || 'Réorganisation impossible'
  }
}

function onDragEnd() {
  dragIndex.value = null
  overIndex.value = null
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
            Cas de test du module — dans l'ordre de lecture que vous avez défini.
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
          <h2 class="inline-flex items-center gap-1.5 text-sm font-semibold">
            Cas
            <!-- L'infobulle DIT que l'ordre ne pilote rien — même patron que la priorité (0006).
                 Un tri manuel muet laisserait croire qu'il ordonne l'exécution. -->
            <Hint text="Ordre de lecture : glissez les cas par la poignée pour les réorganiser. Il n'ordonne PAS l'exécution — celle-ci suit l'ordre des scénarios dans le .feature." />
          </h2>
          <span class="text-xs text-muted-foreground">{{ cases.length }} au total</span>
        </div>

        <p v-if="orderError" class="border-b border-border px-5 py-2 text-xs text-destructive">
          {{ orderError }}
        </p>

        <div v-if="!cases.length" class="flex flex-col items-center gap-3 px-5 py-14 text-center">
          <div class="grid h-12 w-12 place-items-center rounded-full border border-border bg-surface text-muted-foreground">
            <Icon name="circle" class="h-5 w-5" />
          </div>
          <p class="text-sm text-muted-foreground">Aucun cas dans ce module.</p>
        </div>

        <ul v-else>
          <li
            v-for="(c, i) in cases" :key="c.id"
            class="flex items-stretch transition-colors"
            :class="[dragIndex === i && 'opacity-40',
                     overIndex === i && dragIndex !== i && 'bg-primary/10 shadow-[inset_0_2px_0_0_hsl(var(--primary))]']"
            @dragover.prevent="onDragOver(i)"
            @drop.prevent="onDrop(i)"
          >
            <!-- Poignée : seule la poignée est draggable, pas la ligne entière — sinon on
                 déclencherait un glissement en voulant simplement déplier ou cliquer le cas. -->
            <span
              draggable="true" title="Glisser pour réorganiser (ordre de lecture)"
              class="flex w-7 shrink-0 cursor-grab items-center justify-center text-muted-foreground/25 transition-colors hover:text-muted-foreground active:cursor-grabbing"
              @dragstart="onDragStart(i, $event)" @dragend="onDragEnd"
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <circle cx="9" cy="6" r="1.6" /><circle cx="15" cy="6" r="1.6" />
                <circle cx="9" cy="12" r="1.6" /><circle cx="15" cy="12" r="1.6" />
                <circle cx="9" cy="18" r="1.6" /><circle cx="15" cy="18" r="1.6" />
              </svg>
            </span>
            <CaseRow :item="c" :project-id="pid" class="min-w-0 flex-1" @changed="load" />
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>
