<script setup lang="ts">
// Liste des cas de test — disposition TestRail (palette sombre). Groupée par SECTION = MODULE.
// La colonne « Statut » n'affiche QUE le statut FONCTIONNEL (conforme / non conforme), jamais
// l'exécution technique ni les deux mêlés (consigne du porteur). Titre sans préfixe d'angle.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type CaseSummary, type ModuleSummary } from '../lib/api'
import { testStatusMeta, testStatusCode } from '../lib/status'
import { useModuleCreate } from '../lib/useModuleCreate'
import Button from '../components/ui/Button.vue'

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

// ── Création d'un module (modale partagée, rendue par CasesShell) ──────────────
// On ne fait que DÉCLENCHER l'ouverture et ÉCOUTER le succès : la modale unique vit dans le shell
// (qui porte aussi le « + Ajouter une section » de la barre latérale). `createdAt` bumpe après une
// création → on recharge pour voir le nouveau module (vide, donc invisible sans le rechargement).
const { openFor: openCreateModule, createdAt } = useModuleCreate()
watch(createdAt, load)

// Tri et filtre CÔTÉ CLIENT (préférences de lecture, pas de rechargement).
const sortKey = ref<'id' | 'title' | 'status'>('id')
const filterStatus = ref('')  // '' = tous

function statusOf(c: CaseSummary) {
  return testStatusCode(c.last_execution_status, c.last_functional_status)
}

// Cases visibles : filtrées par spécification (arbre) PUIS par statut (barre d'outils).
const visibleCases = computed(() => {
  let list = specFilter.value ? cases.value.filter((c) => c.group_id === specFilter.value) : cases.value
  if (filterStatus.value) list = list.filter((c) => statusOf(c) === filterStatus.value)
  return list
})

function sortRows(rows: CaseSummary[]): CaseSummary[] {
  const copy = [...rows]
  if (sortKey.value === 'title') copy.sort((a, b) => a.title.localeCompare(b.title))
  else if (sortKey.value === 'status') copy.sort((a, b) => statusOf(a).localeCompare(statusOf(b)))
  else copy.sort((a, b) => a.id - b.id)
  return copy
}

// Sections = modules avec leurs cas visibles. On MONTRE les modules vides quand aucun filtre n'est
// actif — sinon un module qu'on vient de créer resterait invisible (et l'écran mentirait sur la
// structure). Sous un filtre (spec/statut), on masque au contraire ce qui n'a rien à montrer.
const sections = computed(() => {
  const filtering = !!specFilter.value || !!filterStatus.value
  return modules.value
    .map((m) => ({ module: m, rows: sortRows(visibleCases.value.filter((c) => c.module_id === m.id)) }))
    .filter((s) => !filtering || s.rows.length > 0)
})

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

// Renommer un module (« Éditer la section »). Prompt simple : une seule valeur, pas besoin d'une
// modale. Le serveur refuse un nom déjà pris (409) — on remonte le message.
async function renameSection(m: ModuleSummary) {
  const nom = window.prompt('Renommer le module', m.name)
  if (!nom || !nom.trim() || nom.trim() === m.name) return
  try {
    await api.renameModule(m.id, nom.trim())
    await load()
  } catch (e: any) {
    window.alert(e?.message || 'Renommage impossible.')
  }
}

// Barre d'icônes du haut. « Importer » retiré (décision porteur) ; « Exporter » branché (CSV).
const topIcons = [
  { d: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3', t: 'Exporter (CSV)' },
]
function topAction(t: string) {
  if (t.startsWith('Exporter')) return exportCsv()
  comingSoon(t)
}

// Export CSV des cas visibles — universel (Excel, partage avec la QA non technique). Côté client :
// les données sont déjà chargées, aucun aller-retour serveur. Un champ contenant `;`/`"`/saut de
// ligne est échappé (guillemets doublés) — sinon le CSV se décale silencieusement.
function csvCell(v: unknown): string {
  const s = String(v ?? '')
  return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}
function exportCsv() {
  const entetes = ['ID', 'Titre', 'Module', 'Type', 'Priorité', 'Statut']
  const lignes = visibleCases.value.map((c) => [
    `C${c.id}`, c.title, c.module || '', c.angle || '', c.priority || '',
    testStatusMeta(testStatusCode(c.last_execution_status, c.last_functional_status)).label,
  ].map(csvCell).join(';'))
  // BOM UTF-8 : sans lui, Excel lit « é » de travers.
  const contenu = '﻿' + [entetes.join(';'), ...lignes].join('\r\n')
  const blob = new Blob([contenu], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cas-de-test-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
function goRunNew() { router.push({ name: 'run-new', params: { pid: pid.value } }) }
</script>

<template>
  <div>
    <!-- En-tête -->
    <div class="flex items-center justify-between px-6 pt-6 pb-2">
      <h1 class="text-[26px] font-semibold tracking-tight">Cas de test</h1>
      <div class="flex items-center gap-3.5 text-muted-foreground">
        <button title="Nouveau module" class="hover:text-foreground" @click="openCreateModule(pid)">
          <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M12 10v5M9.5 12.5h5"/></svg>
        </button>
        <button v-for="ic in topIcons" :key="ic.t" :title="ic.t" class="hover:text-foreground" @click="topAction(ic.t)">
          <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path :d="ic.d"/></svg>
        </button>
        <button title="Générer des cas de test avec l'IA" class="grid place-items-center w-7 h-7 rounded-full bg-success/15 text-success hover:bg-success/25"
                @click="router.push({ name: 'case-new', params: { pid } })">
          <svg class="w-[15px] h-[15px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15l-1.9-4.1L5.5 9l4.6-1.4z"/></svg>
        </button>
        <button title="Lancer une exécution (créer un run)" class="grid place-items-center w-[30px] h-[30px] rounded-full bg-success text-white hover:bg-success/90" @click="goRunNew">
          <svg class="w-[15px] h-[15px]" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        </button>
      </div>
    </div>

    <!-- Barre d'outils secondaire — tri et filtre CÔTÉ CLIENT (les cas sont déjà chargés). -->
    <div class="flex items-center gap-4 px-6 py-2 border-y border-border bg-surface-raised/50 text-xs text-muted-foreground">
      <label class="flex items-center gap-1.5">Trier :
        <select v-model="sortKey" class="bg-transparent text-foreground border-b border-dotted border-muted-foreground outline-none cursor-pointer">
          <option value="id">ID</option>
          <option value="title">Titre</option>
          <option value="status">Statut</option>
        </select>
      </label>
      <label class="flex items-center gap-1.5">Filtre :
        <select v-model="filterStatus" class="bg-transparent text-foreground border-b border-dotted border-muted-foreground outline-none cursor-pointer">
          <option value="">Tous</option>
          <option value="passed">Passed</option>
          <option value="failed">Failed</option>
          <option value="retest">Retest</option>
          <option value="blocked">Blocked</option>
          <option value="untested">Untested</option>
        </select>
      </label>
      <span class="flex-1"></span>
      <span v-if="activeSpecTitle" class="flex items-center gap-1.5 text-primary">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
        {{ activeSpecTitle }}
        <!-- Filtrer sur une spécification et pouvoir LIRE cette spécification sont deux besoins
             distincts : la liste montre ses cas, le lien montre le document dont ils sont nés. -->
        <RouterLink :to="{ name: 'spec-detail', params: { pid, id: String(specFilter) } }"
                    class="hover:underline" title="Ouvrir la spécification">voir le document</RouterLink>
        <RouterLink :to="{ name: 'cases', params: { pid } }" class="hover:text-foreground" title="Retirer le filtre">✕</RouterLink>
      </span>
    </div>

    <div class="px-6 pb-16">
      <div v-if="loading" class="space-y-2 pt-6">
        <div v-for="i in 3" :key="i" class="h-12 rounded-md bg-secondary animate-pulse"></div>
      </div>

      <div v-else-if="!sections.length" class="flex flex-col items-center gap-3 pt-16 text-center">
        <p class="text-sm text-muted-foreground">
          {{ specFilter || filterStatus ? 'Aucun cas de test ne correspond au filtre.' : 'Aucun module dans ce projet.' }}
        </p>
        <Button v-if="!specFilter && !filterStatus" variant="primary" @click="openCreateModule(pid)">Créer le premier module</Button>
      </div>

      <div v-for="s in sections" :key="s.module.id" class="mt-4">
        <!-- En-tête de section (module) -->
        <div class="flex items-center gap-2.5 py-1.5">
          <button class="text-muted-foreground hover:text-foreground" @click="toggle(s.module.id)">
            <svg class="w-3.5 h-3.5 transition-transform" :class="collapsed.includes(s.module.id) ? '-rotate-90' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"/></svg>
          </button>
          <span class="font-bold italic tracking-tight">{{ s.module.name }}</span>
          <span class="rounded-full bg-primary/15 text-primary text-[11px] font-semibold px-2.5 py-0.5 tabular-nums">{{ s.rows.length }}</span>
          <button class="text-muted-foreground hover:text-foreground" title="Renommer le module" @click="renameSection(s.module)">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>
          </button>
        </div>

        <p v-if="!collapsed.includes(s.module.id) && !s.rows.length"
           class="pl-8 py-2 text-xs italic text-muted-foreground/70">
          Aucun cas dans ce module — générez-en avec l'IA ou ajoutez-en un.
        </p>

        <table v-if="!collapsed.includes(s.module.id) && s.rows.length" class="w-full border-collapse">
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
