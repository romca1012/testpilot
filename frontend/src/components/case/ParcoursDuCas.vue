<script setup lang="ts">
// Étape 7b (A109) : le parcours enregistré du cas — son mode opératoire (le plus récent), et le bouton pour le (re)jouer.
// Un nouveau parcours s'ajoute à l'historique ; le prochain test technique suivra le plus récent.
import { onMounted, ref } from 'vue'
import { api, type ParcoursEnregistre } from '../../lib/api'
import Button from '../ui/Button.vue'

const props = defineProps<{ caseId: number | string; projectId: number | string; peutEnregistrer: boolean }>()

const parcours = ref<ParcoursEnregistre[]>([])
const charge = ref(false)

onMounted(async () => {
  try {
    parcours.value = (await api.getParcours(props.caseId)).parcours
    charge.value = true
  } catch { /* illisible : la section reste cachée — un complément, jamais un blocage de la fiche */ }
})

const date = (iso: string) => (iso || '').slice(0, 10)
</script>

<template>
  <section v-if="charge && (parcours.length || peutEnregistrer)" class="mt-8" data-testid="parcours-du-cas">
    <div class="flex items-center justify-between gap-3 border-b border-border pb-2">
      <h2 class="font-semibold">Parcours</h2>
      <RouterLink v-if="peutEnregistrer" :to="`/projects/${projectId}/cases/${caseId}/parcours`">
        <Button size="sm" variant="secondary">{{ parcours.length ? 'Enregistrer à nouveau' : 'Enregistrer le parcours' }}</Button>
      </RouterLink>
    </div>
    <p v-if="!parcours.length" class="mt-3 text-sm text-subtle-foreground">
      Jouez ce cas une fois dans l'application : vos actions guideront le test technique, ou serviront de mode opératoire.
    </p>
    <template v-else>
      <p class="mt-3 text-xs text-subtle-foreground">
        Enregistré par {{ parcours[0].auteur || '—' }} le {{ date(parcours[0].created_at) }}
        <template v-if="parcours.length > 1"> · {{ parcours.length - 1 }} plus ancien(s) gardé(s)</template>
      </p>
      <ol class="mt-2 space-y-1 text-sm text-foreground" data-testid="mode-operatoire">
        <li v-for="ligne in parcours[0].mode_operatoire" :key="ligne">{{ ligne }}</li>
      </ol>
    </template>
  </section>
</template>
