<script setup lang="ts">
// « Générer des cas de test » — création en DEUX PASSES avec pause humaine (décision 0022 n°5,
// étendue au §9 : génération MULTI-CAS le 2026-08-05).
//
// Ajouter un cas = fournir une SPEC (décision 0006) : jamais une coquille vide. Mais la
// génération ne va plus d'un trait jusqu'au Gherkin, et ne produit plus UN seul cas : elle
// identifie les user stories de la spec, propose pour CHACUNE l'ensemble minimal de cas qui la
// couvre, puis s'ARRÊTE — et attend qu'un humain valide, corrige ou retire des cas. Le
// technique — la passe la plus chère, multipliée par le nombre de cas — n'est payé qu'après que
// l'intention a été signée dans son ensemble, pas cas par cas.
//
// L'écran a donc trois temps :
//   1. `form`     — la spécification ET la Section cible (étape 3bis, 2026-08-07)
//   2. `metier`   — les cas proposés, à PLAT, ÉDITABLES, repliés par défaut (c'est la pause)
//   3. `gherkin`  — l'écriture des tests, puis retour à la liste des cas
//
// ── Étape 3 (2026-08-07) : fini le regroupement automatique en Sections par user story ──────────
// L'IA continue à découper la spec en user stories EN INTERNE (ça l'aide à couvrir sans
// redondance), mais ce découpage ne crée plus AUCUNE Section : chaque cas ne porte qu'un simple
// REPÈRE DE LECTURE (`user_story`), affiché en sous-titre sur l'écran de validation.
//
// ── Étape 3bis (retour du manager du porteur, même jour) : la Section se choisit AVANT ──────────
// Pas cas par cas : UNE SEULE Section (existante ou nouvelle), choisie sur l'écran 1 — même
// patron exact que le choix du Module, et OBLIGATOIRE comme lui. Tous les cas qui sortiront de
// cette génération y atterrissent. L'écran 2 n'a donc plus aucun sélecteur : juste une liste à
// relire, repliée par défaut.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { api, type MetierDraft, type ModuleSummary } from '../lib/api'
import { MODELE_SPECIFICATION } from '../lib/modeleSpecification'
import { cles, useGroupes } from '../lib/donnees'
import Button from '../components/ui/Button.vue'
import IconButton from '../components/ui/IconButton.vue'

const route = useRoute()
const router = useRouter()
const qc = useQueryClient()
const pid = computed(() => route.params.pid as string)

type Etape = 'form' | 'analyse' | 'metier' | 'gherkin'
const etape = ref<Etape>('form')

const modules = ref<ModuleSummary[]>([])
const moduleId = ref<number | null>(null)
// ── Création d'un module depuis ce formulaire ────────────────────────────────
// ⚠️ Sans ça, un projet NEUF était un cul-de-sac silencieux : aucun module n'existe, la liste
// est vide, `submit()` sortait sur `if (!moduleId) return` — bouton sans effet, aucun message.
// Le backend savait créer un module depuis toujours ; rien ne le lui demandait.
// `-1` = « nouveau module » (une valeur d'id ne peut pas valoir -1).
const NOUVEAU = -1
const newModuleName = ref('')
const creatingModule = computed(() => moduleId.value === NOUVEAU || modules.value.length === 0)
const title = ref('')
const spec = ref('')
const error = ref('')
const jobId = ref('')
let timer: number | undefined

// ── Section cible, choisie AVANT la génération (étape 3bis) ───────────────────────────────────
// Même patron exact que le Module : `-2` = « nouvelle section » (distinct de NOUVEAU, qui vaut
// -1 et désigne un nouveau MODULE), obligatoire, réinitialisée si le module change (une Section
// n'existe que sous un module précis).
const NOUVELLE_SECTION = -2
const sectionId = ref<number | null>(null)
const newSectionName = ref('')
const { data: groupesData } = useGroupes(pid)
// Vide tant qu'aucun module RÉEL n'est ciblé (module en cours de création : ses sections
// n'existent pas encore) — même convention d'affichage que le glisser-déposer de l'étape 2bis.
const sectionsDuModule = computed(() => {
  if (moduleId.value == null || moduleId.value === NOUVEAU) return []
  const gs = (groupesData.value ?? []).filter((g) => g.module_id === moduleId.value)
  const options: { id: number; label: string }[] = []
  for (const s of gs.filter((g) => g.parent_group_id == null)) {
    options.push({ id: s.id, label: s.title })
    for (const sous of gs.filter((g) => g.parent_group_id === s.id)) {
      options.push({ id: sous.id, label: `${s.title} › ${sous.title}` })
    }
  }
  return options
})
const creatingSection = computed(() =>
  sectionId.value === NOUVELLE_SECTION || sectionsDuModule.value.length === 0)
watch(moduleId, () => { sectionId.value = null; newSectionName.value = '' })

// Les cas proposés, à PLAT, en cours d'édition (étape 3). Copie locale : ce que l'utilisateur
// envoie fait foi, la proposition de l'IA n'est qu'un point de départ — y compris pour la
// SUPPRESSION d'un cas qui ne sert à rien (§9 : « un cas qui peut être validé par un autre n'est
// pas intéressant »).
const cas = ref<MetierDraft[]>([])

// Regroupement PUREMENT VISUEL par user story (repère de lecture, jamais une Section) : les cas
// arrivent déjà groupés par story consécutive (c'est l'ordre dans lequel `decoupage` les a
// planifiés) — un simple découpage en tranches suffit, pas besoin de les re-trier.
const groupesAffichage = computed(() => {
  const out: { userStory: string; indices: number[] }[] = []
  cas.value.forEach((c, i) => {
    const us = c.user_story || ''
    const dernier = out[out.length - 1]
    if (dernier && dernier.userStory === us) dernier.indices.push(i)
    else out.push({ userStory: us, indices: [i] })
  })
  return out
})

// Plié par défaut (étape 3bis) : la Section étant déjà fixée, cet écran ne sert plus qu'à relire
// et corriger — pas besoin d'imposer tous les champs de tous les cas à l'œil dès l'arrivée.
const deplies = ref<Set<number>>(new Set())
function toggleDeplie(i: number) {
  const s = new Set(deplies.value)
  if (s.has(i)) s.delete(i); else s.add(i)
  deplies.value = s
}

// Titre + étapes + résultat attendu sont obligatoires (décision 0022 n°3.c) — un cas sans ces
// trois-là ne teste rien. Les préconditions restent facultatives. Règle inchangée.
function casComplet(c: MetierDraft): boolean {
  return !!c.title.trim() && c.steps.some((s) => s.trim()) && !!c.expected_result.trim()
}
const nbCasRetenus = computed(() => cas.value.length)
// Valide seulement si AU MOINS un cas subsiste, et que TOUS ceux qui subsistent sont complets —
// un cas incomplet ne doit jamais partir en génération technique (coûteuse) pour rien.
const toutValide = computed(() => cas.value.length > 0 && cas.value.every(casComplet))

function addStep(i: number) { cas.value[i].steps.push('') }
function removeStep(i: number, j: number) { cas.value[i].steps.splice(j, 1) }
function removeCase(i: number) { cas.value.splice(i, 1) }

// Une SPÉCIFICATION peut fournir le document (`?spec=`, depuis sa fiche, lot 4 du 2026-07-24) :
// on part alors du texte déjà rédigé plutôt que de le recoller à la main — c'était le chaînon
// manquant entre le document et les cas qu'il engendre.
const specSource = ref<{ id: number; title: string } | null>(null)

onMounted(async () => {
  modules.value = await api.listModules(pid.value)
  // Pré-sélection : le module visé par l'URL, sinon le premier.
  const wanted = Number(route.query.module)
  moduleId.value = modules.value.find((m) => m.id === wanted)?.id ?? modules.value[0]?.id ?? null

  const depuisSpec = Number(route.query.spec)
  if (depuisSpec) {
    try {
      const s = await api.getGroup(depuisSpec)
      spec.value = s.spec_content
      specSource.value = { id: s.id, title: s.title }
      // Le module de la spécification prime : générer un cas ailleurs que dans le module de son
      // document en ferait un orphelin de fait. Sa propre Section, elle, est un bon candidat par
      // défaut (mais reste un choix, pas une contrainte : l'utilisateur peut la changer).
      if (modules.value.some((m) => m.id === s.module_id)) {
        moduleId.value = s.module_id
        sectionId.value = s.id
      }
    } catch { /* spécification illisible : l'écran reste utilisable en saisie libre */ }
  }
})

function partirDuModele() {
  spec.value = MODELE_SPECIFICATION
}
onUnmounted(stopPoll)

function stopPoll() { if (timer) window.clearInterval(timer); timer = undefined }

async function submit() {
  if (!spec.value.trim()) return
  // Le module est créé À LA DEMANDE, avant la génération : un cas doit toujours atterrir quelque
  // part (§7). On le crée d'abord pour que l'échec éventuel (nom déjà pris) soit immédiat et
  // lisible, plutôt que de partir en tâche de fond payante et de finir en job « failed ».
  let cible = moduleId.value
  if (creatingModule.value) {
    if (!newModuleName.value.trim()) return
    error.value = ''
    try {
      const m = await api.createModule(pid.value, newModuleName.value.trim())
      modules.value.push(m)
      cible = m.id
      moduleId.value = m.id
    } catch (e: any) {
      error.value = e?.message || 'Création du module impossible.'
      return
    }
  }
  if (!cible) return

  // La Section, même geste : créée AVANT la génération si besoin (étape 3bis) — obligatoire,
  // comme le module, pour la même raison (échec immédiat et lisible plutôt qu'un job payant qui
  // finit en échec).
  let groupeCible: number | null = null
  if (creatingSection.value) {
    if (!newSectionName.value.trim()) return
    error.value = ''
    try {
      const g = await api.createGroup(cible, { title: newSectionName.value.trim() })
      groupeCible = g.id
    } catch (e: any) {
      error.value = e?.message || 'Création de la section impossible.'
      return
    }
  } else if (sectionId.value != null) {
    groupeCible = sectionId.value
  } else {
    return   // garde-fou : le bouton est désactivé tant qu'aucune Section n'est choisie
  }

  error.value = ''
  etape.value = 'analyse'
  try {
    const job = await api.addCase(cible, spec.value, title.value, groupeCible)
    jobId.value = job.job_id
    poll()
  } catch (e: any) {
    etape.value = 'form'
    error.value = e?.message || 'Création impossible.'
  }
}

function poll() {
  timer = window.setInterval(async () => {
    try {
      const job = await api.getGenerationJob(jobId.value)
      if (job.status === 'running') return
      stopPoll()

      if (job.status === 'awaiting_metier' && job.cases) {
        // ⚠️ LA PAUSE. Le job est arrêté : sans cet aiguillage, le formulaire tournerait
        // indéfiniment sur un job qui n'avancera jamais tout seul. Liste PLATE (étape 3), repliée
        // par défaut (étape 3bis) — la Section est déjà fixée, cet écran ne sert qu'à relire.
        cas.value = job.cases.map((c) => ({ ...c, steps: [...c.steps] }))
        deplies.value = new Set()
        etape.value = 'metier'
      } else if (job.status === 'done' && job.case_ids.length) {
        // N cas générés mais PAS relus : on retourne à la liste, jamais directement à
        // l'exécution — un seul cas ne mérite plus sa propre redirection dédiée (§9).
        // ⚠️ Cette page crée des cas en appelant l'API directement (hors couche `lib/donnees.ts`
        // pour la génération elle-même) : sans cette invalidation, l'arbre du shell (qui lit en
        // cache) restait périmé après une génération — écart constaté le 2026-08-06.
        qc.invalidateQueries({ queryKey: cles.projet(pid) })
        router.push({ name: 'cases', params: { pid: pid.value }, query: { module: String(moduleId.value) } })
      } else {
        etape.value = 'form'
        error.value = job.error || 'La génération a échoué.'
      }
    } catch (e: any) {
      stopPoll()
      etape.value = 'form'
      error.value = e?.message || 'Suivi de la génération impossible.'
    }
  }, 2000)
}

// ── Import d'un fichier de spec → remplit la zone de texte ────────────────────
const importing = ref(false)
const importedName = ref('')
const importError = ref('')
async function onFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  // L'extraction .docx a besoin du serveur ; on l'appelle sur le module visé (créé si besoin).
  importError.value = ''
  importing.value = true
  try {
    let cible = moduleId.value
    if (creatingModule.value) {
      if (!newModuleName.value.trim()) {
        importError.value = 'Nommez d\'abord le module, puis réimportez le fichier.'
        return
      }
      const m = await api.createModule(pid.value, newModuleName.value.trim())
      modules.value.push(m); cible = m.id; moduleId.value = m.id
    }
    if (!cible) return
    const { text, filename } = await api.extractSpec(cible, file)
    spec.value = text
    importedName.value = filename
  } catch (err: any) {
    importError.value = err?.message || 'Import impossible.'
  } finally {
    importing.value = false
    ;(e.target as HTMLInputElement).value = ''  // permet de réimporter le même fichier
  }
}

async function validerMetier() {
  if (!toutValide.value) return
  error.value = ''
  etape.value = 'gherkin'
  const retenus = cas.value.map((c) => ({
    ...c, steps: c.steps.map((s) => s.trim()).filter(Boolean),
  }))
  try {
    await api.validateMetier(jobId.value, retenus)
    poll()
  } catch (e: any) {
    etape.value = 'metier'
    error.value = e?.message || 'Validation impossible.'
  }
}

// Abandonner à la pause : aucun cas n'a été créé, il n'y a donc rien à nettoyer.
function abandonner() { router.push({ name: 'cases', params: { pid: pid.value } }) }
</script>

<template>
  <div class="max-w-[700px]">
    <h1 class="text-2xl font-semibold tracking-tight">Générer des cas de test</h1>

    <!-- ══════════ 1. LA SPÉCIFICATION ET LA SECTION CIBLE ══════════ -->
    <template v-if="etape === 'form' || etape === 'analyse'">
      <p class="mt-1 text-sm text-muted-foreground">
        Un cas se crée à partir d'une <strong class="text-foreground">spécification</strong>.
        L'IA en rédige d'abord le cas en langage métier — <strong class="text-foreground">vous le
        validez</strong> — et seulement ensuite elle écrit le test technique.
      </p>

      <form class="mt-6 space-y-5" @submit.prevent="submit">
        <label class="block">
          <span class="text-sm font-medium">Module <span class="text-destructive">*</span></span>
          <select v-if="modules.length" v-model="moduleId"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2">
            <option v-for="m in modules" :key="m.id" :value="m.id">{{ m.name }}</option>
            <option :value="NOUVEAU">+ Créer un module…</option>
          </select>
          <!-- Projet neuf : aucun module. On le DIT et on propose de le créer ici, au lieu de
               laisser une liste vide et un bouton sans effet. -->
          <input v-if="creatingModule" v-model="newModuleName"
                 :class="modules.length ? 'mt-2' : 'mt-1'"
                 placeholder="Nom du module (ex. Demande de matériel)"
                 class="w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          <p v-if="creatingModule && !modules.length" class="mt-1 text-xs text-muted-foreground">
            Ce projet n'a pas encore de module. Un module regroupe les cas d'une même
            fonctionnalité — donnez-lui un nom pour commencer.
          </p>
        </label>

        <!-- Section CIBLE (étape 3bis) : même patron exact que le Module, obligatoire comme lui —
             tous les cas de cette génération y atterrissent, quelle que soit leur user story. -->
        <label class="block">
          <span class="text-sm font-medium">Section <span class="text-destructive">*</span></span>
          <select v-if="sectionsDuModule.length" v-model="sectionId"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2">
            <option :value="null" disabled>Choisir une section…</option>
            <option v-for="o in sectionsDuModule" :key="o.id" :value="o.id">{{ o.label }}</option>
            <option :value="NOUVELLE_SECTION">+ Créer une section…</option>
          </select>
          <input v-if="creatingSection" v-model="newSectionName"
                 :class="sectionsDuModule.length ? 'mt-2' : 'mt-1'"
                 placeholder="Nom de la section (ex. Connexion)"
                 class="w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          <p v-if="!sectionsDuModule.length && moduleId != null && moduleId !== NOUVEAU"
             class="mt-1 text-xs text-muted-foreground">
            Ce module n'a pas encore de section. Donnez-lui un nom pour commencer — tous les cas
            générés depuis cette spécification y seront rangés.
          </p>
        </label>

        <label class="block">
          <span class="text-sm font-medium">Titre</span>
          <input v-model="title" placeholder="Laissez vide pour laisser l'IA proposer un titre"
                 class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        </label>

        <label class="block">
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium">Spécification <span class="text-destructive">*</span></span>
            <!-- Zone de texte OU fichier (demande du porteur). Le fichier est juste un moyen de
                 REMPLIR la zone : son texte est extrait côté serveur (.txt/.md/.docx) puis
                 déposé ici, éditable ensuite. -->
            <div class="flex items-center gap-3">
              <!-- Le MODÈLE (amendement §4.2 du 2026-07-24) : le document reste libre, mais
                   l'outil dit ce qu'il attend. Sans repère, deux specs du même auteur n'ont pas
                   la même forme et la génération part d'une matière irrégulière. -->
              <button v-if="!spec.trim()" type="button" class="text-xs text-primary hover:underline"
                      @click="partirDuModele">🧭 Partir du modèle</button>
              <label class="text-xs text-primary hover:underline cursor-pointer">
                <input type="file" class="hidden" accept=".txt,.md,.markdown,.docx,.feature,.text"
                       @change="onFile" />
                {{ importing ? 'Import…' : '📎 Importer un fichier (.txt, .md, .docx)' }}
              </label>
            </div>
          </div>
          <p v-if="specSource" class="mt-1 text-xs text-muted-foreground">
            Document repris de la spécification
            <RouterLink :to="{ name: 'spec-detail', params: { pid, id: String(specSource.id) } }"
                        class="text-primary hover:underline">{{ specSource.title }}</RouterLink>
            — le corriger ici ne modifie pas la spécification d'origine.
          </p>
          <textarea v-model="spec" rows="14" required
                    placeholder="Décrivez la fonctionnalité à tester : le parcours, les données attendues, les règles… — ou importez un fichier."
                    class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 font-mono text-sm focus:border-primary outline-none"></textarea>
          <p v-if="importedName" class="mt-1 text-xs text-muted-foreground">
            Importé depuis <strong class="text-foreground">{{ importedName }}</strong> — vous pouvez le corriger avant de générer.
          </p>
          <p v-if="importError" class="mt-1 text-xs text-destructive">{{ importError }}</p>
        </label>

        <p v-if="etape === 'analyse'" class="text-sm text-primary">
          Lecture de la spécification et rédaction du cas… (environ une minute)
        </p>
        <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

        <div class="flex items-center gap-3">
          <Button type="submit" variant="primary"
                  :disabled="etape === 'analyse' || !spec.trim()
                    || (creatingModule && !newModuleName.trim())
                    || (creatingSection && !newSectionName.trim())
                    || (!creatingSection && sectionId == null)"
                  :loading="etape === 'analyse'">
            {{ etape === 'analyse' ? 'Rédaction en cours…' : 'Rédiger le cas de test' }}
          </Button>
          <Button type="button" variant="secondary" @click="abandonner">Annuler</Button>
        </div>
      </form>
    </template>

    <!-- ══════════ 2. LA PAUSE — relire les cas proposés, repliés par défaut (étape 3bis) ══════ -->
    <template v-else-if="etape === 'metier'">
      <p class="mt-1 text-sm text-muted-foreground">
        Voici les cas tels que l'IA les a compris. <strong class="text-foreground">Dépliez-en un
        pour le consulter ou le corriger</strong>, retirez ce qui ne sert à rien, puis validez.
      </p>

      <div class="mt-4 rounded-lg border border-primary/40 bg-primary/5 p-3 text-xs text-muted-foreground">
        Aucun cas n'est encore créé, et aucun test technique n'est encore écrit. C'est le moment
        de corriger : après validation, un test sera généré pour chaque cas retenu, dans la
        Section choisie à l'étape précédente.
      </div>

      <div class="mt-6 space-y-6">
        <template v-for="g in groupesAffichage" :key="g.indices[0]">
          <!-- Repère de LECTURE seulement (étape 3) : jamais une Section, juste la provenance. -->
          <p v-if="g.userStory" class="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Issu de : {{ g.userStory }}
          </p>
          <div v-for="i in g.indices" :key="i" class="rounded-lg border border-border overflow-hidden">
            <div class="flex items-center gap-1 bg-surface-raised hover:bg-accent/40">
              <button type="button" class="flex min-w-0 flex-1 items-center gap-2 px-3 py-2.5 text-left"
                      :aria-label="`${deplies.has(i) ? 'Replier' : 'Déplier'} ${cas[i].title || 'ce cas'}`"
                      :aria-expanded="deplies.has(i)"
                      @click="toggleDeplie(i)">
                <svg class="w-3.5 h-3.5 shrink-0 transition-transform" :class="deplies.has(i) ? '' : '-rotate-90'"
                     viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"/></svg>
                <span class="min-w-0 flex-1 truncate font-medium">{{ cas[i].title || '(sans titre)' }}</span>
                <span v-if="!casComplet(cas[i])"
                      class="shrink-0 rounded-full bg-destructive/15 text-destructive text-xs font-semibold px-2 py-0.5">
                  incomplet
                </span>
              </button>
              <IconButton class="shrink-0 mr-1" variant="danger" label="Retirer ce cas" @click="removeCase(i)">✕</IconButton>
            </div>

            <div v-if="deplies.has(i)" class="p-4 space-y-4 border-t border-border">
              <label class="block">
                <span class="text-sm font-medium">Titre <span class="text-destructive">*</span></span>
                <input v-model="cas[i].title"
                       class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
              </label>

              <label class="block">
                <span class="text-sm font-medium">Préconditions</span>
                <textarea v-model="cas[i].preconditions" rows="2"
                          placeholder="Le contexte nécessaire avant de commencer (facultatif)"
                          class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
              </label>

              <div>
                <span class="text-sm font-medium">Étapes <span class="text-destructive">*</span></span>
                <div class="mt-1 space-y-2">
                  <div v-for="(_, j) in cas[i].steps" :key="j" class="flex items-center gap-2">
                    <span class="w-6 shrink-0 text-right text-muted-foreground tabular-nums text-sm">{{ j + 1 }}.</span>
                    <input v-model="cas[i].steps[j]"
                           class="flex-1 rounded-md bg-surface-raised border border-border px-3 py-1.5 focus:border-primary outline-none" />
                    <IconButton size="sm" variant="danger" label="Supprimer" @click="removeStep(i, j)">✕</IconButton>
                  </div>
                </div>
                <button type="button" class="mt-2 text-sm text-primary hover:underline" @click="addStep(i)">+ Ajouter une étape</button>
              </div>

              <label class="block">
                <span class="text-sm font-medium">Résultat attendu <span class="text-destructive">*</span></span>
                <textarea v-model="cas[i].expected_result" rows="2"
                          placeholder="Une seule phrase de verdict pour tout le cas"
                          class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
              </label>

              <p v-if="!casComplet(cas[i])" class="text-xs text-muted-foreground">
                Titre, au moins une étape et résultat attendu sont nécessaires — un cas sans eux
                ne vérifie rien.
              </p>
            </div>
          </div>
        </template>

        <p v-if="!cas.length" class="text-sm text-muted-foreground">
          Aucune user story exploitable n'a été trouvée dans cette spécification.
        </p>

        <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

        <div class="flex items-center gap-3 pt-2">
          <Button type="button" variant="primary" :disabled="!toutValide" @click="validerMetier">
            Valider {{ nbCasRetenus }} cas et générer les tests
          </Button>
          <Button type="button" variant="secondary" @click="abandonner">Abandonner</Button>
        </div>
      </div>
    </template>

    <!-- ══════════ 3. L'ÉCRITURE DES TESTS ══════════ -->
    <template v-else>
      <p class="mt-1 text-sm text-muted-foreground">
        Écriture des {{ nbCasRetenus }} tests techniques à partir des cas que vous venez de valider.
      </p>
      <div class="mt-8 flex items-center gap-3 text-sm text-primary">
        <span class="inline-block h-4 w-4 rounded-full border-2 border-primary border-t-transparent animate-spin"></span>
        Génération en cours… (quelques minutes)
      </div>
      <p v-if="error" class="mt-3 text-sm text-destructive">{{ error }}</p>
    </template>
  </div>
</template>
