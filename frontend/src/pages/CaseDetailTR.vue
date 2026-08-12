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
import { api, roleSuffisant, type CaseDetail, type ScenarioResultOut } from '../lib/api'
import { ETAT_ORDER, TYPE_ORDER, etatView, priorityView, typeView } from '../lib/status'
import { useSession } from '../lib/useSession'
import CaseHeader from '../components/case/CaseHeader.vue'
import TestsResultsTab from '../components/case/TestsResultsTab.vue'
import DefectsTab from '../components/case/DefectsTab.vue'
import HistoryTab from '../components/case/HistoryTab.vue'
import CodeView from '../components/CodeView.vue'
import RefsList from '../components/RefsList.vue'
import Button from '../components/ui/Button.vue'
import IconButton from '../components/ui/IconButton.vue'

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
    loadSiblings(d.case?.module_id)
  } catch {
    error.value = 'Impossible de charger ce cas.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(caseId, load)

// ── Navigation entre cas (Précédent / Suivant), bornée au MODULE du cas ───────
// Chargée à part (best-effort) : une fratrie indisponible ne casse pas la page, elle désactive
// juste les flèches.
const siblings = ref<number[]>([])
async function loadSiblings(moduleId: number | null | undefined) {
  if (!moduleId) { siblings.value = []; return }
  try {
    // La fratrie se demande au serveur, bornée au MODULE : charger tout le projet pour deux
    // flèches « précédent / suivant » était le genre de coût qu'on ne voit pas venir.
    const page = await api.listCases(pid.value, { module_id: moduleId, limit: 500 })
    siblings.value = page.items.map((x) => x.id).sort((a, b) => a - b)
  } catch { siblings.value = [] }
}
const siblingIndex = computed(() => siblings.value.indexOf(caseId.value))
const prevId = computed(() => siblingIndex.value > 0 ? siblings.value[siblingIndex.value - 1] : null)
const nextId = computed(() =>
  siblingIndex.value >= 0 && siblingIndex.value < siblings.value.length - 1
    ? siblings.value[siblingIndex.value + 1] : null)
function goCase(id: number) {
  router.push({ name: 'case-detail', params: { pid: pid.value, id: String(id) } })
}

const currentVersion = computed(() => {
  const d = detail.value
  if (!d) return null
  return d.versions.find((v) => v.id === d.current_version_id) || d.versions[0] || null
})
// Un cas MANUEL n'a pas de Gherkin : pas de relecture ni d'exécution tant qu'aucun test
// technique n'a été généré. `feature_content` vide = pas de test exécutable.
const hasGherkin = computed(() => !!(currentVersion.value?.feature_content || '').trim())

// ── Onglet Script (2026-08-07) — lecture pour tous, édition réservée au rôle Dev ──────────────
const { session } = useSession()
const peutEditerScript = computed(() => roleSuffisant(session.value?.role || '', 'dev'))
const editingScript = ref(false)
const scriptDraft = ref({ feature: '', steps: '' })
const savingScript = ref(false)
const scriptError = ref('')

// ── Consultation par VERSION (2026-08-11) — une régénération (spec plus évoluée, réparation...)
// crée une NOUVELLE version, jamais un écrasement : sans sélecteur, seule la version COURANTE
// était consultable, malgré les précédentes déjà transmises par l'API. Porté par l'URL
// (`?version=`), comme `tab` — un lien depuis l'Historique doit pouvoir y renvoyer directement.
const versionAffichee = computed(() => {
  const d = detail.value
  if (!d) return null
  const demandee = Number(route.query.version)
  if (demandee && d.versions.some((v) => v.id === demandee)) {
    return d.versions.find((v) => v.id === demandee) || null
  }
  return currentVersion.value
})
const estVersionCourante = computed(() => versionAffichee.value?.id === detail.value?.current_version_id)
const scriptHasGherkin = computed(() => !!(versionAffichee.value?.feature_content || '').trim())

function selectionnerVersion(id: number) {
  editingScript.value = false
  router.replace({ query: { ...route.query, tab: 'script', version: String(id) } })
}
function revenirVersionCourante() {
  const q = { ...route.query, tab: 'script' } as Record<string, any>
  delete q.version
  router.replace({ query: q })
}

function startEditScript() {
  scriptDraft.value = {
    feature: currentVersion.value?.feature_content || '',
    steps: currentVersion.value?.steps_content || '',
  }
  scriptError.value = ''
  editingScript.value = true
}

async function saveScript() {
  if (!caseId.value) return
  savingScript.value = true
  scriptError.value = ''
  try {
    await api.updateCaseScript(caseId.value, scriptDraft.value.feature, scriptDraft.value.steps)
    editingScript.value = false
    await load()
  } catch (e: any) {
    scriptError.value = e?.message || 'Enregistrement impossible.'
  } finally {
    savingScript.value = false
  }
}

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

// Automatiser un cas MANUEL : générer son test technique depuis le métier saisi. Tâche de fond
// (LLM), suivie par le même mécanisme de job que la génération. Au bout, le cas a un Gherkin →
// `hasGherkin` devient vrai, le bouton disparaît, le gate + l'exécution apparaissent.
const automating = ref(false)
let autoTimer: number | undefined
async function automate() {
  automating.value = true
  error.value = ''
  try {
    const job = await api.automateCase(caseId.value)
    autoTimer = window.setInterval(async () => {
      try {
        const j = await api.getGenerationJob(job.job_id)
        if (j.status === 'running') return
        window.clearInterval(autoTimer)
        automating.value = false
        if (j.status === 'done') await load()
        else error.value = j.error || 'Automatisation échouée.'
      } catch {
        window.clearInterval(autoTimer)
        automating.value = false
        error.value = 'Suivi de l\'automatisation interrompu.'
      }
    }, 2000)
  } catch (e: any) {
    automating.value = false
    error.value = e?.message || 'Automatisation impossible.'
  }
}

// Priorité, Type et État éditables EN LIGNE (même endpoint : ces trois métadonnées ne créent
// pas de version et ne rebloquent pas le gate — elles ne changent pas ce que le test vérifie).
const priorityHint = priorityView('medium').hint
const savingMeta = ref(false)
async function onMeta(champs: { priority?: string; type?: string; etat?: string }) {
  savingMeta.value = true
  try {
    await api.setCaseMetadonnees(caseId.value, champs)
    await load()
  } catch (e: any) {
    error.value = e?.message || 'Modification impossible.'
  } finally {
    savingMeta.value = false
  }
}

// Suppression du cas — CASCADE (versions, exécutions, résultats). Confirmation explicite : §2.10
// interdit d'effacer un run en silence, pas sur demande claire de l'utilisateur.
async function deleteCase() {
  const nb = detail.value?.executions?.length || 0
  const detailTxt = nb ? ` et ses ${nb} exécution${nb > 1 ? 's' : ''}` : ''
  if (!window.confirm(`Supprimer le cas « ${c.value?.title } »${detailTxt} ? Cette action est irréversible.`)) return
  try {
    await api.deleteCase(caseId.value)
    router.push({ name: 'cases', params: { pid: pid.value } })
  } catch (e: any) {
    error.value = e?.message || 'Suppression impossible.'
  }
}

const c = computed(() => detail.value?.case ?? null)

// ── Points de vigilance (smoke-check) ─────────────────────────────────────────
// ⚠️ Amendement §4.3 (2026-07-21) : la validation métier à la création vaut relecture. Plus de
// gate humain ni de budget de réparation ICI (la réparation est gérée au niveau du Run). On garde
// seulement les SIGNAUX du smoke-check, en information — ils disent « ce test pourrait ne rien
// créer », sans plus rien à approuver.
const lintWarnings = computed(() => detail.value?.gate?.lint_warnings || [])

onBeforeUnmount(() => { if (autoTimer) window.clearInterval(autoTimer) })
</script>

<template>
  <div v-if="loading" class="p-8 space-y-3">
    <div class="h-8 w-64 rounded bg-secondary animate-pulse"></div>
    <div class="h-40 rounded bg-secondary animate-pulse"></div>
  </div>

  <div v-else-if="error" class="p-8 text-center">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <Button variant="secondary" class="mt-3" @click="load">Réessayer</Button>
  </div>

  <div v-else-if="c && detail">
    <!-- La sous-navigation (Détails / Tests & Résultats / …) vit dans la barre latérale du shell,
         sous « Cas de test » — ici on ne rend que le CONTENU de l'onglet actif. -->
    <div class="min-w-0 p-6 md:p-8 max-w-5xl">
      <CaseHeader :c="c" :can-automate="!hasGherkin" :automating="automating"
                  :prev-id="prevId" :next-id="nextId"
                  @back="backToList" @edit="startEdit" @delete="deleteCase" @automate="automate" @go="goCase" />

      <!-- ====== DÉTAILS ====== -->
      <template v-if="tab === 'details'">
        <!-- Métadonnées — vraies valeurs (avant : « Aucun » en dur, données ignorées). Priorité,
             Type et État éditables EN LIGNE ; les autres champs métier via « Modifier ».
             ⚠️ L'État n'est PLUS un statut système : c'est le cycle de vie du document, que
             l'utilisateur pose lui-même et que rien ne remet à zéro derrière lui. -->
        <div class="mt-4 rounded-lg border border-border bg-primary/5 p-4 grid grid-cols-4 gap-y-4 gap-x-6">
          <div>
            <div class="text-xs font-semibold text-muted-foreground flex items-center gap-1">
              Type
              <span class="cursor-help text-subtle-foreground" :title="typeView(c.type).hint">ⓘ</span>
            </div>
            <select :value="c.type" :disabled="savingMeta"
                    @change="onMeta({ type: ($event.target as HTMLSelectElement).value })"
                    class="mt-0.5 -ml-1 bg-transparent rounded px-1 py-0.5 hover:bg-accent/40 focus:bg-surface-raised focus:border-primary border border-transparent outline-none cursor-pointer">
              <option v-for="code in TYPE_ORDER" :key="code" :value="code">{{ typeView(code).label }}</option>
            </select>
          </div>
          <div>
            <div class="text-xs font-semibold text-muted-foreground flex items-center gap-1">
              État
              <span class="cursor-help text-subtle-foreground"
                    :title="etatView(c.etat).hint + ' Il décrit l\'avancement de la RÉDACTION du cas, jamais le résultat de ses exécutions.'">ⓘ</span>
            </div>
            <select :value="c.etat" :disabled="savingMeta"
                    @change="onMeta({ etat: ($event.target as HTMLSelectElement).value })"
                    class="mt-0.5 -ml-1 bg-transparent rounded px-1 py-0.5 hover:bg-accent/40 focus:bg-surface-raised focus:border-primary border border-transparent outline-none cursor-pointer">
              <option v-for="code in ETAT_ORDER" :key="code" :value="code">{{ etatView(code).label }}</option>
            </select>
          </div>
          <div>
            <div class="text-xs font-semibold text-muted-foreground flex items-center gap-1">
              Priorité
              <span class="cursor-help text-subtle-foreground" :title="priorityHint">ⓘ</span>
            </div>
            <select :value="c.priority" :disabled="savingMeta"
                    @change="onMeta({ priority: ($event.target as HTMLSelectElement).value })"
                    class="mt-0.5 -ml-1 bg-transparent rounded px-1 py-0.5 hover:bg-accent/40 focus:bg-surface-raised focus:border-primary border border-transparent outline-none cursor-pointer">
              <option value="high">Haute</option>
              <option value="medium">Moyenne</option>
              <option value="low">Basse</option>
            </select>
          </div>
          <div>
            <div class="text-xs font-semibold text-muted-foreground">Estimation</div>
            <div class="mt-0.5" :class="!c.estimate && 'text-subtle-foreground italic'">{{ c.estimate || 'Non renseignée' }}</div>
          </div>
          <div>
            <div class="text-xs font-semibold text-muted-foreground">Références</div>
            <div class="mt-0.5" :class="!c.refs && 'text-subtle-foreground italic'">
              <RefsList v-if="c.refs" :refs="c.refs" />
              <template v-else>Aucune</template>
            </div>
          </div>
          <div>
            <div class="text-xs font-semibold text-muted-foreground flex items-center gap-1">
              Test automatisé
              <span class="cursor-help text-subtle-foreground" title="« Oui » quand un test technique (Gherkin) existe et peut être exécuté. Un cas saisi à la main est « Non » tant qu'on n'a pas généré son test.">ⓘ</span>
            </div>
            <div class="mt-0.5">{{ hasGherkin ? 'Oui' : 'Non' }}</div>
          </div>
          <div class="col-span-2 self-end text-xs text-subtle-foreground">
            Estimation et références se modifient via « Modifier ».
          </div>
        </div>

        <p v-if="!hasMetier && !editing" class="mt-3 text-xs text-muted-foreground italic">
          Aperçu dérivé du test technique — ce cas n'a pas encore de contenu métier rédigé.
          Cliquez sur « Modifier » pour le rédiger.
        </p>

        <!-- ════════ LECTURE ════════ -->
        <template v-if="!editing">
          <section class="mt-6">
            <h2 class="font-semibold pb-2 border-b border-border">Préconditions</h2>
            <p v-if="metier.preconditions" class="mt-3 text-base leading-relaxed whitespace-pre-wrap text-foreground">{{ metier.preconditions }}</p>
            <ul v-else-if="derived.preconditions.length" class="mt-3 space-y-1.5 text-base leading-relaxed">
              <li v-for="(p, i) in derived.preconditions" :key="i" class="text-foreground">{{ p }}</li>
            </ul>
            <p v-else class="mt-3 text-muted-foreground">Aucune précondition renseignée.</p>
          </section>

          <section class="mt-6">
            <h2 class="font-semibold pb-2 border-b border-border">Étapes</h2>
            <ol v-if="metier.steps.length || derived.steps.length" class="mt-3 space-y-2 text-base leading-relaxed list-none">
              <li v-for="(s, i) in (metier.steps.length ? metier.steps : derived.steps)" :key="i" class="flex gap-3">
                <span class="shrink-0 text-muted-foreground tabular-nums font-medium">{{ i + 1 }}.</span>
                <span class="text-foreground">{{ s }}</span>
              </li>
            </ol>
            <p v-else class="mt-3 text-muted-foreground">Aucune étape renseignée.</p>
          </section>

          <section class="mt-6">
            <h2 class="font-semibold pb-2 border-b border-border">Résultat attendu</h2>
            <p v-if="metier.expected" class="mt-3 text-base leading-relaxed whitespace-pre-wrap text-foreground">{{ metier.expected }}</p>
            <ul v-else-if="derived.expected.length" class="mt-3 space-y-1.5 text-base leading-relaxed">
              <li v-for="(r, i) in derived.expected" :key="i" class="text-foreground">{{ r }}</li>
            </ul>
            <p v-else class="mt-3 text-muted-foreground">Aucun résultat attendu renseigné.</p>
          </section>

          <!-- Cas MANUEL (aucun Gherkin) : le test technique n'existe pas encore. -->
          <section v-if="!hasGherkin" class="mt-8">
            <h2 class="font-semibold pb-2 border-b border-border">Test technique</h2>
            <div class="mt-3 rounded-lg border border-border bg-primary/5 p-4 text-sm text-muted-foreground">
              Ce cas a été saisi à la main : il décrit ce qui doit être vérifié, mais son test
              technique n'a pas encore été généré (bouton « Automatiser avec l'IA » ci-dessus).
            </div>
          </section>

          <!-- ════════ POINTS DE VIGILANCE (info seule, PLUS un gate) ════════
               Amendement §4.3 (2026-07-21) : la validation métier à la création vaut relecture —
               il n'y a plus d'étape d'approbation ici. Mais le smoke-check reste AFFICHÉ : ces
               alertes disent « ce test pourrait ne rien créer ». Information, pas décision. -->
          <section v-if="hasGherkin && lintWarnings.length" class="mt-8">
            <h2 class="font-semibold pb-2 border-b border-border flex items-center gap-2">
              Points de vigilance
              <span class="rounded-full bg-warning/15 text-warning text-xs font-semibold px-2 py-0.5">{{ lintWarnings.length }}</span>
            </h2>
            <p class="mt-2 text-xs text-muted-foreground">
              Signaux relevés automatiquement sur ce test (cartographie mesurée). Indicatifs — à ton appréciation.
            </p>
            <ul class="mt-3 space-y-2">
              <li v-for="(w, i) in lintWarnings" :key="i" class="rounded-md border border-warning/30 bg-warning/5 p-3 text-sm">
                <div class="text-xs font-semibold text-warning">{{ w.step }} <span v-if="w.line" class="text-muted-foreground">· ligne {{ w.line }}</span></div>
                <div class="mt-1 text-foreground">{{ w.message }}</div>
              </li>
            </ul>
          </section>

          <!-- ════════ EXÉCUTION — renvoi vers Run/Plan ════════
               Un cas ne s'exécute pas seul : il se joue dans un Run. On indique où. -->
          <section v-if="hasGherkin" class="mt-8">
            <h2 class="font-semibold pb-2 border-b border-border">Exécution</h2>
            <div class="mt-3 rounded-lg border border-border bg-primary/5 p-4 text-sm text-muted-foreground">
              Ce test est prêt. Les exécutions se lancent depuis
              <RouterLink :to="{ name: 'executions', params: { pid } }" class="text-primary hover:underline">Exécutions et résultats de test</RouterLink>,
              dans un run qui regroupe les cas à jouer ensemble.
            </div>
          </section>
        </template>

        <!-- ════════ ÉDITION ════════ -->
        <template v-else>
          <div class="mt-4 rounded-lg border border-primary/40 bg-primary/5 p-3 text-xs text-muted-foreground">
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
                  <IconButton size="sm" variant="danger" label="Supprimer" @click="removeStep(i)">✕</IconButton>
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
                <span class="mt-1 block text-xs text-muted-foreground">
                  Séparées par des virgules — deviennent des liens si un gabarit est réglé dans Réglages.
                </span>
              </label>
              <label class="block">
                <span class="text-sm font-medium">Estimation</span>
                <input v-model="form.estimate" placeholder="ex. 15m" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
              </label>
            </div>

            <p v-if="saveError" class="text-sm text-destructive">{{ saveError }}</p>

            <div class="flex items-center gap-3">
              <Button variant="primary" :loading="saving" @click="save">
                {{ saving ? 'Enregistrement…' : 'Enregistrer' }}
              </Button>
              <Button variant="secondary" @click="editing = false">Annuler</Button>
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
        <HistoryTab :versions="detail.versions" @voir-script="selectionnerVersion" />
      </div>

      <!-- ====== SCRIPT (2026-08-07, sélecteur de version le 2026-08-11) — lecture pour tous,
           édition réservée au rôle Dev, et seulement sur la version COURANTE ====== -->
      <div v-else-if="tab === 'script'" class="mt-6 space-y-4">
        <label v-if="detail.versions.length > 1" class="block max-w-sm">
          <span class="text-xs text-muted-foreground">Version</span>
          <select :value="versionAffichee?.id"
                  @change="selectionnerVersion(Number(($event.target as HTMLSelectElement).value))"
                  class="mt-1 w-full rounded-md bg-surface border border-border px-3 py-2 text-sm focus:border-primary outline-none">
            <option v-for="v in [...detail.versions].sort((a, b) => b.version_number - a.version_number)"
                    :key="v.id" :value="v.id">
              Version {{ v.version_number }} — {{ new Date(v.created_at).toLocaleDateString('fr-FR') }}
              — {{ v.created_by === 'repair-agent' ? 'réparation automatique' : (v.created_by || 'auteur inconnu') }}
              {{ v.id === detail.current_version_id ? '(courante)' : '' }}
            </option>
          </select>
        </label>

        <p v-if="!estVersionCourante"
           class="rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm text-warning">
          Vous consultez la version {{ versionAffichee?.version_number }}, pas la version courante
          (V{{ currentVersion?.version_number }}) — lecture seule.
          <button class="ml-1 underline hover:no-underline" @click="revenirVersionCourante">
            Revenir à la version courante
          </button>
        </p>

        <p v-if="!scriptHasGherkin" class="text-sm text-muted-foreground">
          Aucun script technique généré pour cette version.
        </p>
        <template v-else-if="!editingScript">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold">Gherkin (.feature)</h3>
            <button v-if="peutEditerScript && estVersionCourante" class="text-sm text-primary hover:underline"
                    @click="startEditScript">Modifier</button>
          </div>
          <CodeView :content="versionAffichee?.feature_content || ''" lang="gherkin" />
          <h3 class="text-sm font-semibold">Python (steps)</h3>
          <CodeView :content="versionAffichee?.steps_content || ''" lang="python" />
        </template>
        <template v-else>
          <div>
            <h3 class="text-sm font-semibold">Gherkin (.feature)</h3>
            <textarea v-model="scriptDraft.feature" rows="14" spellcheck="false"
                      class="mt-1 w-full rounded-md bg-background border border-border px-3 py-2 font-mono text-xs outline-none focus:border-primary"></textarea>
          </div>
          <div>
            <h3 class="text-sm font-semibold">Python (steps)</h3>
            <textarea v-model="scriptDraft.steps" rows="14" spellcheck="false"
                      class="mt-1 w-full rounded-md bg-background border border-border px-3 py-2 font-mono text-xs outline-none focus:border-primary"></textarea>
          </div>
          <p class="text-xs text-muted-foreground">
            Enregistrer crée une NOUVELLE version — jamais d'écrasement — et la remet en attente
            de relecture : cette modification n'a pas été validée par un dry-run.
          </p>
          <p v-if="scriptError" class="text-sm text-destructive">{{ scriptError }}</p>
          <div class="flex gap-2">
            <Button variant="primary" :loading="savingScript" @click="saveScript">
              {{ savingScript ? 'Enregistrement…' : 'Enregistrer' }}
            </Button>
            <Button variant="secondary" :disabled="savingScript" @click="editingScript = false">Annuler</Button>
          </div>
        </template>
      </div>
    </div>
  </div>

  <div v-else class="p-8 text-sm text-muted-foreground">Cas introuvable.</div>
</template>
