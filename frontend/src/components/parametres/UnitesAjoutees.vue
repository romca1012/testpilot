<script setup lang="ts">
// « Unités ajoutées » (lot PT-03, décision du porteur du 2026-10-13) — les unités propres au projet (« palette », « point de
// fidélité ») et leurs autres écritures. L'outil reconnaît alors « 12 Palettes » et « 12 palettes » comme la même unité ;
// il ne convertit rien. Le serveur valide chaque écriture avec les règles du lecteur de nombres : une unité qu'il connaît
// déjà (« kg », « € ») est refusée, et son message est montré tel quel.
import { computed, onMounted, ref, watch } from 'vue'
import { api, type ProjectSummary, type ProjectUnit } from '../../lib/api'
import Button from '../ui/Button.vue'
import Modal from '../ui/Modal.vue'
import ConfirmDialog from '../ConfirmDialog.vue'

const props = defineProps<{ projet: ProjectSummary; peutRegler: boolean }>()

const unites = ref<ProjectUnit[]>([])
const erreur = ref('')
// `null` = fenêtre fermée ; 'nouvelle' = ajout ; un nombre = modification de cette unité.
const enCours = ref<number | 'nouvelle' | null>(null)
const form = ref({ nom: '', ecritures: '' })
const erreurFormulaire = ref('')
const enregistrement = ref(false)
const aSupprimer = ref<ProjectUnit | null>(null)
const suppression = ref(false)

// Les autres écritures se saisissent séparées par des virgules : « palettes, Palettes ».
const ecrituresSaisies = computed(() => form.value.ecritures.split(',').map((e) => e.trim()).filter(Boolean))

async function charger() {
  erreur.value = ''
  try {
    unites.value = await api.listProjectUnits(props.projet.id)
  } catch (e: any) {
    erreur.value = e?.message || 'Les unités n\'ont pas pu être chargées.'
  }
}
onMounted(charger)
watch(() => props.projet.id, charger)

function ajouter() {
  form.value = { nom: '', ecritures: '' }
  erreurFormulaire.value = ''
  enCours.value = 'nouvelle'
}
function modifier(u: ProjectUnit) {
  form.value = { nom: u.nom, ecritures: u.ecritures.join(', ') }
  erreurFormulaire.value = ''
  enCours.value = u.id
}

async function enregistrer() {
  if (!props.peutRegler || enCours.value === null || !form.value.nom.trim()) return
  enregistrement.value = true
  erreurFormulaire.value = ''
  const corps = { nom: form.value.nom.trim(), ecritures: ecrituresSaisies.value }
  try {
    if (enCours.value === 'nouvelle') await api.createProjectUnit(props.projet.id, corps)
    else await api.updateProjectUnit(props.projet.id, enCours.value, corps)
    enCours.value = null
    await charger()
  } catch (e: any) {
    erreurFormulaire.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrement.value = false
  }
}

async function supprimer() {
  if (!aSupprimer.value) return
  suppression.value = true
  try {
    await api.deleteProjectUnit(props.projet.id, aSupprimer.value.id)
    aSupprimer.value = null
    await charger()
  } catch (e: any) {
    erreur.value = e?.message || 'Suppression impossible.'
    aSupprimer.value = null
  } finally {
    suppression.value = false
  }
}
</script>

<template>
  <section class="mt-5 rounded-xl border border-border bg-surface-raised shadow-sm" data-testid="unites-ajoutees" aria-labelledby="titre-unites-ajoutees">
    <h2 id="titre-unites-ajoutees" class="px-4 pt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground sm:px-6 sm:pt-6">Unités ajoutées</h2>
    <p v-if="erreur" role="alert" class="mx-4 mt-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive sm:mx-6" data-testid="unite-erreur">{{ erreur }}</p>
    <div class="mt-3 overflow-x-auto overflow-y-hidden">
      <table v-if="unites.length" class="w-full text-sm">
        <thead>
          <tr class="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" class="px-4 py-3 font-medium sm:px-6">Unité</th>
            <th scope="col" class="px-4 py-3 font-medium">Autres écritures</th>
            <th scope="col" class="px-4 py-3"><span class="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in unites" :key="u.id" class="border-b border-border last:border-0" data-testid="unite">
            <td class="px-4 py-3 font-medium sm:px-6">{{ u.nom }}</td>
            <td class="px-4 py-3 text-muted-foreground">{{ u.ecritures.join(', ') || '—' }}</td>
            <td class="px-4 py-3 text-right whitespace-nowrap">
              <template v-if="peutRegler">
                <Button type="button" variant="ghost" size="sm" @click="modifier(u)">Modifier</Button>
                <Button type="button" variant="ghost" size="sm" class="text-destructive" @click="aSupprimer = u">Supprimer</Button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else-if="!erreur" class="px-4 pb-4 text-sm text-muted-foreground sm:px-6" data-testid="aucune-unite">Aucune</p>
    </div>
    <div v-if="peutRegler" class="flex justify-end border-t border-border bg-surface px-4 py-4 sm:px-6">
      <Button type="button" variant="primary" data-testid="unite-ajouter" @click="ajouter">Ajouter une unité</Button>
    </div>

    <Modal :open="enCours !== null" :title="enCours === 'nouvelle' ? 'Ajouter une unité' : 'Modifier l\'unité'" @close="enCours = null">
      <form id="form-unite" class="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="unite-formulaire" @submit.prevent="enregistrer">
        <label class="block"><span class="text-sm font-medium">Unité <span class="text-destructive" aria-hidden="true">*</span></span>
          <input v-model="form.nom" required maxlength="24" placeholder="palette" data-testid="unite-nom"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        <label class="block"><span class="text-sm font-medium">Autres écritures</span>
          <input v-model="form.ecritures" placeholder="palettes, Palettes" data-testid="unite-ecritures"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        <p v-if="erreurFormulaire" role="alert" class="text-sm text-destructive sm:col-span-2">{{ erreurFormulaire }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="enCours = null">Annuler</Button>
        <Button type="submit" form="form-unite" variant="primary" data-testid="unite-enregistrer" :loading="enregistrement"
                :disabled="!form.nom.trim()">Enregistrer</Button>
      </template>
    </Modal>

    <ConfirmDialog :open="aSupprimer !== null" title="Supprimer cette unité ?"
                   :message="`« ${aSupprimer?.nom || ''} » ne sera plus reconnue par les tests.`"
                   confirm-label="Supprimer" :busy="suppression" @confirm="supprimer" @cancel="aSupprimer = null" />
  </section>
</template>
