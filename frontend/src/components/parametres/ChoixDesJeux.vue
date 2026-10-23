<script setup lang="ts">
// Lot PT-02b (A28, A32), puis A52 (itérations, 2026-10-16) : le choix des lignes de données de test au lancement d'une
// exécution ET dans une planification — un seul composant, pour que les deux écrans disent exactement la même chose.
//
// Rien n'est proposé à un projet qui n'a pas de variable : le formulaire est alors celui d'avant. Le jeu « Par défaut » est
// coché d'emblée. Comme le « Data Table » de QTP/UFT, chaque ligne cochée est une ITÉRATION de la même exécution (A52) — plus
// une exécution par ligne. Plusieurs environnements cochés : une exécution par environnement, chacune avec ces itérations.
// A56 (porteur, 2026-10-18) : les données de test restent FACULTATIVES — aucune ligne cochée, le test est joué avec les
// valeurs « Par défaut » (le serveur le fait déjà quand aucune ligne ne lui est envoyée).
// A107 (porteur, 2026-10-23) : « de la ligne X à Y » ne se choisit qu'à UN endroit, pour les valeurs de chaque cas (le
// raccourci du tableau commun faisait doublon : les cases à cocher suffisent). La plage proposée existe dans tous les cas
// choisis qui ont des lignes ; le serveur le revérifie à la création et au lancement.
import { computed, onMounted, ref, watch, watchEffect } from 'vue'
import { api, type JeuDeDonnees } from '../../lib/api'

const LIGNES_PAR_LANCEMENT_MAX = 50   // le serveur applique la même borne

// `masque` : le bloc disparaît (campagne manuelle) sans perdre les lignes cochées, retrouvées en revenant en automatique.
// `environnements` (lot PT-04a) : combien d'environnements sont cochés — une exécution par environnement.
// `avecLignesDesCas` (A58) : propose « toutes » ou « la première » des lignes propres aux cas choisis — au lancement
// seulement (une planification joue toutes les lignes).
const props = defineProps<{ pid: string; testsChoisis: number[]; masque?: boolean; environnements?: number; avecLignesDesCas?: boolean }>()
const lignesDesCas = defineModel<'toutes' | 'premiere' | 'plage'>('lignesDesCas', { default: 'toutes' })
const plageDe = defineModel<number>('plageDe', { default: 1 })
const plageA = defineModel<number>('plageA', { default: 1 })
const coches = defineModel<number[]>({ required: true })
// Vrai quand le formulaire peut être envoyé de ce point de vue : 50 lignes cochées au plus (aucune : « Par défaut », A56).
const valide = defineModel<boolean>('valide', { default: true })

const jeux = ref<JeuDeDonnees[]>([])
const casAvecLignes = ref<number[]>([])
const lignesParCas = ref<Record<string, number>>({})
const casChoisisAvecLignes = computed(() => props.testsChoisis.filter((id) => casAvecLignes.value.includes(id)).length)
// La dernière ligne qu'on peut choisir : celle du cas choisi qui en a le moins (0 : nombres illisibles, pas de plage proposée).
const plageMax = computed(() => {
  const nombres = props.testsChoisis.filter((id) => casAvecLignes.value.includes(id)).map((id) => lignesParCas.value[String(id)] ?? 0)
  return nombres.length ? Math.min(...nombres) : 0
})
const plageValide = computed(() => lignesDesCas.value !== 'plage'
  || (Number.isInteger(plageDe.value) && Number.isInteger(plageA.value) && plageDe.value >= 1 && plageDe.value <= plageA.value
      && plageA.value <= plageMax.value))
const executions = computed(() => Math.max(1, props.environnements ?? 1))
const toutes = computed(() => jeux.value.length > 0 && coches.value.length === jeux.value.length)
const pluriel = (n: number, mot: string) => `${n} ${mot}${n > 1 ? 's' : ''}`
watchEffect(() => {
  valide.value = coches.value.length <= LIGNES_PAR_LANCEMENT_MAX && plageValide.value
})
// Proposée d'emblée « de 1 à la dernière ligne possible », tant que la personne n'a pas choisi la plage.
watch(plageMax, (max) => { if (lignesDesCas.value !== 'plage') plageA.value = Math.max(1, max) })

function basculerToutes() {
  coches.value = toutes.value ? jeux.value.filter((j) => j.est_defaut).map((j) => j.id) : jeux.value.map((j) => j.id)
}

onMounted(async () => {
  try {
    const tableau = await api.getTestData(props.pid)
    if (tableau.variables.length) {
      jeux.value = tableau.jeux
      coches.value = tableau.jeux.filter((j) => j.est_defaut).map((j) => j.id)
      if (props.avecLignesDesCas) {
        // Illisible : le choix n'est pas proposé, et le serveur joue toutes les lignes (son défaut) — rien d'autre ne change.
        try { casAvecLignes.value = await api.casAvecLignes(props.pid) } catch { casAvecLignes.value = [] }
        try { lignesParCas.value = await api.lignesParCas(props.pid) } catch { lignesParCas.value = {} }
      }
    }
  } catch { jeux.value = [] }   // tableau illisible : on crée comme avant, le serveur jouera le jeu « Par défaut »
})
</script>

<template>
  <fieldset v-if="jeux.length && !masque" class="rounded-md border border-border p-3" data-testid="choix-jeux">
    <legend class="px-1 text-sm font-medium">Données de test</legend>
    <p class="mb-1 text-sm text-muted-foreground" data-testid="titre-communes">Valeurs communes à tous les cas</p>
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
      <RouterLink :to="{ name: 'project-test-data', params: { pid } }" class="text-primary hover:underline" data-testid="lien-donnees">Données de test</RouterLink>
    </p>
    <!-- A58 : un cas qui a ses propres lignes les joue toutes, une itération chacune — ou seulement la première ; A107 : ou de la
         ligne X à Y. -->
    <div v-if="avecLignesDesCas && casChoisisAvecLignes" class="mt-3 border-t border-dashed border-border pt-2 text-sm"
         role="radiogroup" aria-label="Valeurs de chaque cas" data-testid="lignes-des-cas">
      <p class="text-muted-foreground">Valeurs de chaque cas ({{ casChoisisAvecLignes }} cas)</p>
      <div class="flex flex-wrap items-center gap-x-4 gap-y-1">
        <label class="flex min-h-11 cursor-pointer items-center gap-1.5">
          <input type="radio" value="toutes" v-model="lignesDesCas" data-testid="lignes-toutes" class="accent-[hsl(var(--primary))]" />Toutes
          <span class="rounded-full bg-muted px-2 text-xs text-muted-foreground">recommandé</span>
        </label>
        <label class="flex min-h-11 cursor-pointer items-center gap-1.5">
          <input type="radio" value="premiere" v-model="lignesDesCas" data-testid="lignes-premiere" class="accent-[hsl(var(--primary))]" />La première seulement
        </label>
        <label v-if="plageMax > 1" class="flex min-h-11 cursor-pointer items-center gap-1.5" data-testid="lignes-plage">
          <input type="radio" value="plage" v-model="lignesDesCas" data-testid="lignes-plage-choix" class="accent-[hsl(var(--primary))]" />De la ligne
          <input type="number" min="1" :max="plageMax" v-model.number="plageDe" @focus="lignesDesCas = 'plage'" aria-label="Première ligne"
                 class="w-14 rounded border border-border bg-background px-1 py-0.5" data-testid="plage-de" />
          à
          <input type="number" min="1" :max="plageMax" v-model.number="plageA" @focus="lignesDesCas = 'plage'" aria-label="Dernière ligne"
                 class="w-14 rounded border border-border bg-background px-1 py-0.5" data-testid="plage-a" />
        </label>
      </div>
      <p v-if="lignesDesCas === 'plage' && !plageValide" class="text-xs text-destructive" data-testid="plage-invalide">
        Choisissez de 1 à {{ plageMax }}.
      </p>
    </div>
  </fieldset>
</template>
