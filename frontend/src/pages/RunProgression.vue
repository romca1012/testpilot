<script setup lang="ts">
// Sous-onglet PROGRESSION d'une campagne — où elle en est, et à quelle vitesse elle y est allée.
//
// ⚠️ **Ce qu'on compte, et ce qu'on refuse de compter.** La courbe suit le nombre de cas ayant
// reçu leur PREMIER résultat, jour après jour. Pas le nombre de résultats : rejouer trois fois le
// même cas ferait alors monter la courbe sans qu'un seul cas de plus ait été couvert — une
// campagne pourrait afficher « 120 % ». Un cas compte une fois, le jour où il a été testé.
//
// ⚠️ **Aucune extrapolation, aucune date de fin promise.** L'écran montre ce qui s'est passé ;
// il ne prédit pas quand la campagne sera finie. Une droite prolongée aurait l'air d'un engagement.
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, type RunActivite } from '../lib/api'
import { cleJour, derniersJours, jourLong } from '../lib/format'
import Button from '../components/ui/Button.vue'

const route = useRoute()
const pid = computed(() => route.params.pid as string)
const runId = computed(() => Number(route.params.id))

const activite = ref<RunActivite | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true; error.value = ''
  try { activite.value = await api.getRunActivite(runId.value) }
  catch { error.value = 'Impossible de charger la progression de cette campagne.' }
  finally { loading.value = false }
}
load()
watch(runId, load)

const total = computed(() => activite.value?.case_count || 0)

/** Le JOUR où chaque cas a reçu son premier résultat. Les événements arrivent du plus récent au
 *  plus ancien : le dernier vu pour un cas est donc le plus ancien — son premier résultat. */
const premierJourParCas = computed(() => {
  const m = new Map<number, string>()
  for (const e of activite.value?.events || []) m.set(e.case_id, cleJour(e.created_at))
  return m
})

const testes = computed(() => premierJourParCas.value.size)
const pct = computed(() => (total.value ? Math.round((testes.value / total.value) * 100) : 0))

// La fenêtre part du premier jour d'activité (au plus 60 jours) : une campagne d'un après-midi ne
// doit pas s'afficher écrasée dans un mois de vide.
const JOURS_MAX = 60
const grille = computed(() => {
  const jours = [...premierJourParCas.value.values()].filter(Boolean).sort()
  if (!jours.length) return derniersJours(14)
  const debut = new Date(`${jours[0]}T00:00:00Z`).getTime()
  const span = Math.floor((Date.now() - debut) / 86400000) + 1
  return derniersJours(Math.min(Math.max(span, 2), JOURS_MAX))
})

/** Cumul : combien de cas avaient été testés à la fin de chaque jour de la grille. */
const cumul = computed(() => {
  const parJour = new Map<string, number>()
  for (const j of premierJourParCas.value.values()) parJour.set(j, (parJour.get(j) || 0) + 1)
  let acc = 0
  return grille.value.map((j) => {
    acc += parJour.get(j) || 0
    return acc
  })
})

// Géométrie SVG — tracée à la main : le dépôt n'embarque aucune librairie de graphiques.
const W = 640, H = 170, PAD_L = 30, PAD_R = 8, PAD_T = 10, PAD_B = 22
const plafond = computed(() => Math.max(1, total.value))
function x(i: number): number {
  const n = grille.value.length
  return PAD_L + (n <= 1 ? 0 : (i * (W - PAD_L - PAD_R)) / (n - 1))
}
function y(v: number): number {
  return PAD_T + (H - PAD_T - PAD_B) * (1 - v / plafond.value)
}
const trace = computed(() => cumul.value.map((v, i) => `${x(i)},${y(v)}`).join(' '))
const aire = computed(() =>
  `${PAD_L},${y(0)} ${trace.value} ${x(grille.value.length - 1)},${y(0)}`)
const premier = computed(() => jourLong(grille.value[0] || ''))
const dernier = computed(() => jourLong(grille.value[grille.value.length - 1] || ''))
</script>

<template>
  <div v-if="loading" class="space-y-3">
    <div class="h-8 w-64 rounded bg-secondary animate-pulse"></div>
    <div class="h-40 rounded bg-secondary animate-pulse"></div>
  </div>

  <div v-else-if="error" class="text-center py-10">
    <p class="text-sm text-muted-foreground">{{ error }}</p>
    <Button variant="secondary" class="mt-3" @click="load">Réessayer</Button>
  </div>

  <div v-else-if="activite">
    <h1 class="text-2xl font-semibold tracking-tight truncate">Progression</h1>
    <RouterLink :to="{ name: 'run-detail', params: { pid, id: String(runId) } }"
                class="mt-1 inline-block text-primary text-sm hover:underline">{{ activite.run_name }}</RouterLink>

    <div class="mt-5 flex flex-wrap items-center gap-8 rounded-lg border border-border bg-surface/60 p-4">
      <div>
        <div class="text-3xl font-semibold tabular-nums">{{ pct }} %</div>
        <div class="text-xs text-muted-foreground mt-0.5">{{ testes }} / {{ total }} cas testés</div>
      </div>
      <div class="flex-1 min-w-[240px]">
        <svg :viewBox="`0 0 ${W} ${H}`" class="w-full h-auto" role="img"
             aria-label="Cas testés au fil du temps">
          <polygon :points="aire" fill="hsl(var(--primary))" opacity="0.15" />
          <polyline :points="trace" fill="none" stroke="hsl(var(--primary))" stroke-width="2"
                    stroke-linejoin="round" stroke-linecap="round" />
          <!-- Le plafond est le NOMBRE DE CAS de la campagne, pas le maximum atteint : une courbe
               qui touche le haut du cadre à 3 cas sur 40 laisserait croire que c'est fini. -->
          <line :x1="PAD_L" :y1="y(plafond)" :x2="W - PAD_R" :y2="y(plafond)"
                stroke="hsl(var(--border))" stroke-width="1" stroke-dasharray="3 4" />
          <line :x1="PAD_L" :y1="y(0)" :x2="W - PAD_R" :y2="y(0)" stroke="hsl(var(--border))" stroke-width="1" />
          <text :x="PAD_L - 6" :y="y(plafond) + 4" text-anchor="end" font-size="10"
                fill="hsl(var(--muted-foreground))">{{ plafond }}</text>
          <text :x="PAD_L - 6" :y="y(0) + 4" text-anchor="end" font-size="10"
                fill="hsl(var(--muted-foreground))">0</text>
          <text :x="PAD_L" :y="H - 6" font-size="10" fill="hsl(var(--muted-foreground))">{{ premier }}</text>
          <text :x="W - PAD_R" :y="H - 6" text-anchor="end" font-size="10"
                fill="hsl(var(--muted-foreground))">{{ dernier }}</text>
        </svg>
      </div>
    </div>

    <p class="mt-3 text-xs text-muted-foreground max-w-2xl">
      Un cas compte le jour de son <strong class="text-foreground">premier</strong> résultat.
      Rejouer un cas déjà testé ne fait donc pas monter la courbe — ce serait compter deux fois la
      même couverture. Le détail de qui a posé quoi, et quand, est dans
      <RouterLink :to="{ name: 'run-activite', params: { pid, id: String(runId) } }"
                  class="text-primary hover:underline">Activité</RouterLink>.
    </p>

    <p v-if="!testes" class="mt-4 text-sm text-muted-foreground italic">
      Aucun cas n'a encore été testé dans cette campagne.
    </p>
  </div>
</template>
