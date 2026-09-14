<script setup lang="ts">
// Détail d'un RUN (campagne, décision 0022 n°8) — ses cas et leur résultat DANS CE run.
//
// ⚠️ Ce que cette page montrait avant : une `execution` mono-cas et ses scénarios. Le modèle a
// changé — un run REGROUPE des cas. Le rapport détaillé d'un cas reste accessible en cliquant sa
// ligne (il pointe vers l'exécution qui l'a produit).
//
// Le statut d'un cas est DÉRIVÉ des deux axes réels (Passed/Failed/Retest/Blocked/Untested) :
// jamais un badge unique qui masque l'un des deux (§4.1). Un cas sans résultat dans ce run est
// « Untested » — on ne fabrique aucun résultat.
//
// ⚠️ **Chaque ligne dit COMMENT son résultat a été obtenu** (2026-08-04) : joué par la machine,
// ou joué à la main. Sans cette colonne, ouvrir l'exécution manuelle transformerait cet écran en
// ce que le produit refuse d'être — un tableau de cases cochées dont personne ne peut dire ce qui
// a réellement tourné.
//
// ⚠️ **Le MODE de la campagne décide des gestes offerts.** Automatique → un bouton « Lancer » et
// aucune saisie. Manuelle → aucun bouton « Lancer » et un « + Résultat » par ligne. Les deux à la
// fois, c'était l'écran d'avant : deux gestes proposés, aucun qui s'impose, et un utilisateur qui
// choisit au hasard. Le serveur refuse de son côté — l'écran n'est pas le gardien de la règle,
// seulement son porte-parole.
//
// ⚠️ **La vue « Tests & Résultats », à parité TestRail** (2026-08-05) : deux cartes de synthèse
// (camembert + taux de réussite), puis les cas GROUPÉS PAR STATUT. Ce qu'elle remplace : une
// barre empilée surmontée d'un « % » qui comptait les cas AYANT TOURNÉ. Ce chiffre se lisait
// comme un taux de réussite, alors qu'une campagne intégralement rouge l'aurait affiché à 100 %.
// Le camembert et les groupes descendent tous deux de `TEST_STATUS_ORDER` : la liste des statuts,
// leur ordre et leurs couleurs ne sont écrits qu'à un seul endroit, `lib/status.ts`.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  api, roleSuffisant, type RunDetail as RunDetailDto, type RunCaseResult, type PlanOut,
  type ProjectMember,
} from '../lib/api'
import { useProjects } from '../lib/useProjects'
import { useSession } from '../lib/useSession'
import { libelleActeur, testStatusMeta, TEST_STATUS_ORDER, type TestStatusCode } from '../lib/status'
import ResultMode from '../components/ResultMode.vue'
import AddResultDialog from '../components/AddResultDialog.vue'
import RefsList from '../components/RefsList.vue'
import Button from '../components/ui/Button.vue'
import IconButton from '../components/ui/IconButton.vue'
import Modal from '../components/ui/Modal.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const runId = computed(() => Number(route.params.id))
const { session } = useSession()
const { projectById } = useProjects()
const roleProjet = computed(() => projectById(pid.value)?.effective_role || session.value?.role || '')
const peutModifier = computed(() => roleSuffisant(roleProjet.value, 'testeur'))

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

// ── Plan de test (migration 43) — purement organisationnel : rattacher/retirer ne touche à
// RIEN de l'exécution. `plan_id` est une référence SOUPLE (pas de FK dure côté serveur), donc le
// nom du plan actuel se lit dans la petite liste des plans du projet plutôt que sur le run lui-même.
const showPlanPicker = ref(false)
const plansDuProjet = ref<PlanOut[]>([])
const planActuel = computed(() =>
  plansDuProjet.value.find((p) => p.id === detail.value?.run.plan_id) || null)
async function chargerPlans() {
  try { plansDuProjet.value = await api.listPlans(pid.value) } catch { plansDuProjet.value = [] }
}
onMounted(chargerPlans)

// ── « Assigné à » : qui SUPERVISE ce cas DANS cette campagne (2026-09-14) ────────────────────
// ⚠️ La table `run_case_assignment` existait depuis la migration 25 (2026-08-04) sans jamais
// être alimentée — inspiré de TestRail. Choisi parmi les membres RÉELS du projet (jamais tapé
// à la main), et ça marche pour une campagne automatique COMME manuelle : superviser un résultat
// de machine est le même geste humain que jouer un cas à la main.
const membresDuProjet = ref<ProjectMember[]>([])
async function chargerMembres() {
  try { membresDuProjet.value = await api.listProjectMembers(pid.value) }
  catch { membresDuProjet.value = [] }
}
onMounted(chargerMembres)

// Un cas peut rester assigné à quelqu'un qui a depuis quitté le projet (le champ reste du texte
// libre — voir `AssignmentRepo`, back-end) : on l'ajoute quand même à la liste plutôt que de le
// faire disparaître silencieusement du sélecteur d'un nom qui, lui, n'a pas disparu de la base.
function optionsAssignation(assignedTo: string): ProjectMember[] {
  if (!assignedTo || membresDuProjet.value.some((m) => m.username === assignedTo)) {
    return membresDuProjet.value
  }
  return [...membresDuProjet.value,
          { user_id: -1, username: assignedTo, email: '', role: '', status: 'removed', created_at: '' }]
}

const assignationEnCours = ref<number | null>(null)
async function assignerCas(caseId: number, assignedTo: string) {
  if (!detail.value) return
  assignationEnCours.value = caseId
  // Optimiste : l'écran reflète le choix tout de suite, sans attendre le rechargement complet —
  // une confirmation instantanée compte plus ici qu'une source de vérité à la milliseconde près.
  const cas = detail.value.cases.find((c) => c.id === caseId)
  const avant = cas?.assigned_to ?? ''
  if (cas) cas.assigned_to = assignedTo
  try {
    await api.setAssignment(runId.value, caseId, assignedTo)
  } catch (e: any) {
    if (cas) cas.assigned_to = avant  // échec : on revient à ce qui était vraiment enregistré
    window.alert(e?.message || 'Assignation impossible.')
  } finally {
    assignationEnCours.value = null
  }
}
function ouvrirPlanPicker() {
  showPlanPicker.value = true
  chargerPlans()
}
async function assignerAuPlan(planId: number) {
  if (!detail.value) return
  try {
    await api.assignRunToPlan(planId, detail.value.run.id)
    showPlanPicker.value = false
    await load()
  } catch (e: any) {
    window.alert(e?.message || 'Assignation impossible.')
  }
}
async function retirerDuPlan() {
  if (!detail.value || !planActuel.value) return
  try {
    await api.unassignRunFromPlan(planActuel.value.id, detail.value.run.id)
    await load()
  } catch (e: any) {
    window.alert(e?.message || 'Retrait impossible.')
  }
}

function statusOf(c: RunCaseResult): TestStatusCode { return c.statut as TestStatusCode }

// Répartition RÉELLE des cas du run par statut dérivé.
const dist = computed<Record<TestStatusCode, number>>(() => {
  const d = { passed: 0, failed: 0, retest: 0, blocked: 0, untested: 0 }
  for (const c of detail.value?.cases || []) d[statusOf(c)]++
  return d
})
const total = computed(() => detail.value?.cases.length || 0)
const tested = computed(() => total.value - dist.value.untested)

// ── Ce que la campagne VAUT, en deux chiffres qui ne se recouvrent pas ────────
// « réussi » = la part des cas VERTS sur le total, pas la part de ceux qui ont tourné. Un run où
// 8 cas sur 10 sont encore à jouer n'est pas « 20 % avancé » : il est réussi à 20 %, et 80 % de
// son périmètre n'a rien prouvé du tout. Les deux phrases sont dites côte à côte pour que l'une
// ne puisse jamais être lue à la place de l'autre.
function part(n: number) { return total.value ? Math.round((n / total.value) * 100) : 0 }
const pctReussi = computed(() => part(dist.value.passed))
const pctNonTestes = computed(() => part(dist.value.untested))

// ── Le camembert, à la main ──────────────────────────────────────────────────
// Un `<path>` par statut, aucune librairie de graphiques (le projet n'en embarque pas). Les
// couleurs et les libellés viennent de `status.ts` : ni l'ordre ni la palette ne sont retapés ici.
const R = 54, CX = 60, CY = 60
function pointSur(deg: number): [number, number] {
  const a = ((deg - 90) * Math.PI) / 180
  return [CX + R * Math.cos(a), CY + R * Math.sin(a)]
}
function arc(a0: number, a1: number): string {
  const [x0, y0] = pointSur(a0)
  const [x1, y1] = pointSur(a1)
  const grandArc = a1 - a0 > 180 ? 1 : 0
  return `M ${CX} ${CY} L ${x0.toFixed(2)} ${y0.toFixed(2)} `
       + `A ${R} ${R} 0 ${grandArc} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`
}
// ⚠️ Un statut à 100 % ne se dessine PAS en arc : son point de départ et son point d'arrivée sont
// confondus, et le navigateur rend un disque vide. On rend alors un cercle plein — sinon le seul
// cas où la campagne est unanime est justement celui où le graphique disparaît.
const parts = computed(() => {
  const out: { code: TestStatusCode; d: string; plein: boolean }[] = []
  let a0 = 0
  for (const k of TEST_STATUS_ORDER) {
    const n = dist.value[k]
    if (!n) continue
    const a1 = a0 + (n / total.value) * 360
    out.push({ code: k, d: arc(a0, a1), plein: n === total.value })
    a0 = a1
  }
  return out
})
// Le graphique est une IMAGE pour un lecteur d'écran : sans ce résumé, il ne dit rien du tout.
const resumeCamembert = computed(() =>
  'Répartition des statuts : '
  + TEST_STATUS_ORDER.map((k) => `${dist.value[k]} ${testStatusMeta(k).label}`).join(', '))

// Les deux téléchargements du coin, comme TestRail : l'image du graphique, et ses données.
const svgEl = ref<SVGSVGElement | null>(null)
function telecharger(contenu: BlobPart, type: string, nom: string) {
  const url = URL.createObjectURL(new Blob([contenu], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = nom
  a.click()
  URL.revokeObjectURL(url)
}
function exporterImage() {
  if (!svgEl.value) return
  telecharger(new XMLSerializer().serializeToString(svgEl.value),
              'image/svg+xml;charset=utf-8', `campagne-${runId.value}-repartition.svg`)
}
function exporterCsv() {
  const lignes = TEST_STATUS_ORDER.map(
    (k) => [testStatusMeta(k).label, dist.value[k], `${part(dist.value[k])} %`].join(';'))
  // BOM UTF-8 : sans lui, Excel lit « é » de travers.
  const contenu = '﻿' + ['Statut;Cas;Part', ...lignes].join('\r\n')
  telecharger(contenu, 'text/csv;charset=utf-8', `campagne-${runId.value}-repartition.csv`)
}

// ── Tri, filtre, colonnes : des préférences de LECTURE, rien d'autre ──────────
// Aucune règle métier ne naît ici : on ne fait que réordonner et masquer ce que le serveur a
// déjà tranché. Le statut d'une ligne reste `c.statut`, jamais recalculé à l'écran (§3.6).
const tri = ref<'statut' | 'id' | 'titre'>('statut')
const triAsc = ref(true)
const filtreStatut = ref('')          // '' = aucun filtre
const menuColonnes = ref(false)
// Ni le titre ni le statut ne se masquent : un tableau de cas sans eux ne montre plus rien.
const COLONNES_MASQUABLES = [
  { cle: 'assigne', label: 'Assigné à' },
  { cle: 'mode', label: 'Mode' },
  { cle: 'soumis', label: 'Soumis par' },
] as const
type Colonne = typeof COLONNES_MASQUABLES[number]['cle']
const colonnes = ref<Colonne[]>(['assigne', 'mode', 'soumis'])
function colonneVisible(c: Colonne) { return colonnes.value.includes(c) }
function basculerColonne(c: Colonne) {
  colonnes.value = colonneVisible(c) ? colonnes.value.filter((x) => x !== c) : [...colonnes.value, c]
}
const triParDefaut = computed(() => tri.value === 'statut' && triAsc.value && !filtreStatut.value)
function reinitialiserTri() { tri.value = 'statut'; triAsc.value = true; filtreStatut.value = '' }

const casVisibles = computed(() => {
  const l = (detail.value?.cases || []).filter((c) => !filtreStatut.value || c.statut === filtreStatut.value)
  const s = [...l]
  if (tri.value === 'titre') s.sort((a, b) => a.title.localeCompare(b.title))
  else if (tri.value === 'id') s.sort((a, b) => a.id - b.id)
  else s.sort((a, b) => TEST_STATUS_ORDER.indexOf(statusOf(a)) - TEST_STATUS_ORDER.indexOf(statusOf(b)))
  if (!triAsc.value) s.reverse()
  return s
})

// ⚠️ **Un groupe n'existe que s'il a des cas.** Dérouler cinq bandeaux dont trois sont vides
// ferait passer pour « une campagne qui a du Blocked » une campagne qui n'en a aucun : le lecteur
// retient les intitulés, pas les zéros. Hors tri par statut, une seule liste, sans bandeau.
const groupes = computed(() => {
  if (tri.value !== 'statut') return [{ code: null as TestStatusCode | null, cases: casVisibles.value }]
  const ordre = triAsc.value ? TEST_STATUS_ORDER : [...TEST_STATUS_ORDER].reverse()
  return ordre
    .map((code) => ({ code, cases: casVisibles.value.filter((c) => statusOf(c) === code) }))
    .filter((g) => g.cases.length > 0)
})

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
// Le MODE D'EXÉCUTION de la campagne, choisi à sa création. Il commande quels gestes existent
// sur cet écran : une campagne automatique se LANCE, une campagne manuelle se SAISIT.
const estManuelle = computed(() => detail.value?.run.mode === 'manuelle')

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

// Cliquer un cas : vers CE CAS DANS CETTE CAMPAGNE (le « test », 2026-08-05).
//
// ⚠️ Avant, le clic menait au rapport technique de l'exécution — ou, faute d'exécution, à la fiche
// du cas dans le référentiel. Deux destinations pour le même geste, et aucune qui répondait à la
// question posée en cliquant : « où en est ce cas, ICI ? ». Le rapport détaillé et la fiche du cas
// restent atteignables DEPUIS cette page, nommés pour ce qu'ils sont.
function openCase(c: RunCaseResult) {
  router.push({ name: 'run-test',
                params: { pid: pid.value, id: String(runId.value), caseId: String(c.id) } })
}
function backToList() { router.push({ name: 'executions', params: { pid: pid.value } }) }

// ── Exécution MANUELLE d'un cas (le geste « Add Result » de TestRail) ────────
// ⚠️ **Refusée sur une campagne archivée, et absente d'une campagne automatique** — le bouton
// disparaît alors, plutôt que d'échouer au clic : une action proposée doit être une action
// possible. Le serveur refuse de son côté, l'écran n'est pas le gardien de la règle, seulement
// son porte-parole.
const casSaisi = ref<RunCaseResult | null>(null)
function ouvrirSaisie(c: RunCaseResult) { casSaisi.value = c }
async function resultatAjoute() {
  casSaisi.value = null
  await load()
}
</script>

<template>
  <div v-if="loading" class="space-y-3">
    <div class="h-8 w-64 rounded bg-secondary animate-pulse"></div>
    <div class="h-32 rounded bg-secondary animate-pulse"></div>
  </div>

  <div v-else-if="error" class="text-center py-10">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <Button variant="secondary" class="mt-3" @click="load">Réessayer</Button>
  </div>

  <div v-else-if="detail">
    <!-- En-tête -->
    <div class="flex items-center gap-3 flex-wrap">
      <span class="rounded-full bg-accent-id text-accent-id-foreground text-sm font-semibold px-3 py-1 tabular-nums">R{{ detail.run.id }}</span>
      <h1 class="text-2xl font-semibold tracking-tight truncate">{{ detail.run.name }}</h1>
      <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold"
            :class="(STATUS_RUN[detail.run.status] || STATUS_RUN.draft).cls">
        {{ (STATUS_RUN[detail.run.status] || STATUS_RUN.draft).label }}
      </span>

      <div class="ml-auto flex items-center gap-2">
        <!-- Lancer : geste EXPLICITE. Masqué si la campagne est archivée (lecture seule) — et
             ABSENT d'une campagne manuelle, qui n'a rien à lancer : ses résultats se saisissent. -->
        <Button v-if="peutModifier && !enCours && !archived && !estManuelle" variant="success"
                :disabled="launching || !total" @click="launch">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
          {{ launching ? 'Lancement…' : (detail.run.status === 'completed' ? 'Relancer' : 'Lancer l\'exécution') }}
        </Button>
        <span v-if="enCours" class="flex items-center gap-2 text-sm text-warning">
          <span class="inline-block h-3.5 w-3.5 rounded-full border-2 border-warning border-t-transparent animate-spin"></span>
          Exécution en cours — {{ tested }} / {{ total }} cas
        </span>
        <!-- Clore / rouvrir. Réversible : une clôture par erreur ne doit pas être irrattrapable. -->
        <Button v-if="peutModifier && !enCours" variant="secondary" @click="toggleArchive">
          {{ archived ? 'Rouvrir' : 'Clôturer' }}
        </Button>
      </div>
    </div>

    <!-- Plan de test (migration 43) : purement organisationnel, n'agit sur rien ci-dessus. -->
    <div class="mt-2 flex items-center gap-2 text-sm">
      <template v-if="planActuel">
        <span class="text-muted-foreground">Dans le plan :</span>
        <RouterLink :to="{ name: 'plan-detail', params: { pid, id: String(planActuel.id) } }"
                    class="text-primary hover:underline">{{ planActuel.name }}</RouterLink>
        <button v-if="peutModifier" type="button" class="text-xs text-muted-foreground hover:text-destructive"
                @click="retirerDuPlan">Retirer</button>
      </template>
      <button v-else-if="peutModifier" type="button"
              class="text-xs text-muted-foreground hover:text-foreground underline decoration-dotted"
              @click="ouvrirPlanPicker">
        + Ajouter à un plan de test
      </button>
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
    <button class="mt-1 text-primary text-sm hover:underline" @click="backToList">Exécutions et résultats de test</button>

    <p v-if="detail.description" class="mt-3 text-sm text-foreground whitespace-pre-wrap">{{ detail.description }}</p>
    <p v-if="detail.refs" class="mt-1 text-xs text-muted-foreground">Références : <RefsList :refs="detail.refs" /></p>

    <!-- CONTRE QUOI cette campagne a tourné — lu sur ses exécutions, jamais sur la connexion
         actuelle du projet (elle a pu changer depuis). Des résultats sans leur cible ne prouvent
         rien, et sur un serveur partagé plusieurs instances coexistent. -->
    <p v-if="detail.target_url" class="mt-1 text-xs text-muted-foreground">
      Testé contre <span class="text-foreground">{{ detail.target_url }}</span>
      <template v-if="detail.target_database"> · base <span class="text-foreground">{{ detail.target_database }}</span></template>
    </p>
    <!-- Deux cibles dans une même campagne = la connexion a bougé en cours de route : ses
         résultats ne sont plus comparables entre eux. On le dit, on n'en choisit pas une. -->
    <p v-if="detail.target_mixed" class="mt-1 text-xs text-warning">
      ⚠️ Cette campagne a tourné contre <strong>plusieurs applications différentes</strong> : la
      connexion du projet a changé pendant son déroulement. Ses résultats ne sont pas comparables
      entre eux.
    </p>

    <!-- Avancement : DEUX cartes côte à côte (parité TestRail) — la répartition à gauche, ce que
         la campagne vaut à droite. Une seule barre empilée mélangeait les deux lectures. -->
    <div class="mt-6 grid gap-4 lg:grid-cols-[1.7fr_1fr]">
      <!-- Camembert + sa légende -->
      <div class="relative rounded-lg border border-border bg-surface/60 p-4 flex items-center gap-6">
        <div class="absolute right-3 top-3 flex gap-1">
          <IconButton size="sm" label="Télécharger le graphique (image SVG)" @click="exporterImage">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/>
            </svg>
          </IconButton>
          <IconButton size="sm" label="Télécharger les données de la répartition (CSV)" @click="exporterCsv">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/>
            </svg>
          </IconButton>
        </div>

        <svg ref="svgEl" viewBox="0 0 120 120" class="w-32 h-32 shrink-0"
             xmlns="http://www.w3.org/2000/svg" role="img" :aria-label="resumeCamembert">
          <circle v-if="!total" :cx="CX" :cy="CY" :r="R" fill="hsl(var(--border))" opacity="0.4" />
          <template v-for="p in parts" :key="p.code">
            <circle v-if="p.plein" :cx="CX" :cy="CY" :r="R" :fill="`hsl(${testStatusMeta(p.code).color})`" />
            <path v-else :d="p.d" :fill="`hsl(${testStatusMeta(p.code).color})`" />
          </template>
        </svg>

        <!-- ⚠️ La légende ITÈRE `TEST_STATUS_ORDER` : ni la liste des statuts, ni leur ordre, ni
             leurs couleurs ne sont retapés ici. Le libellé est TOUJOURS écrit à côté de sa
             pastille — jamais la couleur seule. -->
        <ul class="flex-1 min-w-0 space-y-2">
          <li v-for="k in TEST_STATUS_ORDER" :key="k">
            <div class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 rounded-full shrink-0"
                    :style="{ background: `hsl(${testStatusMeta(k).color})` }"></span>
              <span class="font-semibold tabular-nums">{{ dist[k] }}</span>
              <span class="font-semibold">{{ testStatusMeta(k).label }}</span>
            </div>
            <p class="pl-[18px] ml-0.5 text-xs text-muted-foreground">
              {{ part(dist[k]) }} % défini sur {{ testStatusMeta(k).label }}
            </p>
          </li>
        </ul>
      </div>

      <!-- Ce que la campagne vaut : le taux de RÉUSSITE, et ce qui n'a rien prouvé. -->
      <div class="rounded-lg border border-border bg-surface/60 p-4 grid place-items-center text-center">
        <div>
          <div class="text-5xl font-bold tabular-nums">{{ pctReussi }} %</div>
          <div class="text-sm text-muted-foreground mt-1">réussi</div>
          <p class="mt-3 text-xs text-muted-foreground">
            {{ dist.untested }} / {{ total }} non testés ({{ pctNonTestes }} %).
          </p>
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

    <template v-else>
      <!-- Barre d'outils — TRI, FILTRE, COLONNES. Préférences de lecture uniquement. -->
      <div class="flex items-center gap-4 border-b border-border bg-surface-raised/50 px-3 py-2 text-xs text-muted-foreground">
        <label class="flex items-center gap-1.5">Trier :
          <select v-model="tri" aria-label="Trier les cas"
                  class="cursor-pointer border-b border-dotted border-muted-foreground bg-transparent text-foreground outline-none">
            <option value="statut">Statut</option>
            <option value="id">ID</option>
            <option value="titre">Titre</option>
          </select>
        </label>
        <button class="hover:text-foreground" :aria-label="triAsc ? 'Trier en ordre décroissant' : 'Trier en ordre croissant'"
                @click="triAsc = !triAsc">{{ triAsc ? '▲' : '▼' }}</button>
        <button v-if="!triParDefaut" class="hover:text-foreground" aria-label="Réinitialiser le tri et le filtre"
                @click="reinitialiserTri">✕</button>
        <label class="flex items-center gap-1.5">Filtre :
          <select v-model="filtreStatut" aria-label="Filtrer les cas par statut"
                  class="cursor-pointer border-b border-dotted border-muted-foreground bg-transparent text-foreground outline-none">
            <option value="">Aucun</option>
            <option v-for="k in TEST_STATUS_ORDER" :key="k" :value="k">{{ testStatusMeta(k).label }}</option>
          </select>
        </label>
        <span class="flex-1"></span>
        <div class="relative">
          <button class="hover:text-foreground" @click="menuColonnes = !menuColonnes">≡ Colonnes</button>
          <div v-if="menuColonnes" class="absolute right-0 z-30 mt-1 w-40 rounded-md border border-border bg-surface-overlay py-1 shadow-xl">
            <label v-for="col in COLONNES_MASQUABLES" :key="col.cle"
                   class="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-accent/60">
              <input type="checkbox" :checked="colonneVisible(col.cle)" @change="basculerColonne(col.cle)" />
              <span class="text-foreground">{{ col.label }}</span>
            </label>
          </div>
        </div>
      </div>

      <p v-if="!casVisibles.length" class="mt-3 text-sm text-muted-foreground">
        Aucun cas ne porte ce statut dans cette campagne.
      </p>

      <!-- Un bloc par GROUPE. Trié par statut → un bandeau « Passed (2) » par statut PRÉSENT ;
           trié autrement → une seule liste, sans bandeau. -->
      <section v-for="g in groupes" :key="g.code || 'tous'" class="mt-4">
        <div v-if="g.code" class="flex items-center gap-2">
          <span class="text-sm font-semibold">{{ testStatusMeta(g.code).label }}</span>
          <span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums"
                :class="testStatusMeta(g.code).badge">{{ g.cases.length }}</span>
          <span class="h-1 w-16 rounded-full" :style="{ background: `hsl(${testStatusMeta(g.code).color})` }"></span>
        </div>

        <table class="mt-1 w-full border-collapse text-sm">
          <thead>
            <tr class="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
              <th class="py-2 pl-1 w-16 text-left font-semibold">ID</th>
              <th class="py-2 px-2.5 text-left font-semibold">Titre</th>
              <th v-if="colonneVisible('assigne')" class="py-2 px-2.5 w-32 text-left font-semibold">Assigné à</th>
              <th v-if="colonneVisible('mode')" class="py-2 px-2.5 w-32 text-left font-semibold">Mode</th>
              <th v-if="colonneVisible('soumis')" class="py-2 px-2.5 w-40 text-left font-semibold">Soumis par</th>
              <th class="py-2 px-2.5 w-32 text-right font-semibold" title="État du cas dans cette campagne">Ét.</th>
              <th class="py-2 pl-2.5 w-10"></th>
              <th class="py-2 w-6"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in g.cases" :key="c.id"
                class="group border-b border-border/40 hover:bg-accent/30 cursor-pointer"
                @click="openCase(c)">
              <td class="py-3 pl-1 font-bold tabular-nums whitespace-nowrap text-muted-foreground">C{{ c.id }}</td>
              <td class="py-3 px-2.5 text-primary group-hover:underline leading-snug">{{ c.title }}</td>
              <!-- « Assigné à » : qui SUPERVISE ce cas dans cette campagne (2026-09-14, inspiré
                   de TestRail) — choisi parmi les membres RÉELS du projet, jamais tapé à la main.
                   Lecture seule pour qui n'a pas le droit de modifier (même seuil que « + Résultat »). -->
              <td v-if="colonneVisible('assigne')" class="py-3 px-2.5" @click.stop>
                <select v-if="peutModifier && !archived" :value="c.assigned_to"
                        :disabled="assignationEnCours === c.id"
                        :aria-label="`Assigné à — ${c.title}`"
                        class="w-full rounded-md border border-transparent bg-transparent px-1.5 py-1 text-sm hover:border-border hover:bg-surface-raised focus:border-primary focus:bg-surface-raised outline-none disabled:opacity-50"
                        @change="assignerCas(c.id, ($event.target as HTMLSelectElement).value)">
                  <option value="">Non assigné</option>
                  <option v-for="m in optionsAssignation(c.assigned_to)" :key="m.user_id" :value="m.username">{{ m.username }}</option>
                </select>
                <span v-else class="text-muted-foreground">{{ c.assigned_to || '—' }}</span>
              </td>
              <!-- Le MODE avant le statut : on lit « comment ça a été obtenu » puis « ce que ça
                   vaut ». L'inverse laisserait le statut s'imposer seul, ce qu'il ne doit jamais faire. -->
              <td v-if="colonneVisible('mode')" class="py-3 px-2.5">
                <ResultMode :mode="c.result_mode" :created-by="c.created_by" :at="c.result_at" />
              </td>
              <!-- Colonne « Soumis par », comme TestRail. Un compte de service pour la machine, un
                   nom de session pour un humain — et « — » quand personne n'a signé, jamais un nom
                   deviné. -->
              <td v-if="colonneVisible('soumis')" class="py-3 px-2.5 truncate text-muted-foreground">{{ libelleActeur(c.created_by) }}</td>
              <td class="py-3 px-2.5 text-right">
                <span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold"
                      :class="testStatusMeta(statusOf(c)).badge">
                  {{ testStatusMeta(statusOf(c)).label }}
                </span>
              </td>
              <td class="py-3 pl-2.5" @click.stop>
                <Button v-if="peutModifier && !archived && estManuelle" variant="secondary" size="sm"
                        :title="`Ajouter un résultat pour C${c.id}`"
                        @click="ouvrirSaisie(c)">+ Résultat</Button>
              </td>
              <td class="py-3 text-right text-muted-foreground group-hover:text-foreground" aria-hidden="true">›</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>

    <AddResultDialog :open="!!casSaisi" :run-id="runId" :cas="casSaisi"
                     :statuts="detail.statuts_manuels"
                     @close="casSaisi = null" @saved="resultatAjoute" />

    <!-- ════════ Ajouter cette campagne à un plan ════════ -->
    <Modal :open="showPlanPicker" title="Ajouter au plan de test"
           subtitle="Rattache cette campagne à un plan existant — rien n'est relancé ni modifié."
           @close="showPlanPicker = false">
      <p v-if="!plansDuProjet.length" class="text-sm text-muted-foreground">
        Aucun plan de test dans ce projet.
        <RouterLink :to="{ name: 'plan-new', params: { pid } }" class="text-primary hover:underline">En créer un</RouterLink>.
      </p>
      <div v-else class="divide-y divide-border/40 -mx-1">
        <button v-for="p in plansDuProjet" :key="p.id" type="button"
                class="w-full text-left px-1 py-2.5 text-sm hover:bg-accent/30 rounded-md truncate"
                @click="assignerAuPlan(p.id)">
          {{ p.name }}
        </button>
      </div>
    </Modal>
  </div>

  <div v-else class="text-sm text-muted-foreground">Exécution introuvable.</div>
</template>
