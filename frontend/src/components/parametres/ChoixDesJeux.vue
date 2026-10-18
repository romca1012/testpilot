<script setup lang="ts">
// Lot PT-02b (A28, A32), puis A52 (itérations, 2026-10-16) : le choix des lignes de données de test au lancement d'une
// exécution ET dans une planification — un seul composant, pour que les deux écrans disent exactement la même chose.
//
// Rien n'est proposé à un projet qui n'a pas de variable : le formulaire est alors celui d'avant. Le jeu « Par défaut » est
// coché d'emblée. Comme le « Data Table » de QTP/UFT, chaque ligne cochée est une ITÉRATION de la même exécution (A52) — plus
// une exécution par ligne. Plusieurs environnements cochés : une exécution par environnement, chacune avec ces itérations.
// A56 (porteur, 2026-10-18) : les données de test restent FACULTATIVES — aucune ligne cochée, le test est joué avec les
// valeurs « Par défaut » (le serveur le fait déjà quand aucune ligne ne lui est envoyée). « De la ligne X à Y » coche une
// plage d'un coup, dans l'ordre du tableau.
import { computed, onMounted, ref, watchEffect } from 'vue'
import { api, type JeuDeDonnees } from '../../lib/api'

const LIGNES_PAR_LANCEMENT_MAX = 50   // le serveur applique la même borne

// `masque` : le bloc disparaît (campagne manuelle) sans perdre les lignes cochées, retrouvées en revenant en automatique.
// `environnements` (lot PT-04a) : combien d'environnements sont cochés — une exécution par environnement.
const props = defineProps<{ pid: string; testsChoisis: number[]; masque?: boolean; environnements?: number }>()
const coches = defineModel<number[]>({ required: true })
// Vrai quand le formulaire peut être envoyé de ce point de vue : 50 lignes cochées au plus (aucune : « Par défaut », A56).
const valide = defineModel<boolean>('valide', { default: true })

const jeux = ref<JeuDeDonnees[]>([])
const executions = computed(() => Math.max(1, props.environnements ?? 1))
const toutes = computed(() => jeux.value.length > 0 && coches.value.length === jeux.value.length)
const pluriel = (n: number, mot: string) => `${n} ${mot}${n > 1 ? 's' : ''}`
watchEffect(() => {
  valide.value = coches.value.length <= LIGNES_PAR_LANCEMENT_MAX
})

// « De la ligne X à Y » : des numéros de ligne (1 = la première du tableau), jamais des identifiants.
const de = ref(1)
const a = ref(1)
function cocherLaPlage() {
  const [debut, fin] = de.value <= a.value ? [de.value, a.value] : [a.value, de.value]
  coches.value = jeux.value.slice(debut - 1, fin).map((j) => j.id)
}

function basculerToutes() {
  coches.value = toutes.value ? jeux.value.filter((j) => j.est_defaut).map((j) => j.id) : jeux.value.map((j) => j.id)
}

onMounted(async () => {
  try {
    const tableau = await api.getTestData(props.pid)
    if (tableau.variables.length) {
      jeux.value = tableau.jeux
      coches.value = tableau.jeux.filter((j) => j.est_defaut).map((j) => j.id)
      a.value = tableau.jeux.length
    }
  } catch { jeux.value = [] }   // tableau illisible : on crée comme avant, le serveur jouera le jeu « Par défaut »
})
</script>

<template>
  <fieldset v-if="jeux.length && !masque" class="rounded-md border border-border p-3" data-testid="choix-jeux">
    <legend class="px-1 text-sm font-medium">Données de test</legend>
    <div class="flex flex-wrap gap-x-5 gap-y-2">
      <label v-for="(j, i) in jeux" :key="j.id" class="flex min-h-11 cursor-pointer items-center gap-2 text-sm">
        <input type="checkbox" :value="j.id" v-model="coches" :data-testid="`jeu-${j.id}`" class="accent-[hsl(var(--primary))]" />
        <span class="text-xs tabular-nums text-muted-foreground">{{ i + 1 }}</span>{{ j.nom }}
      </label>
    </div>
    <p class="mt-2 flex flex-wrap items-center gap-x-3 text-xs" aria-live="polite">
      <span v-if="coches.length > LIGNES_PAR_LANCEMENT_MAX" class="text-destructive" data-testid="trop-de-jeux">{{ LIGNES_PAR_LANCEMENT_MAX }} lignes au plus</span>
      <span v-else class="text-muted-foreground" data-testid="nombre-executions">
        <template v-if="!coches.length && executions === 1">1 exécution, valeurs par défaut</template>
        <template v-else-if="!coches.length">{{ executions }} exécutions, valeurs par défaut, regroupées dans un plan</template>
        <template v-else-if="executions === 1">1 exécution, {{ pluriel(coches.length, 'itération') }}</template>
        <template v-else>{{ executions }} exécutions de {{ pluriel(coches.length, 'itération') }}, regroupées dans un plan</template>
      </span>
      <button v-if="jeux.length > 1" type="button" class="text-primary hover:underline" data-testid="toutes-les-lignes"
              @click="basculerToutes">{{ toutes ? 'Par défaut seulement' : 'Toutes les lignes' }}</button>
      <span v-if="jeux.length > 2" class="flex items-center gap-1 text-muted-foreground" data-testid="plage">
        <label for="plage-de">De la ligne</label>
        <select id="plage-de" v-model.number="de" class="rounded border border-border bg-background px-1 py-0.5 text-foreground" data-testid="plage-de">
          <option v-for="(j, i) in jeux" :key="j.id" :value="i + 1">{{ i + 1 }}</option>
        </select>
        <label for="plage-a">à</label>
        <select id="plage-a" v-model.number="a" class="rounded border border-border bg-background px-1 py-0.5 text-foreground" data-testid="plage-a">
          <option v-for="(j, i) in jeux" :key="j.id" :value="i + 1">{{ i + 1 }}</option>
        </select>
        <button type="button" class="text-primary hover:underline" data-testid="plage-cocher" @click="cocherLaPlage">Cocher</button>
      </span>
      <RouterLink :to="{ name: 'project-test-data', params: { pid } }" class="text-primary hover:underline" data-testid="lien-donnees">Données de test</RouterLink>
    </p>
  </fieldset>
</template>
