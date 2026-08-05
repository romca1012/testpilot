<script setup lang="ts">
// La COURBE DES RÉSULTATS sur N jours, une ligne par statut — le graphique que TestRail montre en
// tête de l'Activité d'une campagne et de l'Historique d'un test.
//
// ⚠️ **Ce composant ne décide d'aucun statut.** Il reçoit des événements déjà étiquetés par le
// serveur et les COMPTE par jour. Le libellé et la couleur viennent de `lib/status.ts`, point
// unique de traduction — jamais une couleur choisie ici, jamais un `if` sur un code de statut.
//
// ⚠️ **Aucune librairie de graphiques** (contrainte du dépôt) : un `<polyline>` par statut suffit,
// et se lit dans le thème sombre sans configuration.
//
// Il sert DEUX écrans (Activité d'une campagne, Historique d'un test) : c'est ce qui justifie
// qu'il existe séparément plutôt que d'être écrit deux fois.
import { computed } from 'vue'
import { TEST_STATUS_ORDER, testStatusMeta } from '../lib/status'
import { cleJour, derniersJours, jourLong } from '../lib/format'

const props = withDefaults(defineProps<{
  events: { statut: string; created_at: string }[]
  jours?: number
}>(), { jours: 14 })

// Géométrie en unités de viewBox : la courbe s'étire à la largeur disponible.
const W = 640, H = 150, PAD_L = 26, PAD_R = 8, PAD_T = 10, PAD_B = 22

const grille = computed(() => derniersJours(props.jours))

/** Combien de résultats de chaque statut, chaque jour. Un jour sans rien vaut 0 — il reste dans
 *  la courbe : un trou masquerait une période sans activité, qui est une information. */
const compte = computed(() => {
  const par: Record<string, number[]> = {}
  for (const s of TEST_STATUS_ORDER) par[s] = grille.value.map(() => 0)
  const index = new Map(grille.value.map((j, i) => [j, i]))
  for (const e of props.events) {
    const i = index.get(cleJour(e.created_at))
    if (i === undefined) continue
    if (par[e.statut]) par[e.statut][i]++
  }
  return par
})

const plafond = computed(() =>
  Math.max(1, ...TEST_STATUS_ORDER.flatMap((s) => compte.value[s])))

function x(i: number): number {
  const n = grille.value.length
  return PAD_L + (n <= 1 ? 0 : (i * (W - PAD_L - PAD_R)) / (n - 1))
}
function y(v: number): number {
  return PAD_T + (H - PAD_T - PAD_B) * (1 - v / plafond.value)
}
function ligne(statut: string): string {
  return compte.value[statut].map((v, i) => `${x(i)},${y(v)}`).join(' ')
}

/** Total de la période par statut — la légende dit un NOMBRE, pas seulement une couleur. */
const totaux = computed(() => Object.fromEntries(
  TEST_STATUS_ORDER.map((s) => [s, compte.value[s].reduce((a, b) => a + b, 0)])))

const aucun = computed(() => TEST_STATUS_ORDER.every((s) => totaux.value[s] === 0))
const premier = computed(() => jourLong(grille.value[0] || ''))
const dernier = computed(() => jourLong(grille.value[grille.value.length - 1] || ''))
</script>

<template>
  <div class="rounded-lg border border-border bg-surface/60 p-4">
    <svg :viewBox="`0 0 ${W} ${H}`" class="w-full h-auto" role="img"
         :aria-label="`Résultats des ${jours} derniers jours, par statut`">
      <!-- Repères horizontaux : 0 et le plafond. Deux suffisent — une grille dense ferait du
           bruit sans rien apprendre à cette échelle. -->
      <line :x1="PAD_L" :y1="y(0)" :x2="W - PAD_R" :y2="y(0)"
            stroke="hsl(var(--border))" stroke-width="1" />
      <line :x1="PAD_L" :y1="y(plafond)" :x2="W - PAD_R" :y2="y(plafond)"
            stroke="hsl(var(--border))" stroke-width="1" stroke-dasharray="3 4" opacity="0.6" />
      <text :x="PAD_L - 6" :y="y(0) + 4" text-anchor="end" font-size="10"
            fill="hsl(var(--muted-foreground))">0</text>
      <text :x="PAD_L - 6" :y="y(plafond) + 4" text-anchor="end" font-size="10"
            fill="hsl(var(--muted-foreground))">{{ plafond }}</text>

      <polyline v-for="s in TEST_STATUS_ORDER" :key="s" :points="ligne(s)" fill="none"
                :stroke="`hsl(${testStatusMeta(s).color})`" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round" />

      <text :x="PAD_L" :y="H - 6" font-size="10" fill="hsl(var(--muted-foreground))">{{ premier }}</text>
      <text :x="W - PAD_R" :y="H - 6" text-anchor="end" font-size="10"
            fill="hsl(var(--muted-foreground))">{{ dernier }}</text>
    </svg>

    <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] text-muted-foreground">
      <span v-for="s in TEST_STATUS_ORDER" :key="s" class="flex items-center gap-1.5">
        <span class="h-0.5 w-4 rounded-full" :style="{ background: `hsl(${testStatusMeta(s).color})` }"></span>
        {{ testStatusMeta(s).label }} : {{ totaux[s] }}
      </span>
    </div>

    <!-- Dire qu'il ne s'est RIEN passé, plutôt que de laisser une ligne plate à zéro se faire
         passer pour un graphique en panne. -->
    <p v-if="aucun" class="mt-2 text-xs text-muted-foreground italic">
      Aucun résultat sur les {{ jours }} derniers jours.
    </p>
  </div>
</template>
