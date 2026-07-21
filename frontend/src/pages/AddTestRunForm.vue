<script setup lang="ts">
// « Ajouter une exécution de test » — création d'un RUN (campagne de N cas, décision 0022 n°8).
//
// Créer NE LANCE RIEN (8.c.1) : le run naît en brouillon, le lancement est un geste séparé. Deux
// sélections : « tous les cas » (VIVANTE — les nouveaux cas rejoignent) et « cas spécifiques »
// (FIGÉE, transverse multi-modules §7). Le filtrage dynamique est reporté (8.a) et n'est plus
// proposé du tout à l'écran — le serveur le refuse toujours explicitement.
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

// ── Sélection TRANSVERSE (§7) ────────────────────────────────────────────────
// Une exécution nommée peut regrouper des cas de PLUSIEURS modules — c'est le JTBD « régression
// transverse ». Le backend le permet (référence par ID, sans contrainte de module) ; l'écran doit
// le RENDRE VISIBLE, sinon l'utilisateur ne sait pas qu'il peut le faire.
const byModule = computed(() => {
  const map = new Map<string, CaseSummary[]>()
  for (const c of cases.value) {
    const k = c.module || 'Sans module'
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(c)
  }
  return [...map.entries()].map(([module, rows]) => ({ module, rows }))
})
function toggleModule(rows: CaseSummary[]) {
  const ids = rows.map((c) => c.id)
  const tousCoches = ids.every((id) => selected.value.includes(id))
  selected.value = tousCoches
    ? selected.value.filter((id) => !ids.includes(id))
    : [...new Set([...selected.value, ...ids])]
}
// Combien de modules la sélection couvre — pour dire « transverse » quand c'est le cas.
const modulesCouverts = computed(() => {
  const mods = new Set(cases.value.filter((c) => selected.value.includes(c.id))
                                  .map((c) => c.module || 'Sans module'))
  return mods.size
})

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

              <!-- La liste n'apparaît QUE si ce mode est choisi : pas de bruit sinon.
                   Groupée PAR MODULE : une exécution peut être TRANSVERSE (§7) — on le montre. -->
              <div v-if="form.selection === 'frozen'" class="mt-3">
                <div class="flex items-center gap-3 text-xs flex-wrap">
                  <button type="button" class="text-primary hover:underline" @click="selectAll">Tout cocher</button>
                  <button type="button" class="text-primary hover:underline" @click="selectNone">Tout décocher</button>
                  <span class="text-muted-foreground">{{ selected.length }} sélectionné(s)</span>
                  <span v-if="modulesCouverts > 1"
                        class="rounded-full bg-primary/15 text-primary px-2 py-0.5 font-medium">
                    Transverse — {{ modulesCouverts }} modules
                  </span>
                </div>
                <p class="mt-1 text-xs text-muted-foreground">
                  Vous pouvez piocher dans <strong class="text-foreground">plusieurs modules</strong> :
                  c'est ce qui permet une campagne de régression transverse.
                </p>
                <p v-if="!cases.length" class="mt-2 text-xs text-muted-foreground">
                  Aucun cas de test dans ce projet — créez-en un d'abord.
                </p>
                <div v-else class="mt-2 max-h-64 overflow-y-auto rounded-md border border-border">
                  <div v-for="g in byModule" :key="g.module">
                    <button type="button"
                            class="w-full flex items-center gap-2 bg-surface-raised/70 px-3 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground border-b border-border/60"
                            @click="toggleModule(g.rows)">
                      <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
                      {{ g.module }}
                      <span class="ml-auto font-normal normal-case">{{ g.rows.length }} cas — tout (dé)cocher</span>
                    </button>
                    <label v-for="c in g.rows" :key="c.id"
                           class="flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent/30 cursor-pointer border-b border-border/40">
                      <input type="checkbox" :checked="selected.includes(c.id)" @change="toggleCase(c.id)"
                             class="accent-[hsl(var(--primary))]" />
                      <span class="text-muted-foreground tabular-nums text-xs">C{{ c.id }}</span>
                      <span class="truncate">{{ c.title }}</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>
          </label>

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
