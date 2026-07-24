<script setup lang="ts">
// Détail d'un RUN (campagne, décision 0022 n°8) — ses cas et leur résultat DANS CE run.
//
// ⚠️ Ce que cette page montrait avant : une `execution` mono-cas et ses scénarios. Le modèle a
// changé — un run REGROUPE des cas. Le rapport détaillé d'un cas reste accessible en cliquant sa
// ligne (il pointe vers l'exécution qui l'a produit).
//
// Le statut d'un cas est DÉRIVÉ des deux axes réels (Passed/Failed/Retest/Blocked/Untested) :
// jamais un badge unique qui masque l'un des deux (§4.1). Un cas sans exécution dans ce run est
// « Untested » — on ne fabrique aucun résultat.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type RunDetail as RunDetailDto, type RunCaseResult } from '../lib/api'
import { testStatusCode, testStatusMeta, TEST_STATUS_ORDER, type TestStatusCode } from '../lib/status'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const runId = computed(() => Number(route.params.id))

const detail = ref<RunDetailDto | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true; error.value = ''
  try { detail.value = await api.getRun(runId.value) }
  catch { error.value = 'Impossible de charger cette exécution.' }
  finally { loading.value = false }
}
onMounted(load)
watch(runId, load)

function statusOf(c: RunCaseResult): TestStatusCode {
  return testStatusCode(c.execution_status, c.functional_status)
}

// Répartition RÉELLE des cas du run par statut dérivé.
const dist = computed<Record<TestStatusCode, number>>(() => {
  const d = { passed: 0, failed: 0, retest: 0, blocked: 0, untested: 0 }
  for (const c of detail.value?.cases || []) d[statusOf(c)]++
  return d
})
const total = computed(() => detail.value?.cases.length || 0)
const tested = computed(() => total.value - dist.value.untested)
const pct = computed(() => (total.value ? Math.round((tested.value / total.value) * 100) : 0))

const STATUS_RUN: Record<string, { label: string; cls: string }> = {
  draft: { label: 'Brouillon', cls: 'bg-secondary text-muted-foreground' },
  running: { label: 'En cours', cls: 'bg-warning/15 text-warning' },
  completed: { label: 'Terminé', cls: 'bg-success/15 text-success' },
}

// ── Lancement de la campagne ─────────────────────────────────────────────────
// Geste EXPLICITE (0022 8.c.1). Les cas sont joués en séquence côté serveur ; on rafraîchit
// périodiquement pour voir les résultats tomber un par un, jusqu'à la clôture du run.
const launching = ref(false)
const launchError = ref('')
// Le CODE de l'erreur, pas sa phrase (contrat RFC 9457, lot B). C'est lui qui décide si l'écran
// peut proposer une action de réparation — brancher sur le texte français casserait à la
// première reformulation du message, sans que personne le voie venir.
const launchErrorCode = ref('')
let pollTimer: number | undefined

const enCours = computed(() => detail.value?.run.status === 'running')

async function launch() {
  launchError.value = ''
  launching.value = true
  try {
    await api.launchRun(runId.value)
    await load()
    poll()
  } catch (e: any) {
    launchError.value = e?.message || 'Lancement impossible.'
    launchErrorCode.value = e?.code || ''
  } finally {
    launching.value = false
  }
}

function poll() {
  stopPoll()
  pollTimer = window.setInterval(async () => {
    try {
      const d = await api.getRun(runId.value)
      detail.value = d
      if (d.run.status !== 'running') stopPoll()   // campagne close
    } catch { stopPoll() }
  }, 4000)
}
function stopPoll() {
  if (pollTimer) window.clearInterval(pollTimer)
  pollTimer = undefined
}
// Si on ouvre une campagne déjà en cours, on suit son avancement sans avoir à la relancer.
watch(enCours, (v) => { if (v) poll(); else stopPoll() })
onBeforeUnmount(stopPoll)

// ── Archivage : clore = LECTURE SEULE (réversible, rien n'est effacé) ────────
const archived = computed(() => !!detail.value?.run.is_archived)
async function toggleArchive() {
  try {
    await api.archiveRun(runId.value, !archived.value)
    await load()
  } catch (e: any) {
    launchError.value = e?.message || 'Opération impossible.'
  }
}

// Cliquer un cas : vers son RAPPORT s'il a été exécuté ici, sinon vers le cas lui-même.
function openCase(c: RunCaseResult) {
  if (c.execution_id) {
    router.push({ name: 'report', params: { pid: pid.value, id: String(c.execution_id) } })
  } else {
    router.push({ name: 'case-detail', params: { pid: pid.value, id: String(c.id) } })
  }
}
function backToList() { router.push({ name: 'executions', params: { pid: pid.value } }) }
</script>

<template>
  <div v-if="loading" class="space-y-3">
    <div class="h-8 w-64 rounded bg-secondary animate-pulse"></div>
    <div class="h-32 rounded bg-secondary animate-pulse"></div>
  </div>

  <div v-else-if="error" class="text-center py-10">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <button class="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:border-primary/40" @click="load">Réessayer</button>
  </div>

  <div v-else-if="detail">
    <!-- En-tête -->
    <div class="flex items-center gap-3 flex-wrap">
      <span class="rounded-full bg-[hsl(262_52%_55%)] text-white text-sm font-semibold px-3 py-1 tabular-nums">R{{ detail.run.id }}</span>
      <h1 class="text-2xl font-semibold tracking-tight truncate">{{ detail.run.name }}</h1>
      <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold"
            :class="(STATUS_RUN[detail.run.status] || STATUS_RUN.draft).cls">
        {{ (STATUS_RUN[detail.run.status] || STATUS_RUN.draft).label }}
      </span>

      <div class="ml-auto flex items-center gap-2">
        <!-- Lancer : geste EXPLICITE. Masqué si la campagne est archivée (lecture seule). -->
        <button v-if="!enCours && !archived"
                class="rounded-md bg-success text-white font-semibold px-4 py-2 text-sm flex items-center gap-2 hover:bg-success/90 disabled:opacity-50"
                :disabled="launching || !total" @click="launch">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          {{ launching ? 'Lancement…' : (detail.run.status === 'completed' ? 'Relancer' : 'Lancer l\'exécution') }}
        </button>
        <span v-if="enCours" class="flex items-center gap-2 text-sm text-warning">
          <span class="inline-block h-3.5 w-3.5 rounded-full border-2 border-warning border-t-transparent animate-spin"></span>
          Exécution en cours — {{ tested }} / {{ total }} cas
        </span>
        <!-- Clore / rouvrir. Réversible : une clôture par erreur ne doit pas être irrattrapable. -->
        <button v-if="!enCours" class="rounded-md border border-border px-3 py-2 text-sm hover:border-primary/40"
                @click="toggleArchive">
          {{ archived ? 'Rouvrir' : 'Clôturer' }}
        </button>
      </div>
    </div>

    <!-- Bandeau « archivée » : dit pourquoi il n'y a plus de bouton Lancer (note fonctionnelle). -->
    <div v-if="archived" class="mt-3 flex items-start gap-2 rounded-lg border-l-4 border-muted-foreground/40 bg-secondary/50 px-4 py-3 text-sm text-muted-foreground">
      <svg class="w-4 h-4 mt-0.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="4" rx="1"/><path d="M5 8v11a1 1 0 001 1h12a1 1 0 001-1V8M10 12h4"/></svg>
      <span>
        Exécution <strong class="text-foreground">archivée</strong> : ses résultats sont figés et
        elle ne peut plus être relancée. Rien n'a été supprimé — « Rouvrir » la rend à nouveau modifiable.
      </span>
    </div>
    <p v-if="launchError" class="mt-2 text-sm text-destructive">
      {{ launchError }}
      <!-- Une connexion incomplète se CORRIGE : on emmène là où on la corrige, plutôt que de
           laisser l'utilisateur chercher l'écran. Décidé sur le code, jamais sur la phrase. -->
      <RouterLink v-if="launchErrorCode === 'connexion_incomplete'" to="/projects"
                  class="ml-1 underline hover:text-foreground">Corriger la connexion du projet</RouterLink>
    </p>
    <p v-if="enCours" class="mt-1 text-xs text-muted-foreground">
      Les cas sont joués l'un après l'autre contre l'application réelle — les résultats
      apparaissent au fur et à mesure.
    </p>
    <button class="mt-1 text-primary/90 text-sm hover:underline" @click="backToList">Exécutions et résultats de test</button>

    <p v-if="detail.description" class="mt-3 text-sm text-foreground/85 whitespace-pre-wrap">{{ detail.description }}</p>
    <p v-if="detail.refs" class="mt-1 text-xs text-muted-foreground">Références : {{ detail.refs }}</p>

    <!-- CONTRE QUOI cette campagne a tourné — lu sur ses exécutions, jamais sur la connexion
         actuelle du projet (elle a pu changer depuis). Des résultats sans leur cible ne prouvent
         rien, et sur un serveur partagé plusieurs instances coexistent. -->
    <p v-if="detail.target_url" class="mt-1 text-xs text-muted-foreground">
      Testé contre <span class="text-foreground/90">{{ detail.target_url }}</span>
      <template v-if="detail.target_database"> · base <span class="text-foreground/90">{{ detail.target_database }}</span></template>
    </p>
    <!-- Deux cibles dans une même campagne = la connexion a bougé en cours de route : ses
         résultats ne sont plus comparables entre eux. On le dit, on n'en choisit pas une. -->
    <p v-if="detail.target_mixed" class="mt-1 text-xs text-warning">
      ⚠️ Cette campagne a tourné contre <strong>plusieurs applications différentes</strong> : la
      connexion du projet a changé pendant son déroulement. Ses résultats ne sont pas comparables
      entre eux.
    </p>

    <!-- Avancement -->
    <div class="mt-6 flex flex-wrap items-center gap-6 rounded-lg border border-border bg-surface/60 p-4">
      <div>
        <div class="text-3xl font-semibold tabular-nums">{{ pct }} %</div>
        <div class="text-xs text-muted-foreground mt-0.5">{{ tested }} / {{ total }} cas testés</div>
      </div>
      <div class="flex-1 min-w-[200px]">
        <div class="h-2 rounded-full bg-border overflow-hidden flex">
          <div v-for="k in TEST_STATUS_ORDER" :key="k" class="h-full"
               :style="{ width: (total ? (dist[k] / total) * 100 : 0) + '%',
                         background: testStatusMeta(k).color }"></div>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted-foreground">
          <span v-for="k in TEST_STATUS_ORDER" :key="k" class="flex items-center gap-1.5">
            <span class="h-2.5 w-2.5 rounded-sm" :style="{ background: testStatusMeta(k).color }"></span>
            {{ testStatusMeta(k).label }} : {{ dist[k] }}
          </span>
        </div>
      </div>
    </div>

    <!-- Les cas du run -->
    <h2 class="mt-8 font-semibold pb-2 border-b border-border">
      Cas de test <span class="text-muted-foreground font-normal">({{ total }})</span>
    </h2>
    <p v-if="!total" class="mt-3 text-sm text-muted-foreground">
      Cette exécution ne contient aucun cas.
    </p>
    <table v-else class="w-full border-collapse mt-1">
      <tbody>
        <tr v-for="c in detail.cases" :key="c.id"
            class="group border-b border-border/40 hover:bg-accent/30 cursor-pointer"
            @click="openCase(c)">
          <td class="py-3 pl-1 w-16 font-bold tabular-nums whitespace-nowrap text-muted-foreground">C{{ c.id }}</td>
          <td class="py-3 px-2.5 text-primary group-hover:underline leading-snug">{{ c.title }}</td>
          <td class="py-3 px-2.5 w-44 text-right">
            <span class="inline-flex items-center rounded-full px-2.5 py-1 text-[12.5px] font-semibold"
                  :class="testStatusMeta(statusOf(c)).badge">
              {{ testStatusMeta(statusOf(c)).label }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>

  <div v-else class="text-sm text-muted-foreground">Exécution introuvable.</div>
</template>
