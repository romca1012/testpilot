<script setup lang="ts">
// « Ajouter un cas de test » — SAISIE MANUELLE, sans IA (décision 0022, correction du porteur
// 2026-07-21). L'humain rédige le document métier : titre, préconditions, étapes, résultat
// attendu. Le cas naît SANS Gherkin — il n'est pas exécutable tant qu'un test technique n'a pas
// été généré. C'est l'inverse du bouton « Générer », qui lance l'IA.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ModuleSummary } from '../lib/api'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)

const modules = ref<ModuleSummary[]>([])
const moduleId = ref<number | null>(null)
const NOUVEAU = -1
const newModuleName = ref('')
const creatingModule = computed(() => moduleId.value === NOUVEAU || modules.value.length === 0)

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
    const c = await api.createManualCase(cible, {
      title: form.value.title.trim(),
      preconditions: form.value.preconditions,
      test_steps: form.value.steps.map((s) => s.trim()).filter(Boolean),
      expected_result: form.value.expected.trim(),
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
  <div class="p-6 md:p-8 max-w-[760px]">
    <h1 class="text-[26px] font-semibold tracking-tight">Ajouter un cas de test</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Vous rédigez le cas <strong class="text-foreground">à la main</strong>. Pour laisser l'IA le
      générer à partir d'une spécification, utilisez plutôt
      <RouterLink :to="{ name: 'case-new', params: { pid } }" class="text-primary hover:underline">Générer des cas de test</RouterLink>.
    </p>

    <div class="mt-4 rounded-lg border border-border bg-primary/[0.04] p-3 text-xs text-muted-foreground">
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
            <button type="button" class="text-muted-foreground hover:text-destructive px-1" title="Supprimer" @click="removeStep(i)">✕</button>
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
        <button type="submit" :disabled="saving || !complet"
                class="rounded-md bg-primary text-white font-semibold px-4 py-2 disabled:opacity-60">
          {{ saving ? 'Création…' : 'Créer le cas' }}
        </button>
        <button type="button" class="rounded-md border border-border px-4 py-2 hover:border-primary/40" @click="cancel">Annuler</button>
      </div>
    </form>
  </div>
</template>
