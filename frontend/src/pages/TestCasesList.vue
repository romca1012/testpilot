<script setup lang="ts">
// Liste des cas de test — disposition TestRail (palette sombre). Groupée par SECTION = MODULE.
// La colonne « Statut » n'affiche QUE le statut FONCTIONNEL (conforme / non conforme), jamais
// l'exécution technique ni les deux mêlés (consigne du porteur). Titre sans préfixe d'angle.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseSummary, type ModuleSummary } from '../lib/api'
import { testStatusMeta, testStatusCode } from '../lib/status'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const specFilter = computed(() => Number(route.query.spec) || null)

const modules = ref<ModuleSummary[]>([])
const cases = ref<CaseSummary[]>([])
const loading = ref(true)
const collapsed = ref<number[]>([])

async function load() {
  loading.value = true
  const [m, c] = await Promise.all([api.listModules(pid.value), api.listCases(pid.value)])
  modules.value = m
  cases.value = c
  loading.value = false
}
onMounted(load)
watch(pid, load)

// Cases visibles : filtrées par spécification si l'arbre en a sélectionné une.
const visibleCases = computed(() =>
  specFilter.value ? cases.value.filter((c) => c.group_id === specFilter.value) : cases.value)

// Sections = modules qui portent au moins un cas visible.
const sections = computed(() =>
  modules.value
    .map((m) => ({ module: m, rows: visibleCases.value.filter((c) => c.module_id === m.id) }))
    .filter((s) => s.rows.length > 0))

const activeSpecTitle = computed(() => {
  if (!specFilter.value) return null
  return cases.value.find((c) => c.group_id === specFilter.value)?.group_title || null
})

function toggle(mid: number) {
  collapsed.value = collapsed.value.includes(mid)
    ? collapsed.value.filter((x) => x !== mid) : [...collapsed.value, mid]
}
function openCase(id: number) {
  router.push({ name: 'case-detail', params: { pid: pid.value, id: String(id) } })
}
function comingSoon(what: string) { window.alert(`${what} — à venir.`) }

// Barre d'icônes du haut (visuelles). `play` et `ai` ont un accent de couleur.
const topIcons = [
  { d: 'M9 9h11v11H9zM5 15V5a2 2 0 012-2h10', t: 'Dupliquer' },
  { d: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3', t: 'Exporter' },
  { d: 'M3 15v4a2 2 0 002 2h14a2 2 0 002-2v-4M17 8l-5-5-5 5M12 3v12', t: 'Importer' },
  { d: 'M6 9V2h12v7M6 18H4a2 2 0 01-2-2v-5a2 2 0 012-2h16a2 2 0 012 2v5a2 2 0 01-2 2h-2M6 14h12v8H6z', t: 'Imprimer' },
]
</script>

<template>
  <div>
    <!-- En-tête -->
    <div class="flex items-center justify-between px-6 pt-6 pb-2">
      <h1 class="text-[26px] font-semibold tracking-tight">Cas de test</h1>
      <div class="flex items-center gap-3.5 text-muted-foreground">
        <button v-for="ic in topIcons" :key="ic.t" :title="ic.t" class="hover:text-foreground" @click="comingSoon(ic.t)">
          <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path :d="ic.d"/></svg>
        </button>
        <button title="Générer avec l'IA" class="grid place-items-center w-7 h-7 rounded-full bg-success/15 text-success hover:bg-success/25" @click="comingSoon('Génération IA')">
          <svg class="w-[15px] h-[15px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15l-1.9-4.1L5.5 9l4.6-1.4z"/></svg>
        </button>
        <button title="Lancer" class="grid place-items-center w-[30px] h-[30px] rounded-full bg-success text-white hover:bg-success/90" @click="comingSoon('Lancer une exécution')">
          <svg class="w-[15px] h-[15px]" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        </button>
      </div>
    </div>

    <!-- Barre d'outils secondaire -->
    <div class="flex items-center gap-4 px-6 py-2 border-y border-border bg-surface-raised/50 text-xs text-muted-foreground">
      <span>Trier : <button class="text-foreground border-b border-dotted border-muted-foreground" @click="comingSoon('Tri')">Section</button></span>
      <span>Filtre : <button class="text-foreground border-b border-dotted border-muted-foreground" @click="comingSoon('Filtre')">Aucun</button></span>
      <span class="flex-1"></span>
      <span v-if="activeSpecTitle" class="flex items-center gap-1.5 text-primary">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
        {{ activeSpecTitle }}
        <RouterLink :to="{ name: 'cases', params: { pid } }" class="hover:text-foreground" title="Retirer le filtre">✕</RouterLink>
      </span>
    </div>

    <div class="px-6 pb-16">
      <div v-if="loading" class="space-y-2 pt-6">
        <div v-for="i in 3" :key="i" class="h-12 rounded-md bg-secondary animate-pulse"></div>
      </div>

      <p v-else-if="!sections.length" class="pt-10 text-sm text-muted-foreground">
        Aucun cas de test {{ specFilter ? 'dans cette spécification' : 'pour ce projet' }}.
      </p>

      <div v-for="s in sections" :key="s.module.id" class="mt-4">
        <!-- En-tête de section (module) -->
        <div class="flex items-center gap-2.5 py-1.5">
          <button class="text-muted-foreground hover:text-foreground" @click="toggle(s.module.id)">
            <svg class="w-3.5 h-3.5 transition-transform" :class="collapsed.includes(s.module.id) ? '-rotate-90' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"/></svg>
          </button>
          <span class="font-bold italic tracking-tight">{{ s.module.name }}</span>
          <span class="rounded-full bg-primary/15 text-primary text-[11px] font-semibold px-2.5 py-0.5 tabular-nums">{{ s.rows.length }}</span>
          <button class="text-muted-foreground hover:text-foreground" title="Éditer" @click="comingSoon('Éditer la section')">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>
          </button>
        </div>

        <table v-if="!collapsed.includes(s.module.id)" class="w-full border-collapse">
          <thead>
            <tr class="text-[11px] uppercase tracking-wider text-muted-foreground">
              <th class="w-6"></th>
              <th class="w-16 text-left font-semibold py-2 pl-3 relative">
                <span class="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded bg-primary"></span>ID
              </th>
              <th class="text-left font-semibold py-2 px-2.5">Titre</th>
              <th class="w-44 text-right font-semibold py-2 px-2.5">Statut</th>
              <th class="w-8"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in s.rows" :key="c.id" class="group border-t border-border/60 hover:bg-accent/30 cursor-pointer" @click="openCase(c.id)">
              <td class="py-3 pl-1">
                <svg class="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.3"/><circle cx="15" cy="6" r="1.3"/><circle cx="9" cy="12" r="1.3"/><circle cx="15" cy="12" r="1.3"/><circle cx="9" cy="18" r="1.3"/><circle cx="15" cy="18" r="1.3"/></svg>
              </td>
              <td class="py-3 pl-3 font-bold tabular-nums whitespace-nowrap">C{{ c.id }}</td>
              <td class="py-3 px-2.5 text-primary group-hover:underline leading-snug">{{ c.title }}</td>
              <td class="py-3 px-2.5 text-right">
                <span class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12.5px] font-semibold" :class="testStatusMeta(testStatusCode(c.last_execution_status, c.last_functional_status)).badge">
                  {{ testStatusMeta(testStatusCode(c.last_execution_status, c.last_functional_status)).label }}
                </span>
              </td>
              <td class="py-3 text-muted-foreground">
                <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
