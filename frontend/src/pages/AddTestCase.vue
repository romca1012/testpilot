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
//   1. `form`     — la spécification
//   2. `metier`   — les Sections proposées, groupées, ÉDITABLES (c'est la pause)
//   3. `gherkin`  — l'écriture des tests, puis retour à la liste des cas
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type MetierDraft, type ModuleSummary, type SectionDraft } from '../lib/api'
import { MODELE_SPECIFICATION } from '../lib/modeleSpecification'

const route = useRoute()
const router = useRouter()
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

// Les Sections proposées, en cours d'édition. Copie locale : ce que l'utilisateur envoie fait
// foi, la proposition de l'IA n'est qu'un point de départ — y compris pour la SUPPRESSION d'un
// cas qui ne sert à rien (§9 : « un cas qui peut être validé par un autre n'est pas intéressant »).
const sections = ref<SectionDraft[]>([])
// Sections repliées, par INDEX — même mécanisme que le pliage des modules dans TestCasesList.vue.
const repliees = ref<number[]>([])
function toggleSection(i: number) {
  repliees.value = repliees.value.includes(i)
    ? repliees.value.filter((x) => x !== i) : [...repliees.value, i]
}

// Titre + étapes + résultat attendu sont obligatoires (décision 0022 n°3.c) — un cas sans ces
// trois-là ne teste rien. Les préconditions restent facultatives. Règle inchangée, appliquée
// maintenant à CHAQUE cas retenu plutôt qu'à un document unique.
function casComplet(c: MetierDraft): boolean {
  return !!c.title.trim() && c.steps.some((s) => s.trim()) && !!c.expected_result.trim()
}
const nbCasRetenus = computed(() => sections.value.reduce((n, s) => n + s.cases.length, 0))
// Valide seulement si AU MOINS un cas subsiste, et que TOUS ceux qui subsistent sont complets —
// un cas incomplet ne doit jamais partir en génération technique (coûteuse) pour rien.
const toutValide = computed(() =>
  nbCasRetenus.value > 0 && sections.value.every((s) => s.cases.every(casComplet)))

function addStep(si: number, ci: number) { sections.value[si].cases[ci].steps.push('') }
function removeStep(si: number, ci: number, i: number) { sections.value[si].cases[ci].steps.splice(i, 1) }
// Retirer un cas ne supprime PAS sa Section : une Section vidée de tous ses cas est simplement
// ignorée par le serveur à la validation (elle ne sera pas créée).
function removeCase(si: number, ci: number) { sections.value[si].cases.splice(ci, 1) }

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
      // document en ferait un orphelin de fait.
      if (modules.value.some((m) => m.id === s.module_id)) moduleId.value = s.module_id
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
  error.value = ''
  etape.value = 'analyse'
  try {
    const job = await api.addCase(cible, spec.value, title.value)
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

      if (job.status === 'awaiting_metier' && job.sections) {
        // ⚠️ LA PAUSE. Le job est arrêté : sans cet aiguillage, le formulaire tournerait
        // indéfiniment sur un job qui n'avancera jamais tout seul.
        sections.value = job.sections.map((s) => ({
          title: s.title,
          cases: s.cases.map((c) => ({ ...c, steps: [...c.steps] })),
        }))
        repliees.value = []
        etape.value = 'metier'
      } else if (job.status === 'done' && job.case_ids.length) {
        // N cas générés mais PAS relus : on retourne à la liste, jamais directement à
        // l'exécution — un seul cas ne mérite plus sa propre redirection dédiée (§9).
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
  // Sections vidées de tous leurs cas exclues avant l'envoi : rien ne sert de les faire
  // transiter, le serveur les ignorerait de toute façon (elles ne créent rien).
  const retenues = sections.value
    .filter((s) => s.cases.length)
    .map((s) => ({
      title: s.title,
      cases: s.cases.map((c) => ({ ...c, steps: c.steps.map((s) => s.trim()).filter(Boolean) })),
    }))
  try {
    await api.validateMetier(jobId.value, retenues)
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
  <div class="p-6 md:p-8 max-w-[760px]">
    <h1 class="text-[26px] font-semibold tracking-tight">Générer des cas de test</h1>

    <!-- ══════════ 1. LA SPÉCIFICATION ══════════ -->
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
                    class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 font-mono text-[13px] focus:border-primary outline-none"></textarea>
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
          <button type="submit"
                  :disabled="etape === 'analyse' || !spec.trim() || (creatingModule && !newModuleName.trim())"
                  class="rounded-md bg-primary text-white font-semibold px-4 py-2 disabled:opacity-60">
            {{ etape === 'analyse' ? 'Rédaction en cours…' : 'Rédiger le cas de test' }}
          </button>
          <button type="button" class="rounded-md border border-border px-4 py-2 hover:border-primary/40" @click="abandonner">Annuler</button>
        </div>
      </form>
    </template>

    <!-- ══════════ 2. LA PAUSE — validation des Sections proposées (§9) ══════════ -->
    <template v-else-if="etape === 'metier'">
      <p class="mt-1 text-sm text-muted-foreground">
        Voici les cas tels que l'IA les a compris, groupés par user story. <strong
        class="text-foreground">Corrigez, ou retirez</strong> ce qui ne sert à rien — c'est cet
        ensemble qui servira à écrire les tests.
      </p>

      <div class="mt-4 rounded-lg border border-primary/40 bg-primary/[0.05] p-3 text-xs text-muted-foreground">
        Aucun cas n'est encore créé, et aucun test technique n'est encore écrit. C'est le moment
        de corriger : après validation, un test sera généré pour chaque cas retenu.
      </div>

      <div class="mt-6 space-y-4">
        <div v-for="(section, si) in sections" :key="si"
             class="rounded-lg border border-border overflow-hidden">
          <button type="button"
                  class="w-full flex items-center gap-2 px-3 py-2.5 bg-surface-raised hover:bg-accent/40 text-left"
                  :aria-label="`${repliees.includes(si) ? 'Déplier' : 'Replier'} la section ${section.title}`"
                  :aria-expanded="!repliees.includes(si)"
                  @click="toggleSection(si)">
            <svg class="w-3.5 h-3.5 shrink-0 transition-transform" :class="repliees.includes(si) ? '-rotate-90' : ''"
                 viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"/></svg>
            <span class="font-semibold flex-1 truncate">{{ section.title }}</span>
            <span class="shrink-0 rounded-full bg-primary/15 text-primary text-[11px] font-semibold px-2 py-0.5 tabular-nums">
              {{ section.cases.length }} cas
            </span>
          </button>

          <div v-if="!repliees.includes(si) && !section.cases.length" class="px-3 py-3 text-xs text-muted-foreground">
            Aucun cas retenu dans cette section — elle ne sera pas créée.
          </div>

          <div v-if="!repliees.includes(si)" class="divide-y divide-border">
            <div v-for="(cas, ci) in section.cases" :key="ci" class="p-4 space-y-4">
              <div class="flex items-start gap-3">
                <label class="block flex-1">
                  <span class="text-sm font-medium">Titre <span class="text-destructive">*</span></span>
                  <input v-model="cas.title"
                         class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
                </label>
                <button type="button"
                        class="mt-6 text-muted-foreground hover:text-destructive px-1 shrink-0"
                        title="Retirer ce cas" @click="removeCase(si, ci)">✕</button>
              </div>

              <label class="block">
                <span class="text-sm font-medium">Préconditions</span>
                <textarea v-model="cas.preconditions" rows="2"
                          placeholder="Le contexte nécessaire avant de commencer (facultatif)"
                          class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
              </label>

              <div>
                <span class="text-sm font-medium">Étapes <span class="text-destructive">*</span></span>
                <div class="mt-1 space-y-2">
                  <div v-for="(_, i) in cas.steps" :key="i" class="flex items-center gap-2">
                    <span class="w-6 shrink-0 text-right text-muted-foreground tabular-nums text-sm">{{ i + 1 }}.</span>
                    <input v-model="cas.steps[i]"
                           class="flex-1 rounded-md bg-surface-raised border border-border px-3 py-1.5 focus:border-primary outline-none" />
                    <button type="button" class="text-muted-foreground hover:text-destructive px-1" title="Supprimer" @click="removeStep(si, ci, i)">✕</button>
                  </div>
                </div>
                <button type="button" class="mt-2 text-sm text-primary hover:underline" @click="addStep(si, ci)">+ Ajouter une étape</button>
              </div>

              <label class="block">
                <span class="text-sm font-medium">Résultat attendu <span class="text-destructive">*</span></span>
                <textarea v-model="cas.expected_result" rows="2"
                          placeholder="Une seule phrase de verdict pour tout le cas"
                          class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
              </label>

              <p v-if="!casComplet(cas)" class="text-xs text-muted-foreground">
                Titre, au moins une étape et résultat attendu sont nécessaires — un cas sans eux
                ne vérifie rien.
              </p>
            </div>
          </div>
        </div>

        <p v-if="!sections.length" class="text-sm text-muted-foreground">
          Aucune user story exploitable n'a été trouvée dans cette spécification.
        </p>

        <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

        <div class="flex items-center gap-3 pt-2">
          <button type="button" :disabled="!toutValide"
                  class="rounded-md bg-primary text-white font-semibold px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  @click="validerMetier">
            Valider {{ nbCasRetenus }} cas et générer les tests
          </button>
          <button type="button" class="rounded-md border border-border px-4 py-2 hover:border-primary/40" @click="abandonner">Abandonner</button>
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
