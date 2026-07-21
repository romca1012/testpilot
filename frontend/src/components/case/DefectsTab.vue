<script setup lang="ts">
// Onglet « Défauts » — vraies données. Compteurs dérivés des exécutions réelles + barres SVG.
// Liste vide HONNÊTE : aucun défaut formel n'est lié aux cas 9/10 (ils sont non_conforme, mais
// aucun `vrai_bug` confirmé n'y est rattaché). La structure de liste est prête pour le futur.
import { computed } from 'vue'
import type { ExecutionSummary } from '../../lib/api'

const props = defineProps<{ executions: ExecutionSummary[] }>()

const testsStarted = computed(() => props.executions.length)
const resultsAdded = computed(() => props.executions.reduce((a, e) => a + (e.scenarios_total || 0), 0))
const defectsLinked = 0 // aucun défaut lié en base pour ce cas — état réel

const metrics = computed(() => [
  { key: 'tests', label: 'Tests', value: testsStarted.value, note: `${testsStarted.value} test${testsStarted.value > 1 ? 's' : ''} commencé${testsStarted.value > 1 ? 's' : ''}.`, color: 'var(--untested)' },
  { key: 'results', label: 'Résultats', value: resultsAdded.value, note: `${resultsAdded.value} résultat${resultsAdded.value > 1 ? 's' : ''} de test ajouté${resultsAdded.value > 1 ? 's' : ''}.`, color: 'var(--warning)' },
  { key: 'defects', label: 'Défauts', value: defectsLinked, note: `${defectsLinked} défaut enregistré.`, color: 'var(--destructive)' },
])
const barMax = computed(() => Math.max(1, ...metrics.value.map((m) => m.value)))

const W = 320, BH = 22, GAP = 18, PAD_L = 4, PAD_R = 30
function barW(v: number) { return (v / barMax.value) * (W - PAD_L - PAD_R) }
function soon(w: string) { window.alert(`${w} — à venir.`) }
</script>

<template>
  <div class="space-y-8">
    <!-- Vue d'ensemble -->
    <div class="rounded-lg border border-border bg-surface-raised/40 p-5 flex flex-col lg:flex-row items-center gap-8">
      <!-- gros chiffre -->
      <div class="text-center shrink-0">
        <div class="text-5xl font-bold tabular-nums">{{ defectsLinked }}</div>
        <div class="text-sm text-muted-foreground mt-1">Défauts</div>
      </div>

      <!-- barres -->
      <div class="flex-1 min-w-0 w-full">
        <svg :viewBox="`0 0 ${W} ${metrics.length * (BH + GAP)}`" class="w-full h-auto">
          <g v-for="(m, i) in metrics" :key="m.key" :transform="`translate(0 ${i * (BH + GAP)})`">
            <rect :x="PAD_L" y="0" :width="W - PAD_L - PAD_R" :height="BH" rx="4" fill="hsl(var(--border))" opacity="0.3" />
            <rect :x="PAD_L" y="0" :width="barW(m.value)" :height="BH" rx="4" :fill="`hsl(${m.color})`" />
            <text :x="PAD_L + Math.max(barW(m.value), 4) + 8" :y="BH / 2 + 4" fill="hsl(var(--foreground))" font-size="12" font-weight="600" class="tabular-nums">{{ m.value }}</text>
          </g>
        </svg>
      </div>

      <!-- stats -->
      <div class="lg:w-56 shrink-0 w-full">
        <div class="flex items-center justify-between">
          <p class="text-sm text-muted-foreground">Tests et défauts :</p>
          <div class="flex items-center gap-2 text-muted-foreground">
            <button title="Exporter en image" class="hover:text-foreground" @click="soon('Export image')"><svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 15l5-5 4 4 3-3 6 6"/></svg></button>
            <button title="Exporter en CSV" class="hover:text-foreground" @click="soon('Export CSV')"><svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3v4a1 1 0 001 1h4M9 13v5m3-3l-3 3-3-3M8 3h6l5 5v11a2 2 0 01-2 2H8a2 2 0 01-2-2V5a2 2 0 012-2z"/></svg></button>
          </div>
        </div>
        <ul class="mt-3 space-y-3">
          <li v-for="m in metrics" :key="m.key">
            <div class="flex items-center gap-2">
              <span class="h-2.5 w-2.5 rounded-full shrink-0" :style="{ background: `hsl(${m.color})` }"></span>
              <span class="font-semibold">{{ m.label }}</span>
            </div>
            <p class="pl-[18px] ml-0.5 text-xs text-muted-foreground">{{ m.note }}</p>
          </li>
        </ul>
      </div>
    </div>

    <!-- Liste des défauts -->
    <section>
      <h2 class="text-lg font-semibold border-b border-border pb-2">Défauts</h2>
      <div class="py-10 text-center">
        <p class="text-sm">Aucun défaut jusqu'à présent.</p>
        <p class="mt-2 text-xs text-muted-foreground max-w-lg mx-auto">
          Les défauts peuvent être liés dans la boîte de dialogue « Ajouter un résultat » lors de
          l'ajout de résultats pour ce cas (onglet « Exécutions et résultats de test »).
        </p>
      </div>
    </section>
  </div>
</template>
