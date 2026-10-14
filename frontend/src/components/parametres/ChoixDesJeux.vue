<script setup lang="ts">
// Lot PT-02b (A28, A32, A35) : le choix des jeux de données au lancement d'une exécution ET dans une planification — un
// seul composant, pour que les deux écrans disent exactement la même chose.
//
// Rien n'est proposé à un projet qui n'a pas de variable (`actif` reste faux) : le formulaire est alors celui d'avant. Le jeu
// « Par défaut » est coché d'emblée. Un jeu coché = une exécution ; plusieurs = une exécution par jeu, regroupées dans un
// plan. A35 : la première joue tous les tests choisis, les suivantes seulement ceux qui écrivent des variables (tri refait
// par le serveur au lancement : ce décompte est celui d'aujourd'hui).
import { computed, onMounted, ref, watchEffect } from 'vue'
import { api, type JeuDeDonnees } from '../../lib/api'

const JEUX_PAR_LANCEMENT_MAX = 50   // le serveur applique la même borne (A28)

// `masque` : le bloc disparaît (campagne manuelle) sans perdre les jeux cochés, retrouvés en revenant en automatique.
const props = defineProps<{ pid: string; testsChoisis: number[]; masque?: boolean }>()
const coches = defineModel<number[]>({ required: true })
// Vrai quand le formulaire peut être envoyé de ce point de vue : projet sans jeu, ou de 1 à 50 jeux cochés.
const valide = defineModel<boolean>('valide', { default: true })

const jeux = ref<JeuDeDonnees[]>([])
// `null` : liste illisible — l'annonce perd son détail, jamais le choix des jeux.
const casAvecVariables = ref<Set<number> | null>(null)
const testsAvecVariables = computed(() => props.testsChoisis.filter((id) => casAvecVariables.value?.has(id)).length)
const nombreDExecutions = computed(() => Math.max(1, coches.value.length))
const pluriel = (n: number, mot: string) => `${n} ${mot}${n > 1 ? 's' : ''}`
watchEffect(() => {
  valide.value = !jeux.value.length || (coches.value.length >= 1 && coches.value.length <= JEUX_PAR_LANCEMENT_MAX)
})

onMounted(async () => {
  try {
    const tableau = await api.getTestData(props.pid)
    if (tableau.variables.length) {
      jeux.value = tableau.jeux
      coches.value = tableau.jeux.filter((j) => j.est_defaut).map((j) => j.id)
    }
  } catch { jeux.value = [] }   // tableau illisible : on crée comme avant, le serveur jouera le jeu « Par défaut »
  if (jeux.value.length) {
    try { casAvecVariables.value = new Set(await api.casAvecVariables(props.pid)) } catch { casAvecVariables.value = null }
  }
})
</script>

<template>
  <fieldset v-if="jeux.length && !masque" class="rounded-md border border-border p-3" data-testid="choix-jeux">
    <legend class="px-1 text-sm font-medium">Données de test</legend>
    <div class="flex flex-wrap gap-x-5 gap-y-2">
      <label v-for="j in jeux" :key="j.id" class="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
        <input type="checkbox" :value="j.id" v-model="coches" :data-testid="`jeu-${j.id}`" class="accent-[hsl(var(--primary))]" />
        {{ j.nom }}
      </label>
    </div>
    <p class="mt-2 flex flex-wrap items-center gap-x-3 text-xs" aria-live="polite">
      <span v-if="coches.length > JEUX_PAR_LANCEMENT_MAX" class="text-destructive" data-testid="trop-de-jeux">{{ JEUX_PAR_LANCEMENT_MAX }} jeux au plus</span>
      <span v-else-if="!coches.length" class="text-destructive">Cochez au moins un jeu</span>
      <span v-else class="text-muted-foreground" data-testid="nombre-executions">
        <template v-if="nombreDExecutions === 1">1 exécution</template>
        <template v-else-if="!casAvecVariables">{{ nombreDExecutions }} exécutions, regroupées dans un plan</template>
        <template v-else>{{ nombreDExecutions }} exécutions : {{ pluriel(testsChoisis.length, 'test') }} dans la première,
          {{ testsAvecVariables ? `${testsAvecVariables} avec variables` : 'aucun test avec variables' }} dans les autres</template>
      </span>
      <RouterLink :to="{ name: 'project-test-data', params: { pid } }" class="text-primary hover:underline" data-testid="lien-donnees">Données de test</RouterLink>
    </p>
  </fieldset>
</template>
