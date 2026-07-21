<script setup lang="ts">
// « Qualité de génération » — le suivi de l'évolution de l'outil.
//
// LA question : un test fraîchement généré TOURNE-T-IL sans erreur technique ? C'est l'axe
// EXÉCUTION (le test a-t-il pu s'exécuter), jamais le fonctionnel — un test qui tourne et détecte
// un vrai bug est un SUCCÈS technique (invariant des deux axes, §5). C'est exactement l'objectif
// « faire les tests sans erreur technique quel que soit le connecteur ».
//
// ⚠️ Rien n'est fabriqué ici : chaque chiffre agrège des exécutions RÉELLES (premier jet). Le
// tableau se remplit tout seul à chaque run — d'où sa valeur pour voir l'outil progresser.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, type Quality } from '../lib/api'
import StatTile from '../components/StatTile.vue'

const route = useRoute()
const pid = computed(() => route.params.pid as string)

const data = ref<Quality | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await api.getQuality(pid.value)
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible.'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(pid, load)

// Taux affiché SEULEMENT s'il existe : `ran_rate === null` veut dire « aucune mesure », pas
// « 0 % » — le repli silencieux qu'on refuse partout (§4.6).
const pct = computed(() =>
  data.value && data.value.ran_rate !== null ? Math.round(data.value.ran_rate * 100) : null)
const tone = computed(() => {
  if (pct.value === null) return 'muted'
  return pct.value >= 90 ? 'success' : pct.value >= 60 ? 'warning' : 'destructive'
})

// Barres par jour : hauteur relative au plus gros total, empilées success / erreur / interrompu.
const maxJour = computed(() =>
  Math.max(1, ...(data.value?.by_day || []).map((d) => d.success + d.technical_error + d.not_executed)))
</script>

<template>
  <div class="p-6 md:p-8 max-w-4xl">
    <header>
      <h1 class="text-[26px] font-semibold tracking-tight">Qualité de génération</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Un test fraîchement généré tourne-t-il <strong class="text-foreground">sans erreur
        technique</strong> ? Mesuré sur les exécutions réelles au premier jet — pas la conformité
        de l'application, juste : le test a-t-il pu s'exécuter.
      </p>
    </header>

    <div v-if="loading" class="mt-8 h-32 rounded-xl bg-secondary animate-pulse"></div>

    <div v-else-if="error" class="mt-8 text-sm text-muted-foreground">
      {{ error }}
      <button class="ml-2 text-primary hover:underline" @click="load">Réessayer</button>
    </div>

    <template v-else-if="data">
      <!-- Aucune donnée : on le DIT, on n'affiche pas « 0 % » -->
      <div v-if="!data.total" class="mt-8 rounded-xl border border-border bg-card px-5 py-10 text-center">
        <p class="text-sm text-muted-foreground">
          Aucune exécution mesurée pour l'instant. Générez un cas et lancez-le : sa réussite
          technique apparaîtra ici, et le tableau suivra l'évolution de l'outil au fil des runs.
        </p>
      </div>

      <template v-else>
        <!-- Le chiffre phare + le détail des trois états -->
        <div class="mt-6 grid gap-3 sm:grid-cols-4">
          <StatTile label="Réussite technique (1er jet)" :value="pct === null ? '—' : pct + ' %'"
                    :tone="tone" icon="check" />
          <StatTile label="Tests qui ont tourné" :value="data.ran" tone="success" icon="check" />
          <StatTile label="Erreurs techniques" :value="data.technical_error"
                    :tone="data.technical_error ? 'destructive' : 'muted'" icon="x" />
          <StatTile label="Interrompus" :value="data.not_executed"
                    :tone="data.not_executed ? 'warning' : 'muted'" icon="dot" />
        </div>

        <p class="mt-3 text-xs text-muted-foreground">
          {{ data.ran }} run{{ data.ran > 1 ? 's' : '' }} sur {{ data.total }} ont pu s'exécuter.
          « Erreur technique » = le test n'a pas pu tourner (sélecteur ou route introuvable,
          timeout…) ; « interrompu » = arrêté avant de tourner. Un test qui tourne et trouve un
          bug compte comme une réussite technique.
        </p>

        <!-- Évolution jour par jour -->
        <section class="mt-8">
          <h2 class="text-sm font-semibold text-muted-foreground uppercase tracking-wider">Évolution</h2>
          <div class="mt-4 flex items-end gap-2 overflow-x-auto pb-2" style="min-height: 140px">
            <div v-for="d in data.by_day" :key="d.jour" class="flex flex-col items-center gap-1.5 shrink-0" style="width: 48px">
              <div class="w-full flex flex-col-reverse rounded-md overflow-hidden bg-secondary/40"
                   :style="{ height: '110px' }" :title="`${d.jour} — ${d.success} ok / ${d.technical_error} erreur / ${d.not_executed} interrompu`">
                <div v-if="d.success" class="bg-success/80"
                     :style="{ height: (d.success / maxJour * 110) + 'px' }"></div>
                <div v-if="d.technical_error" class="bg-destructive/80"
                     :style="{ height: (d.technical_error / maxJour * 110) + 'px' }"></div>
                <div v-if="d.not_executed" class="bg-warning/70"
                     :style="{ height: (d.not_executed / maxJour * 110) + 'px' }"></div>
              </div>
              <span class="text-[10px] text-muted-foreground tabular-nums">{{ d.jour.slice(5) }}</span>
            </div>
          </div>
          <div class="mt-2 flex items-center gap-4 text-[11px] text-muted-foreground">
            <span class="flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-sm bg-success/80"></span>A tourné</span>
            <span class="flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-sm bg-destructive/80"></span>Erreur technique</span>
            <span class="flex items-center gap-1.5"><span class="h-2.5 w-2.5 rounded-sm bg-warning/70"></span>Interrompu</span>
          </div>
        </section>

        <p class="mt-8 text-xs text-muted-foreground/70">
          Mesure au <strong>premier jet</strong> (hors réparation et rejeux) : c'est la qualité de
          la génération elle-même, pas celle du filet qui la rattrape. Chiffres dérivés des runs
          réels — aucune valeur saisie à la main.
        </p>
      </template>
    </template>
  </div>
</template>
