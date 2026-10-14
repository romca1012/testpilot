<script setup lang="ts">
// Lot PT-02c : le bouton « Variable » de l'édition d'un test — choisir une variable du projet l'écrit `{{nom}}` à l'endroit
// du curseur (le parent insère). Rien n'est proposé à un projet sans variable.
import { onMounted, ref } from 'vue'
import { api, type VariableDeTest } from '../../lib/api'

const props = defineProps<{ pid: string }>()
const emit = defineEmits<{ inserer: [texte: string] }>()

const variables = ref<VariableDeTest[]>([])
const choix = ref('')
onMounted(async () => {
  try { variables.value = (await api.getTestData(props.pid)).variables } catch { variables.value = [] }
})
// Une variable telle qu'un test l'écrit — construite ici, jamais écrite en dur dans le gabarit (Vue y lirait une expression).
const ecrite = (nom: string) => `{{${nom}}}`
function choisir() {
  if (choix.value) emit('inserer', ecrite(choix.value))
  choix.value = ''
}
</script>

<template>
  <select v-if="variables.length" v-model="choix" @change="choisir" data-testid="inserer-variable" aria-label="Insérer une variable"
          class="min-h-9 rounded-md border border-border bg-surface-raised px-2 py-1 text-xs outline-none focus:border-primary">
    <option value="">Variable</option>
    <option v-for="v in variables" :key="v.id" :value="v.nom">{{ ecrite(v.nom) }}</option>
  </select>
</template>
