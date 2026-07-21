<script setup lang="ts">
// « Ajouter un cas de test » — création en DEUX PASSES avec pause humaine (décision 0022 n°5).
//
// Ajouter un cas = fournir une SPEC (décision 0006) : jamais une coquille vide. Mais la
// génération ne va plus d'un trait jusqu'au Gherkin : elle s'ARRÊTE une fois le document métier
// rédigé, et attend qu'un humain le valide ou le corrige. Le technique — la passe la plus chère —
// n'est payé qu'après que l'intention a été signée.
//
// L'écran a donc trois temps :
//   1. `form`     — la spécification
//   2. `metier`   — le document proposé, ÉDITABLE (c'est la pause)
//   3. `gherkin`  — l'écriture du test, puis redirection vers le gate
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type MetierDraft, type ModuleSummary } from '../lib/api'

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

// Le document métier en cours d'édition. Copie locale : ce que l'utilisateur envoie fait foi,
// la proposition de l'IA n'est qu'un point de départ.
const metier = ref<MetierDraft>({
  title: '', preconditions: '', steps: [], expected_result: '', angle: '',
})

// Titre + étapes + résultat attendu sont obligatoires (décision 0022 n°3.c) — un cas sans ces
// trois-là ne teste rien. Les préconditions restent facultatives.
const metierComplet = computed(() =>
  !!metier.value.title.trim()
  && metier.value.steps.some((s) => s.trim())
  && !!metier.value.expected_result.trim())

onMounted(async () => {
  modules.value = await api.listModules(pid.value)
  // Pré-sélection : le module visé par l'URL, sinon le premier.
  const wanted = Number(route.query.module)
  moduleId.value = modules.value.find((m) => m.id === wanted)?.id ?? modules.value[0]?.id ?? null
})
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

      if (job.status === 'awaiting_metier' && job.metier) {
        // ⚠️ LA PAUSE. Le job est arrêté : sans cet aiguillage, le formulaire tournerait
        // indéfiniment sur un job qui n'avancera jamais tout seul.
        metier.value = { ...job.metier, steps: [...job.metier.steps] }
        etape.value = 'metier'
      } else if (job.status === 'done' && job.case_id) {
        // Le cas est généré mais PAS relu : on emmène au gate, jamais directement à l'exécution.
        router.push({ name: 'case-detail', params: { pid: pid.value, id: String(job.case_id) } })
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

function addStep() { metier.value.steps.push('') }
function removeStep(i: number) { metier.value.steps.splice(i, 1) }

async function validerMetier() {
  if (!metierComplet.value) return
  error.value = ''
  etape.value = 'gherkin'
  try {
    await api.validateMetier(jobId.value, {
      ...metier.value,
      steps: metier.value.steps.map((s) => s.trim()).filter(Boolean),
    })
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
    <h1 class="text-[26px] font-semibold tracking-tight">Ajouter un cas de test</h1>

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
          <span class="text-sm font-medium">Spécification <span class="text-destructive">*</span></span>
          <textarea v-model="spec" rows="14" required
                    placeholder="Décrivez la fonctionnalité à tester : le parcours, les données attendues, les règles…"
                    class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 font-mono text-[13px] focus:border-primary outline-none"></textarea>
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

    <!-- ══════════ 2. LA PAUSE — validation du document métier ══════════ -->
    <template v-else-if="etape === 'metier'">
      <p class="mt-1 text-sm text-muted-foreground">
        Voici le cas tel que l'IA l'a compris. <strong class="text-foreground">Corrigez ce qui ne
        va pas</strong> — c'est ce document qui servira à écrire le test.
      </p>

      <div class="mt-4 rounded-lg border border-primary/40 bg-primary/[0.05] p-3 text-xs text-muted-foreground">
        Aucun cas n'est encore créé, et le test technique n'est pas encore écrit. C'est le moment
        de corriger : après validation, le test sera généré à partir de ce texte.
      </div>

      <div class="mt-6 space-y-5">
        <label class="block">
          <span class="text-sm font-medium">Titre <span class="text-destructive">*</span></span>
          <input v-model="metier.title"
                 class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        </label>

        <label class="block">
          <span class="text-sm font-medium">Préconditions</span>
          <textarea v-model="metier.preconditions" rows="3"
                    placeholder="Le contexte nécessaire avant de commencer (facultatif)"
                    class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
        </label>

        <div>
          <span class="text-sm font-medium">Étapes <span class="text-destructive">*</span></span>
          <div class="mt-1 space-y-2">
            <div v-for="(_, i) in metier.steps" :key="i" class="flex items-center gap-2">
              <span class="w-6 shrink-0 text-right text-muted-foreground tabular-nums text-sm">{{ i + 1 }}.</span>
              <input v-model="metier.steps[i]"
                     class="flex-1 rounded-md bg-surface-raised border border-border px-3 py-1.5 focus:border-primary outline-none" />
              <button type="button" class="text-muted-foreground hover:text-destructive px-1" title="Supprimer" @click="removeStep(i)">✕</button>
            </div>
          </div>
          <button type="button" class="mt-2 text-sm text-primary hover:underline" @click="addStep">+ Ajouter une étape</button>
        </div>

        <label class="block">
          <span class="text-sm font-medium">Résultat attendu <span class="text-destructive">*</span></span>
          <textarea v-model="metier.expected_result" rows="2"
                    placeholder="Une seule phrase de verdict pour tout le cas"
                    class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
        </label>

        <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
        <p v-if="!metierComplet" class="text-xs text-muted-foreground">
          Titre, au moins une étape et résultat attendu sont nécessaires — un cas sans eux ne
          vérifie rien.
        </p>

        <div class="flex items-center gap-3">
          <button type="button" :disabled="!metierComplet"
                  class="rounded-md bg-primary text-white font-semibold px-4 py-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  @click="validerMetier">
            Valider et générer le test
          </button>
          <button type="button" class="rounded-md border border-border px-4 py-2 hover:border-primary/40" @click="abandonner">Abandonner</button>
        </div>
      </div>
    </template>

    <!-- ══════════ 3. L'ÉCRITURE DU TEST ══════════ -->
    <template v-else>
      <p class="mt-1 text-sm text-muted-foreground">
        Écriture du test technique à partir du cas que vous venez de valider.
      </p>
      <div class="mt-8 flex items-center gap-3 text-sm text-primary">
        <span class="inline-block h-4 w-4 rounded-full border-2 border-primary border-t-transparent animate-spin"></span>
        Génération en cours… (2 à 3 minutes)
      </div>
      <p v-if="error" class="mt-3 text-sm text-destructive">{{ error }}</p>
    </template>
  </div>
</template>
