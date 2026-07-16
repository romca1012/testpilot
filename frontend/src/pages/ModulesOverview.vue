<script setup lang="ts">
/**
 * Première vue d'un projet : sa STRUCTURE — les modules — et non un mur de cas.
 *
 * Le référentiel s'organise Projet → Module → Cas (décision 0004), mais aucune vue ne rendait
 * ce niveau : on tombait sur la table plate de tous les cas, où le module n'était qu'un
 * sous-titre. On voit désormais de quoi le projet est fait, puis on ouvre un module pour ses cas.
 *
 * La table transverse n'est pas perdue : elle reste accessible en « Tous les cas ».
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, type CaseSummary, type ModuleSummary } from '../lib/api'
import { prettyModule } from '../lib/status'
import Icon from '../components/ui/Icon.vue'

const route = useRoute()
const pid = computed(() => route.params.pid as string)

const modules = ref<ModuleSummary[]>([])
const cases = ref<CaseSummary[]>([])
const loading = ref(true)
const error = ref('')

// Grille (cartes) ou liste compacte. Préférence retenue par utilisateur : la re-choisir à
// chaque visite ferait perdre son intérêt à l'option. Purement visuel — aucune donnée en jeu.
type Vue = 'grid' | 'list'
const VUE_KEY = 'tp.modules.view'
const vue = ref<Vue>('grid')

onMounted(() => {
  try {
    const saved = localStorage.getItem(VUE_KEY)
    if (saved === 'grid' || saved === 'list') vue.value = saved
  } catch { /* stockage indisponible : la grille par défaut reste correcte */ }
})

function setVue(v: Vue) {
  vue.value = v
  try { localStorage.setItem(VUE_KEY, v) } catch { /* préférence d'affichage : jamais bloquant */ }
}

onMounted(async () => {
  try {
    const [m, c] = await Promise.all([api.listModules(pid.value), api.listCases(pid.value)])
    modules.value = m
    cases.value = c
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
})

/** Compteurs par module, calculés sur les cas RÉELS — jamais un nombre que la liste du module
 *  contredirait ensuite. `à relire` est le seul chiffre mis en avant : c'est le seul qui appelle
 *  une action humaine (le gate, invariant 4.3). */
const statsOf = (moduleId: number) => {
  const mine = cases.value.filter((c) => c.module_id === moduleId)
  return { total: mine.length, toReview: mine.filter((c) => c.validation_status === 'to_review').length }
}
const orphanCount = computed(() => cases.value.filter((c) => c.module_id == null).length)
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Modules</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          La structure du projet. Ouvrez un module pour voir et gérer ses cas de test.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Bascule grille / liste — affichage seulement. -->
        <div class="inline-flex rounded-md border border-border p-0.5" role="group" aria-label="Affichage">
          <button
            v-for="opt in ([{ v: 'grid', label: 'Grille' }, { v: 'list', label: 'Liste' }] as const)"
            :key="opt.v" :aria-pressed="vue === opt.v"
            class="rounded px-2 py-1 text-xs transition-colors"
            :class="vue === opt.v ? 'bg-primary/15 text-foreground' : 'text-muted-foreground hover:text-foreground'"
            @click="setVue(opt.v)"
          >
            {{ opt.label }}
          </button>
        </div>
        <RouterLink :to="`/projects/${pid}/cases/all`"
                    class="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground">
          Tous les cas
          <Icon name="chevron" class="h-3 w-3" />
        </RouterLink>
      </div>
    </header>

    <div v-if="loading" class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <div v-for="i in 3" :key="i" class="h-28 rounded-xl border border-border bg-card animate-pulse" />
    </div>

    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>

    <div v-else-if="!modules.length"
         class="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-5 py-16 text-center">
      <div class="grid h-12 w-12 place-items-center rounded-full border border-border bg-surface text-muted-foreground">
        <Icon name="circle" class="h-5 w-5" />
      </div>
      <p class="text-sm text-muted-foreground">Aucun module dans ce projet.</p>
    </div>

    <!-- Vue LISTE : compacte, lisible quand les modules se multiplient. Mêmes informations que
         la grille — c'est la densité qui change, pas le contenu. -->
    <ul v-else-if="vue === 'list'" class="divide-y divide-border rounded-xl border border-border bg-card">
      <li v-for="m in modules" :key="m.id">
        <RouterLink :to="`/projects/${pid}/modules/${m.id}`"
                    class="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-accent/30">
          <Icon name="folder" class="h-4 w-4 shrink-0 text-muted-foreground" />
          <div class="min-w-0 flex-1">
            <div class="truncate text-sm font-medium">{{ prettyModule(m.name) }}</div>
            <p v-if="m.description" class="truncate text-xs text-muted-foreground">{{ m.description }}</p>
          </div>
          <span class="shrink-0 text-xs tabular-nums text-muted-foreground">{{ statsOf(m.id).total }} cas</span>
          <span v-if="statsOf(m.id).toReview"
                class="shrink-0 rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-xs text-warning">
            {{ statsOf(m.id).toReview }} à relire
          </span>
          <Icon name="chevron" class="h-4 w-4 shrink-0 text-muted-foreground/30 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
        </RouterLink>
      </li>
    </ul>

    <div v-else class="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      <RouterLink
        v-for="m in modules" :key="m.id" :to="`/projects/${pid}/modules/${m.id}`"
        class="group flex flex-col gap-3 rounded-xl border border-border bg-card p-4 transition-colors hover:border-primary/40"
      >
        <div class="flex items-start gap-3">
          <div class="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-border bg-surface text-muted-foreground">
            <Icon name="folder" class="h-4 w-4" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="truncate font-medium">{{ prettyModule(m.name) }}</div>
            <p v-if="m.description" class="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
              {{ m.description }}
            </p>
          </div>
          <Icon name="chevron" class="h-4 w-4 shrink-0 text-muted-foreground/30 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
        </div>

        <div class="flex items-center gap-3 text-xs text-muted-foreground">
          <span class="tabular-nums">
            {{ statsOf(m.id).total }} cas{{ statsOf(m.id).total > 1 ? '' : '' }}
          </span>
          <!-- Seul chiffre mis en avant : ce qui attend une décision humaine. -->
          <span v-if="statsOf(m.id).toReview"
                class="rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-warning">
            {{ statsOf(m.id).toReview }} à relire
          </span>
        </div>
      </RouterLink>
    </div>

    <p v-if="!loading && orphanCount" class="text-xs text-muted-foreground">
      {{ orphanCount }} cas sans module — visible dans l'arbre et dans
      <RouterLink :to="`/projects/${pid}/cases/all`" class="text-primary hover:underline">tous les cas</RouterLink>.
    </p>
  </div>
</template>
