<script setup lang="ts">
// « Ajouter un cas de test » — SAISIE MANUELLE, sans IA (décision 0022, correction du porteur
// 2026-07-21). L'humain rédige le document métier : titre, préconditions, étapes, résultat
// attendu. Le cas naît SANS Gherkin — il n'est pas exécutable tant qu'un test technique n'a pas
// été généré. C'est l'inverse du bouton « Générer », qui lance l'IA.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ModuleSummary } from '../lib/api'
import { useGroupes } from '../lib/donnees'
import Button from '../components/ui/Button.vue'
import IconButton from '../components/ui/IconButton.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)

const modules = ref<ModuleSummary[]>([])
const moduleId = ref<number | null>(null)
const NOUVEAU = -1
const newModuleName = ref('')
const creatingModule = computed(() => moduleId.value === NOUVEAU || modules.value.length === 0)

// ── Section CIBLE (2026-09-11) — même patron EXACT que « Générer des cas » (AddTestCase.vue,
// étape 3bis, 2026-08-07) : obligatoire, comme le Module, pour la MÊME raison. Avant ce jour,
// seule la génération IA l'imposait ; la saisie manuelle auto-enveloppait chaque cas dans sa
// propre Section invisible, jamais partagée — un écart entre les deux écrans, pas un choix
// délibéré. Aligner l'un sur l'autre plutôt que d'inventer un troisième patron.
const NOUVELLE_SECTION = -2
const sectionId = ref<number | null>(null)
const newSectionName = ref('')
const { data: groupesData } = useGroupes(pid)
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

const form = ref({ title: '', preconditions: '', steps: [''], expected: '' })
const saving = ref(false)
const error = ref('')

// Titre + au moins une étape + résultat attendu (décision 0022 n°3.c) — un cas sans eux ne
// décrit rien. Préconditions facultatives.
const complet = computed(() =>
  !!form.value.title.trim() && form.value.steps.some((s) => s.trim())
  && !!form.value.expected.trim())

onMounted(async () => {
  modules.value = await api.listModules(pid.value)
  const wanted = Number(route.query.module)
  moduleId.value = modules.value.find((m) => m.id === wanted)?.id ?? modules.value[0]?.id ?? null
  // Section pré-choisie : venue d'un clic sur « Ajouter un cas » DEPUIS une Section précise
  // (TestCasesList.vue) — appel DIRECT plutôt qu'un watch sur `useGroupes` (dont la résolution
  // asynchrone, via le cache vue-query, n'est pas garantie avant que ce bloc s'exécute) : on
  // attend explicitement la réponse, puis on ne retient la Section QUE si elle appartient au
  // module résolu ci-dessus — jamais fait confiance à l'URL seule.
  const wantedSection = Number(route.query.section) || null
  if (wantedSection) {
    const groupes = await api.listGroups(pid.value)
    if (groupes.some((g) => g.id === wantedSection && g.module_id === moduleId.value)) {
      sectionId.value = wantedSection
    }
  }
})

function addStep() { form.value.steps.push('') }
function removeStep(i: number) { form.value.steps.splice(i, 1) }

async function submit() {
  if (!complet.value) return
  saving.value = true
  error.value = ''
  try {
    // Module créé à la demande (un projet neuf n'en a aucun), avant le cas.
    let cible = moduleId.value
    if (creatingModule.value) {
      if (!newModuleName.value.trim()) { saving.value = false; return }
      const m = await api.createModule(pid.value, newModuleName.value.trim())
      modules.value.push(m); cible = m.id; moduleId.value = m.id
    }
    if (!cible) { saving.value = false; return }

    // La Section, même geste que le module : créée à la demande si besoin, obligatoire pour la
    // même raison (échec immédiat et lisible plutôt qu'un cas qui atterrit on ne sait où).
    let groupeCible: number
    if (creatingSection.value) {
      if (!newSectionName.value.trim()) { saving.value = false; return }
      const g = await api.createGroup(cible, { title: newSectionName.value.trim() })
      groupeCible = g.id
    } else if (sectionId.value != null) {
      groupeCible = sectionId.value
    } else {
      saving.value = false; return   // garde-fou : le bouton est désactivé tant que rien n'est choisi
    }

    const c = await api.createManualCase(cible, {
      title: form.value.title.trim(),
      preconditions: form.value.preconditions,
      test_steps: form.value.steps.map((s) => s.trim()).filter(Boolean),
      expected_result: form.value.expected.trim(),
      group_id: groupeCible,
    })
    router.push({ name: 'case-detail', params: { pid: pid.value, id: String(c.id) } })
  } catch (e: any) {
    error.value = e?.message || 'Création impossible.'
  } finally {
    saving.value = false
  }
}

function cancel() { router.push({ name: 'cases', params: { pid: pid.value } }) }
</script>

<template>
  <div class="max-w-[700px]">
    <h1 class="text-2xl font-semibold tracking-tight">Ajouter un cas de test</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Vous rédigez le cas <strong class="text-foreground">à la main</strong>. Pour laisser l'IA le
      générer à partir d'une spécification, utilisez plutôt
      <RouterLink :to="{ name: 'case-new', params: { pid } }" class="text-primary hover:underline">Générer des cas de test</RouterLink>.
    </p>

    <div class="mt-4 rounded-lg border border-border bg-primary/5 p-3 text-xs text-muted-foreground">
      Le cas sera créé avec son contenu métier mais <strong class="text-foreground">sans test
      technique</strong> : il ne pourra pas être exécuté tant que le test n'aura pas été généré.
    </div>

    <form class="mt-6 space-y-5" @submit.prevent="submit">
      <label class="block">
        <span class="text-sm font-medium">Module <span class="text-destructive">*</span></span>
        <select v-if="modules.length" v-model="moduleId"
                class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2">
          <option v-for="m in modules" :key="m.id" :value="m.id">{{ m.name }}</option>
          <option :value="NOUVEAU">+ Créer un module…</option>
        </select>
        <input v-if="creatingModule" v-model="newModuleName" :class="modules.length ? 'mt-2' : 'mt-1'"
               placeholder="Nom du module (ex. Demande de matériel)"
               class="w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        <p v-if="creatingModule && !modules.length" class="mt-1 text-xs text-muted-foreground">
          Ce projet n'a pas encore de module. Donnez-lui un nom pour commencer.
        </p>
      </label>

      <!-- Section CIBLE : même patron exact que « Générer des cas » (AddTestCase.vue) —
           obligatoire, comme le Module. Pré-remplie si on arrive depuis une Section précise de
           l'arbre ; réinitialisée si le Module change (une Section n'existe que sous UN module). -->
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
          Ce module n'a pas encore de section. Donnez-lui un nom pour commencer.
        </p>
      </label>

      <label class="block">
        <span class="text-sm font-medium">Titre <span class="text-destructive">*</span></span>
        <input v-model="form.title" placeholder="Phrase décrivant ce qui est vérifié"
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
      </label>

      <label class="block">
        <span class="text-sm font-medium">Préconditions</span>
        <textarea v-model="form.preconditions" rows="3"
                  placeholder="Le contexte nécessaire avant de commencer (facultatif)"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
      </label>

      <div>
        <span class="text-sm font-medium">Étapes <span class="text-destructive">*</span></span>
        <div class="mt-1 space-y-2">
          <div v-for="(_, i) in form.steps" :key="i" class="flex items-center gap-2">
            <span class="w-6 shrink-0 text-right text-muted-foreground tabular-nums text-sm">{{ i + 1 }}.</span>
            <input v-model="form.steps[i]" placeholder="Action à effectuer"
                   class="flex-1 rounded-md bg-surface-raised border border-border px-3 py-1.5 focus:border-primary outline-none" />
            <IconButton size="sm" variant="danger" label="Supprimer" @click="removeStep(i)">✕</IconButton>
          </div>
        </div>
        <button type="button" class="mt-2 text-sm text-primary hover:underline" @click="addStep">+ Ajouter une étape</button>
      </div>

      <label class="block">
        <span class="text-sm font-medium">Résultat attendu <span class="text-destructive">*</span></span>
        <textarea v-model="form.expected" rows="2" placeholder="Une phrase de verdict pour tout le cas"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
      </label>

      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

      <div class="flex items-center gap-3">
        <Button type="submit" variant="primary" :loading="saving"
                :disabled="saving || !complet
                  || (creatingModule && !newModuleName.trim())
                  || (creatingSection && !newSectionName.trim())
                  || (!creatingSection && sectionId == null)">
          {{ saving ? 'Création…' : 'Créer le cas' }}
        </Button>
        <Button type="button" variant="secondary" @click="cancel">Annuler</Button>
      </div>
    </form>
  </div>
</template>
