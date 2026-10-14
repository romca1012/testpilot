<script setup lang="ts">
// Lot PT-02c (A32) : le test d'une version, « tel qu'écrit » ou tel qu'il serait joué avec une colonne de données. Le texte
// remplacé vient du SERVEUR (`apercu-donnees`, même calcul qu'au lancement) — jamais recalculé ici, où il pourrait
// diverger de ce que l'exécution jouera. Rien ne change pour un projet sans variable ou un test qui n'en écrit pas.
import { computed, onMounted, ref, watch } from 'vue'
import { api, type ApercuDonnees, type JeuDeDonnees } from '../../lib/api'
import CodeView from '../CodeView.vue'

const props = defineProps<{ pid: string; caseId: number; versionId: number | null; feature: string }>()

const jeux = ref<JeuDeDonnees[]>([])
const choix = ref<number | null>(null)          // null : tel qu'écrit
const apercu = ref<ApercuDonnees | null>(null)
const erreur = ref('')
const proposer = computed(() => jeux.value.length > 0 && props.feature.includes('{{'))

onMounted(async () => {
  try {
    const tableau = await api.getTestData(props.pid)
    // Les jeux suffisent : un projet dont toutes les variables sont à la corbeille en a encore, et l'aperçu doit alors
    // annoncer « Serait bloqué » (un projet qui n'a jamais déclaré de variable n'a aucun jeu).
    jeux.value = tableau.jeux
  } catch { jeux.value = [] }   // tableau illisible : le test tel qu'écrit, comme avant
})

async function charger() {
  apercu.value = null
  erreur.value = ''
  if (choix.value == null || !props.versionId) return
  const demande = choix.value
  const version = props.versionId
  try {
    const vu = await api.apercuDonnees(props.caseId, version, demande)
    // Une réponse arrivée après un autre choix (jeu OU version) n'est jamais affichée sous le mauvais test.
    if (choix.value === demande && props.versionId === version) apercu.value = vu
  } catch (e: any) {
    erreur.value = e?.message || 'Aperçu indisponible.'
  }
}
watch([choix, () => props.versionId], charger)
</script>

<template>
  <div>
    <div v-if="proposer" class="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
      <label class="flex items-center gap-2">
        <span class="text-muted-foreground">Valeurs</span>
        <select v-model="choix" data-testid="apercu-jeu"
                class="min-h-9 rounded-md border border-border bg-surface-raised px-2 py-1 text-xs outline-none focus:border-primary">
          <option :value="null">Tel qu'écrit</option>
          <option v-for="j in jeux" :key="j.id" :value="j.id">{{ j.nom }}</option>
        </select>
      </label>
      <RouterLink :to="{ name: 'project-test-data', params: { pid } }" class="text-primary hover:underline"
                  data-testid="lien-donnees">Données de test</RouterLink>
    </div>
    <p v-if="apercu?.manques.length" role="status" class="mb-2 text-xs text-destructive" data-testid="apercu-manques">
      Serait bloqué : {{ apercu.manques.join(' ; ') }}
    </p>
    <p v-else-if="erreur" class="mb-2 text-xs text-destructive">{{ erreur }}</p>
    <CodeView :content="apercu ? apercu.texte : feature" lang="gherkin" data-testid="apercu-texte" />
  </div>
</template>
