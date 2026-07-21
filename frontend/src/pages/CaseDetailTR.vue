<script setup lang="ts">
// Détail d'un cas — disposition TestRail (palette sombre). Sous-nav : Détails (actif) +
// Tests & Résultats / Défauts / Historique (placeholders « à venir », lot séparé).
//
// ⚠️ TRANSITOIRE : les vraies sections métier (Préconditions / Étapes numérotées / Résultat
// attendu) sont un livrable de l'ÉTAPE 3 (la génération doit les PRODUIRE). En attendant, on en
// dérive un aperçu LISIBLE depuis le Gherkin de la version courante — mots-clés Gherkin
// retirés (jamais de Given/When/Then affiché, consigne du porteur). Provisoire, signalé comme tel.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseDetail, type ScenarioResultOut } from '../lib/api'
import { angleLabel, validationView } from '../lib/status'
import CaseHeader from '../components/case/CaseHeader.vue'
import TestsResultsTab from '../components/case/TestsResultsTab.vue'
import DefectsTab from '../components/case/DefectsTab.vue'
import HistoryTab from '../components/case/HistoryTab.vue'
import ReviewGate from '../components/ReviewGate.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const caseId = computed(() => Number(route.params.id))
const tab = computed(() => (route.query.tab as string) || 'details')

const detail = ref<CaseDetail | null>(null)
const scenarios = ref<ScenarioResultOut[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    // Les deux en parallèle : le détail (cas, exécutions, versions) et les résultats par scénario.
    const [d, sc] = await Promise.all([
      api.getCase(caseId.value),
      api.getCaseScenarios(caseId.value).catch(() => [] as ScenarioResultOut[]),
    ])
    detail.value = d
    scenarios.value = sc
  } catch {
    error.value = 'Impossible de charger ce cas.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(caseId, load)

const currentVersion = computed(() => {
  const d = detail.value
  if (!d) return null
  return d.versions.find((v) => v.id === d.current_version_id) || d.versions[0] || null
})

// ── Dérivation PROVISOIRE depuis le Gherkin (à remplacer par les champs métier, étape 3) ──
const GHERKIN_KW = /^\s*(Soit|Étant donné(?:e|s)?|Etant donné(?:e|s)?|Quand|Alors|Et|Mais|Given|When|Then|And|But)\b\s*/i

function scenariosOf(feature: string): { title: string; steps: string[] }[] {
  const lines = (feature || '').split('\n')
  const out: { title: string; steps: string[] }[] = []
  let cur: { title: string; steps: string[] } | null = null
  let inBackground = false
  const background: string[] = []
  for (const raw of lines) {
    const l = raw.trim()
    if (/^(Contexte|Background)\s*:/i.test(l)) { inBackground = true; continue }
    if (/^(Scénario|Scenario)\b/i.test(l)) {
      inBackground = false
      cur = { title: l.split(':').slice(1).join(':').trim() || l, steps: [] }
      out.push(cur)
      continue
    }
    if (/^#|^Fonctionnalité|^Feature|^En tant que|^Je veux|^Afin/i.test(l) || !l) continue
    const step = l.replace(GHERKIN_KW, '').trim()
    if (!step) continue
    if (inBackground) background.push(step)
    else if (cur) cur.steps.push(step)
  }
  return [{ title: '__background__', steps: background }, ...out]
}

const derived = computed(() => {
  const parsed = scenariosOf(currentVersion.value?.feature_content || '')
  const bg = parsed.find((s) => s.title === '__background__')?.steps || []
  const first = parsed.find((s) => s.title !== '__background__')
  // Étapes = les actions du premier scénario, hors lignes de vérification (« … existe », « le
  // nombre … »). Résultat = ces lignes de vérification, en verdict.
  const isCheck = (s: string) => /(existe|augmente|conforme|affich|erreur|nombre|attendu|pointe|égal|contient)/i.test(s)
  const actions = (first?.steps || []).filter((s) => !isCheck(s))
  const checks = (first?.steps || []).filter(isCheck)
  return { preconditions: bg, steps: actions, expected: checks }
})

// ── Le contenu MÉTIER RÉEL (décision 0022) — la dérivation ci-dessus n'est plus qu'un REPLI ──
// Tant que les champs sont vides (cas d'avant la génération métier, chantier B), on continue
// d'afficher l'aperçu dérivé, signalé comme tel. On ne STOCKE jamais ce texte dérivé : il
// aurait l'air rédigé alors qu'il vient d'une conversion automatique (arbitrage A.1).
function parseSteps(raw: string): string[] {
  if (!raw) return []
  try {
    const v = JSON.parse(raw)
    return Array.isArray(v) ? v.map(String) : []
  } catch { return raw.split('\n').map((s) => s.trim()).filter(Boolean) }
}
const metier = computed(() => {
  const v = currentVersion.value
  return {
    preconditions: v?.preconditions || '',
    steps: parseSteps(v?.test_steps || ''),
    expected: v?.expected_result || '',
  }
})
// Un seul champ métier rempli suffit à considérer que le cas est « rédigé ».
const hasMetier = computed(() =>
  !!(metier.value.preconditions || metier.value.steps.length || metier.value.expected))

// ── Édition ───────────────────────────────────────────────────────────────────
const editing = ref(false)
const saving = ref(false)
const saveError = ref('')
const form = ref({ title: '', preconditions: '', steps: [] as string[], expected: '', refs: '', estimate: '' })

function startEdit() {
  const v = currentVersion.value
  form.value = {
    title: c.value?.title || '',
    // À l'ouverture, on pré-remplit avec le métier réel s'il existe, SINON avec la dérivation :
    // l'utilisateur part de quelque chose de lisible au lieu d'une page blanche — et à partir du
    // moment où il enregistre, c'est SON texte, assumé, plus une dérivation.
    preconditions: v?.preconditions || derived.value.preconditions.join('\n'),
    steps: metier.value.steps.length ? [...metier.value.steps] : [...derived.value.steps],
    expected: v?.expected_result || derived.value.expected.join(' '),
    refs: c.value?.refs || '',
    estimate: c.value?.estimate || '',
  }
  saveError.value = ''
  editing.value = true
}
function addStep() { form.value.steps.push('') }
function removeStep(i: number) { form.value.steps.splice(i, 1) }

async function save() {
  saving.value = true
  saveError.value = ''
  try {
    await api.updateCaseMetier(caseId.value, {
      title: form.value.title,
      preconditions: form.value.preconditions,
      test_steps: JSON.stringify(form.value.steps.map((s) => s.trim()).filter(Boolean)),
      expected_result: form.value.expected,
      refs: form.value.refs,
      estimate: form.value.estimate,
    })
    editing.value = false
    await load()
  } catch (e: any) {
    saveError.value = e?.message || 'Enregistrement impossible.'
  } finally {
    saving.value = false
  }
}

function backToList() { router.push({ name: 'cases', params: { pid: pid.value } }) }

const c = computed(() => detail.value?.case ?? null)

// ── Relecture (gate) et lancement d'exécution ─────────────────────────────────
// ⚠️ REPORTÉS depuis l'ancienne page `CaseDetail.vue`, devenue orpheline quand cet écran l'a
// remplacée. Les deux backends fonctionnaient, mais plus AUCUN bouton ne les atteignait : on ne
// pouvait plus ni approuver une version, ni lancer un test depuis l'interface. Le gate est
// pourtant l'invariant §4.3 (relecture humaine obligatoire avant la première exécution) — le
// perdre revenait à retirer du produit la garantie qu'il annonce.
const running = ref(false)
const runError = ref('')
let pollTimer: number | undefined

const currentReview = computed(() =>
  (detail.value?.reviews || []).find((r) => r.version_id === detail.value?.current_version_id))

function reviewerLabel(reviewer: string) {
  return reviewer === 'cli' ? 'ligne de commande' : reviewer || '—'
}

async function launch() {
  runError.value = ''
  running.value = true
  try {
    const { execution_id } = await api.runCase(caseId.value)
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
        router.push({ name: 'report', params: { pid: pid.value, id: String(execId) } })
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
onBeforeUnmount(stopPoll)
</script>

<template>
  <div v-if="loading" class="p-8 space-y-3">
    <div class="h-8 w-64 rounded bg-secondary animate-pulse"></div>
    <div class="h-40 rounded bg-secondary animate-pulse"></div>
  </div>

  <div v-else-if="error" class="p-8 text-center">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <button class="mt-3 rounded-md border border-border px-3 py-1.5 text-sm hover:border-primary/40" @click="load">Réessayer</button>
  </div>

  <div v-else-if="c && detail">
    <!-- La sous-navigation (Détails / Tests & Résultats / …) vit dans la barre latérale du shell,
         sous « Cas de test » — ici on ne rend que le CONTENU de l'onglet actif. -->
    <div class="min-w-0 p-6 md:p-8 max-w-5xl">
      <CaseHeader :c="c" @back="backToList" @edit="startEdit" />

      <!-- ====== DÉTAILS ====== -->
      <template v-if="tab === 'details'">
        <!-- Métadonnées -->
        <div class="mt-4 rounded-lg border border-border bg-primary/[0.05] p-4 grid grid-cols-4 gap-y-4 gap-x-6">
          <div><div class="text-xs font-semibold text-muted-foreground">Type</div><div class="mt-0.5">{{ angleLabel(c.angle) }}</div></div>
          <div><div class="text-xs font-semibold text-muted-foreground">État</div><div class="mt-0.5">{{ validationView(c.validation_status).label }}</div></div>
          <div><div class="text-xs font-semibold text-muted-foreground">Priorité</div><div class="mt-0.5 text-muted-foreground">Aucun</div></div>
          <div><div class="text-xs font-semibold text-muted-foreground">Estimation</div><div class="mt-0.5 text-muted-foreground">Aucun</div></div>
          <div><div class="text-xs font-semibold text-muted-foreground">Références</div><div class="mt-0.5 text-muted-foreground">Aucun</div></div>
          <div><div class="text-xs font-semibold text-muted-foreground">Test automatisé par IA</div><div class="mt-0.5 text-muted-foreground">Aucun</div></div>
          <div></div><div></div>
        </div>

        <p v-if="!hasMetier && !editing" class="mt-3 text-xs text-muted-foreground italic">
          Aperçu dérivé du test technique — ce cas n'a pas encore de contenu métier rédigé.
          Cliquez sur « Modifier » pour le rédiger.
        </p>

        <!-- ════════ LECTURE ════════ -->
        <template v-if="!editing">
          <section class="mt-6">
            <h2 class="font-semibold pb-2 border-b border-border">Préconditions</h2>
            <p v-if="metier.preconditions" class="mt-3 text-[15px] leading-relaxed whitespace-pre-wrap text-foreground/90">{{ metier.preconditions }}</p>
            <ul v-else-if="derived.preconditions.length" class="mt-3 space-y-1.5 text-[15px] leading-relaxed">
              <li v-for="(p, i) in derived.preconditions" :key="i" class="text-foreground/90">{{ p }}</li>
            </ul>
            <p v-else class="mt-3 text-muted-foreground">Aucune précondition renseignée.</p>
          </section>

          <section class="mt-6">
            <h2 class="font-semibold pb-2 border-b border-border">Étapes</h2>
            <ol v-if="metier.steps.length || derived.steps.length" class="mt-3 space-y-2 text-[15px] leading-relaxed list-none">
              <li v-for="(s, i) in (metier.steps.length ? metier.steps : derived.steps)" :key="i" class="flex gap-3">
                <span class="shrink-0 text-muted-foreground tabular-nums font-medium">{{ i + 1 }}.</span>
                <span class="text-foreground/90">{{ s }}</span>
              </li>
            </ol>
            <p v-else class="mt-3 text-muted-foreground">Aucune étape renseignée.</p>
          </section>

          <section class="mt-6">
            <h2 class="font-semibold pb-2 border-b border-border">Résultat attendu</h2>
            <p v-if="metier.expected" class="mt-3 text-[15px] leading-relaxed whitespace-pre-wrap text-foreground/90">{{ metier.expected }}</p>
            <ul v-else-if="derived.expected.length" class="mt-3 space-y-1.5 text-[15px] leading-relaxed">
              <li v-for="(r, i) in derived.expected" :key="i" class="text-foreground/90">{{ r }}</li>
            </ul>
            <p v-else class="mt-3 text-muted-foreground">Aucun résultat attendu renseigné.</p>
          </section>

          <!-- ════════ RELECTURE (gate) ════════
               Invariant §4.3 : une version générée par IA doit être relue par un humain AVANT
               sa première exécution. Bloc distinct du lancement, et placé AVANT lui : l'ordre à
               l'écran dit l'ordre réel du produit. -->
          <section class="mt-8">
            <h2 class="font-semibold pb-2 border-b border-border">Relecture</h2>
            <div class="mt-3 space-y-3">
              <ReviewGate :case-id="caseId" :gate="detail.gate" @reviewed="load" />
              <p v-if="currentReview" class="text-xs text-muted-foreground">
                Dernière décision : {{ currentReview.decision === 'approved' ? 'approuvée' : 'rejetée' }}
                par {{ reviewerLabel(currentReview.reviewer) }} · {{ currentReview.decided_at }}
              </p>
            </div>
          </section>

          <!-- ════════ EXÉCUTION ════════
               Le bouton est DÉSACTIVÉ tant que le gate n'autorise pas : l'interface ne propose
               jamais une action que le backend refusera (« affiché ≠ réel », invariant §4.6), et
               le message dit POURQUOI plutôt que de laisser deviner. -->
          <section class="mt-8">
            <h2 class="font-semibold pb-2 border-b border-border">Exécution</h2>
            <div class="mt-3 flex flex-wrap items-center gap-3">
              <button class="rounded-md bg-primary text-white font-semibold px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                      :disabled="running || !detail.gate?.allowed" @click="launch">
                {{ running ? 'Exécution en cours…' : 'Lancer une exécution' }}
              </button>
              <span v-if="running" class="text-xs text-muted-foreground">
                Le test tourne réellement contre l'application — cela prend quelques minutes.
              </span>
              <span v-else-if="!detail.gate?.allowed" class="text-xs text-muted-foreground">
                Approuvez la version en relecture pour pouvoir la lancer.
              </span>
            </div>
            <p v-if="runError" class="mt-2 text-xs text-destructive">{{ runError }}</p>
          </section>
        </template>

        <!-- ════════ ÉDITION ════════ -->
        <template v-else>
          <div class="mt-4 rounded-lg border border-primary/40 bg-primary/[0.04] p-3 text-xs text-muted-foreground">
            Enregistrer crée une <strong class="text-foreground">nouvelle version</strong> du cas.
            Le test technique n'est pas régénéré : la version devra être <strong class="text-foreground">relue</strong> avant toute exécution.
          </div>

          <section class="mt-5 space-y-5">
            <label class="block">
              <span class="text-sm font-medium">Titre</span>
              <input v-model="form.title" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
            </label>

            <label class="block">
              <span class="text-sm font-medium">Préconditions</span>
              <textarea v-model="form.preconditions" rows="3" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
            </label>

            <div>
              <span class="text-sm font-medium">Étapes</span>
              <div class="mt-1 space-y-2">
                <div v-for="(s, i) in form.steps" :key="i" class="flex items-center gap-2">
                  <span class="w-6 shrink-0 text-right text-muted-foreground tabular-nums text-sm">{{ i + 1 }}.</span>
                  <input v-model="form.steps[i]" class="flex-1 rounded-md bg-surface-raised border border-border px-3 py-1.5 focus:border-primary outline-none" />
                  <button type="button" class="text-muted-foreground hover:text-destructive px-1" title="Supprimer" @click="removeStep(i)">✕</button>
                </div>
              </div>
              <button type="button" class="mt-2 text-sm text-primary hover:underline" @click="addStep">+ Ajouter une étape</button>
            </div>

            <label class="block">
              <span class="text-sm font-medium">Résultat attendu</span>
              <textarea v-model="form.expected" rows="2" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
            </label>

            <div class="grid grid-cols-2 gap-4">
              <label class="block">
                <span class="text-sm font-medium">Références</span>
                <input v-model="form.refs" placeholder="JIRA-123…" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
              </label>
              <label class="block">
                <span class="text-sm font-medium">Estimation</span>
                <input v-model="form.estimate" placeholder="ex. 15m" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
              </label>
            </div>

            <p v-if="saveError" class="text-sm text-destructive">{{ saveError }}</p>

            <div class="flex items-center gap-3">
              <button class="rounded-md bg-primary text-white font-semibold px-4 py-2 disabled:opacity-60" :disabled="saving" @click="save">
                {{ saving ? 'Enregistrement…' : 'Enregistrer' }}
              </button>
              <button class="rounded-md border border-border px-4 py-2 hover:border-primary/40" @click="editing = false">Annuler</button>
            </div>
          </section>
        </template>
      </template>

      <!-- ====== TESTS & RÉSULTATS ====== -->
      <div v-else-if="tab === 'tests'" class="mt-6">
        <TestsResultsTab :pid="pid" :executions="detail.executions" :scenarios="scenarios" />
      </div>

      <!-- ====== DÉFAUTS ====== -->
      <div v-else-if="tab === 'defauts'" class="mt-6">
        <DefectsTab :executions="detail.executions" />
      </div>

      <!-- ====== HISTORIQUE ====== -->
      <div v-else-if="tab === 'historique'" class="mt-6">
        <HistoryTab :versions="detail.versions" />
      </div>
    </div>
  </div>

  <div v-else class="p-8 text-sm text-muted-foreground">Cas introuvable.</div>
</template>
