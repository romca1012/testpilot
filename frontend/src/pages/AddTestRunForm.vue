<script setup lang="ts">
// « Ajouter une exécution de test » — création d'un RUN (campagne de N cas, décision 0022 n°8).
//
// Créer NE LANCE RIEN (8.c.1) : le run naît en brouillon, le lancement est un geste séparé. Deux
// sélections seulement : « tous les cas » (VIVANTE — les nouveaux cas rejoignent) et « cas
// spécifiques » (FIGÉE). Le filtrage dynamique est REPORTÉ (8.a) : on le dit, on ne le simule pas.
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseSummary } from '../lib/api'

const route = useRoute()
const router = useRouter()
const pid = route.params.pid as string

const today = new Date().toISOString().slice(0, 10)
const form = ref({
  name: `Exécution de test ${today}`,
  refs: '',
  description: '',
  selection: 'all' as 'all' | 'frozen',
})

const cases = ref<CaseSummary[]>([])
const selected = ref<number[]>([])
const saving = ref(false)
const error = ref('')

onMounted(async () => {
  try { cases.value = await api.listCases(pid) } catch { cases.value = [] }
})

const canSubmit = computed(() =>
  !!form.value.name.trim()
  && (form.value.selection === 'all' || selected.value.length > 0))

function toggleCase(id: number) {
  selected.value = selected.value.includes(id)
    ? selected.value.filter((x) => x !== id) : [...selected.value, id]
}
function selectAll() { selected.value = cases.value.map((c) => c.id) }
function selectNone() { selected.value = [] }

async function submit() {
  if (!canSubmit.value) return
  saving.value = true
  error.value = ''
  try {
    const run = await api.createRun(pid, {
      name: form.value.name.trim(),
      description: form.value.description,
      refs: form.value.refs,
      selection_mode: form.value.selection,
      case_ids: form.value.selection === 'frozen' ? selected.value : [],
    })
    router.push({ name: 'run-detail', params: { pid, id: String(run.id) } })
  } catch (e: any) {
    error.value = e?.message || 'Création impossible.'
  } finally {
    saving.value = false
  }
}
function cancel() { router.push({ name: 'executions', params: { pid } }) }
</script>

<template>
  <div class="max-w-[700px]">
    <h1 class="text-2xl font-semibold tracking-tight">Ajouter une exécution de test</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Une exécution regroupe les cas à jouer ensemble. Elle est créée
      <strong class="text-foreground">sans être lancée</strong> — vous la lancerez depuis sa page.
    </p>

    <form class="mt-6 space-y-5" @submit.prevent="submit">
      <label class="block">
        <span class="text-sm font-medium">Nom <span class="text-destructive">*</span></span>
        <input v-model="form.name" required
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        <span class="text-xs text-muted-foreground">Ex. : Recette 2026-07, Build 240 ou Version 3.0</span>
      </label>

      <label class="block">
        <span class="text-sm font-medium">Références</span>
        <textarea v-model="form.refs" rows="2" placeholder="JIRA-123, …"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
        <span class="text-xs text-muted-foreground">Tickets externes liés à cette campagne.</span>
      </label>

      <label class="block">
        <span class="text-sm font-medium">Description</span>
        <textarea v-model="form.description" rows="3"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
      </label>

      <!-- Sélection des cas -->
      <div>
        <span class="text-sm font-medium">Sélection des cas de test <span class="text-destructive">*</span></span>
        <div class="mt-2 space-y-2">
          <label class="flex gap-3 rounded-md border p-3 cursor-pointer transition-colors"
                 :class="form.selection === 'all' ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'">
            <input type="radio" value="all" v-model="form.selection" class="mt-1 accent-[hsl(var(--primary))]" />
            <div>
              <div class="text-sm font-medium">Inclure tous les cas de test</div>
              <p class="text-xs text-muted-foreground mt-0.5">
                Sélection <strong class="text-foreground">vivante</strong> : les cas créés après coup
                rejoignent automatiquement cette exécution. ({{ cases.length }} cas aujourd'hui.)
              </p>
            </div>
          </label>

          <label class="flex gap-3 rounded-md border p-3 cursor-pointer transition-colors"
                 :class="form.selection === 'frozen' ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'">
            <input type="radio" value="frozen" v-model="form.selection" class="mt-1 accent-[hsl(var(--primary))]" />
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium">Sélectionner des cas de test spécifiques</div>
              <p class="text-xs text-muted-foreground mt-0.5">
                Sélection <strong class="text-foreground">figée</strong> : aucun ajout automatique ensuite.
              </p>

              <!-- La liste n'apparaît QUE si ce mode est choisi : pas de bruit sinon. -->
              <div v-if="form.selection === 'frozen'" class="mt-3">
                <div class="flex items-center gap-3 text-xs">
                  <button type="button" class="text-primary hover:underline" @click="selectAll">Tout cocher</button>
                  <button type="button" class="text-primary hover:underline" @click="selectNone">Tout décocher</button>
                  <span class="text-muted-foreground">{{ selected.length }} sélectionné(s)</span>
                </div>
                <p v-if="!cases.length" class="mt-2 text-xs text-muted-foreground">
                  Aucun cas de test dans ce projet — créez-en un d'abord.
                </p>
                <div v-else class="mt-2 max-h-56 overflow-y-auto rounded-md border border-border divide-y divide-border/60">
                  <label v-for="c in cases" :key="c.id"
                         class="flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent/30 cursor-pointer">
                    <input type="checkbox" :checked="selected.includes(c.id)" @change="toggleCase(c.id)"
                           class="accent-[hsl(var(--primary))]" />
                    <span class="text-muted-foreground tabular-nums text-xs">C{{ c.id }}</span>
                    <span class="truncate">{{ c.title }}</span>
                  </label>
                </div>
              </div>
            </div>
          </label>

          <!-- Filtrage dynamique : REPORTÉ (0022 8.a). Affiché désactivé et EXPLIQUÉ, plutôt que
               proposé puis refusé par le serveur (« affiché ≠ réel »). -->
          <div class="flex gap-3 rounded-md border border-border/60 p-3 opacity-50">
            <input type="radio" disabled class="mt-1" />
            <div>
              <div class="text-sm font-medium">Filtrage dynamique <span class="text-xs font-normal">(pas encore disponible)</span></div>
              <p class="text-xs text-muted-foreground mt-0.5">
                Les cas rejoindraient l'exécution selon des critères. Reporté : cela demande de
                réévaluer chaque exécution à chaque modification de cas.
              </p>
            </div>
          </div>
        </div>
      </div>

      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

      <div class="flex items-center gap-3 pt-2">
        <button type="submit" :disabled="saving || !canSubmit"
                class="rounded-md bg-success text-white font-semibold px-4 py-2 flex items-center gap-2 hover:bg-success/90 disabled:opacity-50 disabled:cursor-not-allowed">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 12.5l4.2 4.2L19 6.8"/></svg>
          {{ saving ? 'Création…' : 'Ajouter une exécution de test' }}
        </button>
        <button type="button" class="rounded-md border border-border px-4 py-2 hover:border-primary/40" @click="cancel">Annuler</button>
      </div>
    </form>
  </div>
</template>
