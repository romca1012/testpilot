<script setup lang="ts">
// Lot PT-04a (A48 à A50) : le choix des environnements au lancement d'une exécution ET dans une planification — un seul
// composant pour les deux écrans, comme `ChoixDesJeux`.
//
// Rien n'est proposé à un projet qui n'a que son environnement par défaut : le formulaire est alors celui d'avant. Le défaut
// est coché d'emblée. Un environnement « Production » est montré, jamais cochable (A48) ; le serveur le refuse aussi.
// Plusieurs environnements cochés : une exécution par environnement, regroupées dans un plan ; les lignes de données de test
// sont des itérations de chacune (A52). Quand le bloc des jeux est affiché (`jeux` > 0), c'est lui qui annonce le décompte.
import { computed, onMounted, ref, watchEffect } from 'vue'
import { api, type Environnement } from '../../lib/api'

const EXECUTIONS_PAR_LANCEMENT_MAX = 20   // le serveur applique la même borne (environnements par lancement)

const props = defineProps<{ pid: string; masque?: boolean; jeux?: number }>()
const coches = defineModel<number[]>({ required: true })
const valide = defineModel<boolean>('valide', { default: true })

const environnements = ref<Environnement[]>([])
const actif = computed(() => environnements.value.length > 1)
const nombreDExecutions = computed(() => Math.max(1, coches.value.length))
watchEffect(() => {
  valide.value = !actif.value || (coches.value.length >= 1 && nombreDExecutions.value <= EXECUTIONS_PAR_LANCEMENT_MAX)
})

onMounted(async () => {
  try {
    environnements.value = await api.listEnvironnements(props.pid)
  } catch { environnements.value = [] }   // illisible : on crée comme avant, sur l'environnement par défaut
  coches.value = actif.value ? environnements.value.filter((e) => e.est_defaut).map((e) => e.id) : []
})
</script>

<template>
  <fieldset v-if="actif && !masque" class="rounded-md border border-border p-3" data-testid="choix-environnements">
    <legend class="px-1 text-sm font-medium">Environnement</legend>
    <div class="flex flex-wrap gap-x-5 gap-y-2">
      <label v-for="e in environnements" :key="e.id"
             :class="['flex min-h-11 items-center gap-2 text-sm', e.nature === 'production' ? 'cursor-not-allowed text-muted-foreground' : 'cursor-pointer']">
        <input type="checkbox" :value="e.id" v-model="coches" :disabled="e.nature === 'production'" :data-testid="`environnement-${e.id}`"
               class="accent-[hsl(var(--primary))]" />
        {{ e.nom }}
        <span v-if="e.nature === 'production'" class="rounded-full bg-destructive/10 px-2 py-0.5 text-xs font-medium text-destructive">{{ e.nature_libelle }}</span>
      </label>
    </div>
    <p class="mt-2 text-xs" aria-live="polite">
      <span v-if="!coches.length" class="text-destructive">Cochez au moins un environnement</span>
      <span v-else-if="nombreDExecutions > EXECUTIONS_PAR_LANCEMENT_MAX" class="text-destructive" data-testid="trop-d-executions">{{ EXECUTIONS_PAR_LANCEMENT_MAX }} exécutions au plus</span>
      <span v-else-if="!jeux && nombreDExecutions > 1" class="text-muted-foreground" data-testid="nombre-executions-env">{{ nombreDExecutions }} exécutions, regroupées dans un plan</span>
    </p>
  </fieldset>
</template>
