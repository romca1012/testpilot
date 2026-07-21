<script setup lang="ts">
// Activité des 30 derniers jours — DÉRIVÉE des vraies exécutions du cas (pas de mock). Courbe
// SVG légère (aucune librairie). Une série par statut FONCTIONNEL, activable via la légende.
import { computed, ref } from 'vue'
import type { ExecutionSummary } from '../../lib/api'

const props = defineProps<{ executions: ExecutionSummary[] }>()

// Statuts fonctionnels réels du projet → couleurs. (On reste sur l'axe fonctionnel, cohérent
// avec la colonne « Statut » de la liste.)
const SERIES = [
  { key: 'conforme', label: 'Conforme', color: 'var(--success)' },
  { key: 'non_conforme', label: 'Non conforme', color: 'var(--destructive)' },
  { key: 'indetermine', label: 'Indéterminé', color: 'var(--warning)' },
] as const
type Key = typeof SERIES[number]['key']

const active = ref<Set<Key>>(new Set(SERIES.map((s) => s.key)))
function toggle(k: Key) {
  const n = new Set(active.value)
  n.has(k) ? n.delete(k) : n.add(k)
  active.value = n
}

const DAYS = 30
// 30 seaux journaliers (aujourd'hui inclus), remontés depuis les dates réelles.
const buckets = computed(() => {
  const days: { date: Date; counts: Record<Key, number> }[] = []
  const today = new Date(); today.setHours(0, 0, 0, 0)
  for (let i = DAYS - 1; i >= 0; i--) {
    const d = new Date(today); d.setDate(today.getDate() - i)
    days.push({ date: d, counts: { conforme: 0, non_conforme: 0, indetermine: 0 } })
  }
  for (const e of props.executions) {
    if (!e.started_at) continue
    const d = new Date(e.started_at); d.setHours(0, 0, 0, 0)
    const idx = Math.round((d.getTime() - days[0].date.getTime()) / 86400000)
    if (idx < 0 || idx >= DAYS) continue
    const k = e.functional_status as Key
    if (k in days[idx].counts) days[idx].counts[k]++
  }
  return days
})

const totals = computed<Record<Key, number>>(() => {
  const t: Record<Key, number> = { conforme: 0, non_conforme: 0, indetermine: 0 }
  for (const b of buckets.value) for (const s of SERIES) t[s.key] += b.counts[s.key]
  return t
})
const grandTotal = computed(() => SERIES.reduce((a, s) => a + totals.value[s.key], 0))

// Géométrie SVG.
const W = 620, H = 180, PAD_L = 28, PAD_B = 22, PAD_T = 10, PAD_R = 8
const yMax = computed(() => Math.max(1, ...buckets.value.flatMap((b) => SERIES.map((s) => b.counts[s.key]))))
function x(i: number) { return PAD_L + (i / (DAYS - 1)) * (W - PAD_L - PAD_R) }
function y(v: number) { return PAD_T + (1 - v / yMax.value) * (H - PAD_T - PAD_B) }
function path(k: Key) {
  return buckets.value.map((b, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(b.counts[k]).toFixed(1)}`).join(' ')
}
function pointsWithValue(k: Key) {
  return buckets.value.map((b, i) => ({ i, v: b.counts[k] })).filter((p) => p.v > 0)
}
// Étiquettes d'axe X : ~5 dates réparties.
const xLabels = computed(() =>
  [0, 7, 14, 21, 29].map((i) => ({ i, label: `${buckets.value[i].date.getDate()}/${buckets.value[i].date.getMonth() + 1}` })))
const yTicks = computed(() => {
  const m = yMax.value
  return Array.from(new Set([0, Math.ceil(m / 2), m]))
})
function pct(k: Key) { return grandTotal.value ? Math.round((totals.value[k] / grandTotal.value) * 100) : 0 }
function soon(w: string) { window.alert(`${w} — à venir.`) }
</script>

<template>
  <div class="rounded-lg border border-border bg-surface-raised/40 p-4 flex flex-col lg:flex-row gap-6">
    <!-- Courbe -->
    <div class="flex-1 min-w-0">
      <svg :viewBox="`0 0 ${W} ${H}`" class="w-full h-auto" role="img" aria-label="Activité des tests sur 30 jours">
        <!-- grille horizontale + axes Y -->
        <g v-for="t in yTicks" :key="t">
          <line :x1="PAD_L" :x2="W - PAD_R" :y1="y(t)" :y2="y(t)" stroke="hsl(var(--border))" stroke-width="1" :stroke-dasharray="t === 0 ? '0' : '3 4'" />
          <text :x="PAD_L - 6" :y="y(t) + 3" text-anchor="end" fill="hsl(var(--muted-foreground))" font-size="10">{{ t }}</text>
        </g>
        <!-- séries -->
        <template v-for="s in SERIES" :key="s.key">
          <g v-if="active.has(s.key)">
            <path :d="path(s.key)" fill="none" :stroke="`hsl(${s.color})`" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
            <circle v-for="p in pointsWithValue(s.key)" :key="p.i" :cx="x(p.i)" :cy="y(p.v)" r="3" :fill="`hsl(${s.color})`" />
          </g>
        </template>
        <!-- étiquettes X -->
        <text v-for="l in xLabels" :key="l.i" :x="x(l.i)" :y="H - 6" text-anchor="middle" fill="hsl(var(--muted-foreground))" font-size="10">{{ l.label }}</text>
      </svg>
    </div>

    <!-- Panneau de stats -->
    <div class="lg:w-56 shrink-0">
      <div class="flex items-center justify-between">
        <p class="text-sm text-muted-foreground">Au cours des 30 derniers jours :</p>
        <div class="flex items-center gap-2 text-muted-foreground">
          <button title="Exporter en image" class="hover:text-foreground" @click="soon('Export image')"><svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 15l5-5 4 4 3-3 6 6"/></svg></button>
          <button title="Exporter en CSV" class="hover:text-foreground" @click="soon('Export CSV')"><svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 3v4a1 1 0 001 1h4M9 13v5m3-3l-3 3-3-3M8 3h6l5 5v11a2 2 0 01-2 2H8a2 2 0 01-2-2V5a2 2 0 012-2z"/></svg></button>
        </div>
      </div>
      <ul class="mt-3 space-y-3">
        <li v-for="s in SERIES" :key="s.key">
          <button class="flex items-center gap-2 w-full text-left" :class="!active.has(s.key) && 'opacity-40'" @click="toggle(s.key)">
            <span class="h-2.5 w-2.5 rounded-full shrink-0" :style="{ background: `hsl(${s.color})` }"></span>
            <span class="font-semibold tabular-nums">{{ totals[s.key] }} {{ s.label }}</span>
          </button>
          <p class="pl-[18px] ml-0.5 text-xs text-muted-foreground">{{ pct(s.key) }} % défini sur {{ s.label }}</p>
        </li>
      </ul>
    </div>
  </div>
</template>
