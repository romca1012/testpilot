<script setup lang="ts">
// Lot PT-04a (A48 à A50) : le groupe « Environnement » de l'onglet « Configurations » — où rejouer les tests (recette,
// préproduction…). L'environnement par défaut est le projet lui-même : son adresse se règle dans « Identité et application »,
// seul son nom change ici. Un environnement ajouté déclare sa nature, sans valeur par défaut (A48) : « Production » est
// affiché mais jamais joué. Même présentation que l'onglet « Comptes » : un tableau, une fenêtre pour ajouter ou modifier.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, type Environnement, type ProjectSummary } from '../../lib/api'
import Button from '../ui/Button.vue'
import Modal from '../ui/Modal.vue'
import ConfirmDialog from '../ConfirmDialog.vue'

const props = defineProps<{ projet: ProjectSummary; peutRegler: boolean }>()

const environnements = ref<Environnement[]>([])
const chargement = ref(true)
const erreur = ref('')
const enCours = ref<Environnement | 'nouveau' | null>(null)
const form = reactive({ nom: '', base_url: '', connector_version: '', database: '', oracle_base_url: '', nature: '' })
const erreurFormulaire = ref('')
const enregistrement = ref(false)
const aSupprimer = ref<Environnement | null>(null)
const suppression = ref(false)
const estOdoo = computed(() => props.projet.connector_type === 'odoo')
const estDefaut = computed(() => enCours.value !== null && enCours.value !== 'nouveau' && enCours.value.est_defaut)
// Un environnement Odoo déclare sa base (le serveur l'exige aussi) : jamais celle du projet reprise à sa place.
const formulaireValide = computed(() => !!form.nom.trim() && (estDefaut.value
  || (!!form.base_url.trim() && !!form.nature && (!estOdoo.value || !!form.database.trim()))))

async function charger() {
  chargement.value = true
  try {
    environnements.value = await api.listEnvironnements(props.projet.id)
    erreur.value = ''
  } catch (e: any) {
    erreur.value = e?.message || 'Environnements illisibles.'
  } finally {
    chargement.value = false
  }
}

function ouvrir(e: Environnement | 'nouveau') {
  const source = e === 'nouveau' ? null : e
  Object.assign(form, {
    nom: source?.nom ?? '', base_url: source?.base_url ?? '', connector_version: source?.connector_version ?? '',
    database: source?.database ?? '', oracle_base_url: source?.oracle_base_url ?? '',
    nature: source && !source.est_defaut ? source.nature : '',   // A48 : jamais de nature choisie à la place de la personne
  })
  erreurFormulaire.value = ''
  enCours.value = e
}

async function enregistrer() {
  if (!formulaireValide.value || enCours.value === null) return
  enregistrement.value = true
  erreurFormulaire.value = ''
  try {
    const corps = estDefaut.value ? { nom: form.nom.trim() } : { ...form, nom: form.nom.trim() }
    environnements.value = enCours.value === 'nouveau'
      ? await api.createEnvironnement(props.projet.id, corps)
      : await api.updateEnvironnement(props.projet.id, enCours.value.id, corps)
    enCours.value = null
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
    await api.deleteEnvironnement(props.projet.id, aSupprimer.value.id)
    aSupprimer.value = null
    await charger()
  } catch (e: any) {
    aSupprimer.value = null
    erreur.value = e?.message || 'Suppression impossible.'
  } finally {
    suppression.value = false
  }
}

watch(() => props.projet.id, charger)
// Le défaut reflète l'adresse du projet : elle peut changer dans « Identité et application » pendant que la page est ouverte.
watch(() => [props.projet.base_url, props.projet.database], charger)
onMounted(charger)
</script>

<template>
  <section class="rounded-xl border border-border bg-surface-raised shadow-sm" data-testid="environnements">
    <div class="px-4 pt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground sm:px-6" aria-hidden="true">Environnement</div>
    <p v-if="erreur" role="alert" class="m-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{{ erreur }}</p>
    <div class="overflow-x-auto overflow-y-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" class="px-4 py-3 font-medium">Nom</th>
            <th scope="col" class="px-4 py-3 font-medium">Adresse</th>
            <th scope="col" class="px-4 py-3 font-medium">Version</th>
            <th scope="col" class="px-4 py-3 font-medium">Nature</th>
            <th scope="col" class="px-4 py-3"><span class="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in environnements" :key="e.id" class="border-b border-border/60 last:border-b-0" data-testid="environnement-ligne">
            <td class="px-4 py-3 font-semibold">{{ e.nom }}</td>
            <td class="px-4 py-3 break-all">{{ e.base_url || '—' }}<span v-if="e.database" class="text-muted-foreground"> · {{ e.database }}</span></td>
            <td class="px-4 py-3">{{ e.connector_version || '—' }}</td>
            <td class="px-4 py-3">
              <span :class="['rounded-full px-2.5 py-1 text-xs font-medium',
                             e.nature === 'production' ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground']"
                    :data-testid="`nature-${e.id}`">{{ e.nature_libelle }}</span>
            </td>
            <td class="px-4 py-2 text-right">
              <span class="inline-flex items-center gap-1.5">
                <span v-if="e.est_defaut" class="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">Par défaut</span>
                <template v-if="peutRegler">
                  <Button type="button" variant="ghost" size="sm" :data-testid="`environnement-modifier-${e.id}`" @click="ouvrir(e)">Modifier</Button>
                  <Button v-if="!e.est_defaut" type="button" variant="ghost" size="sm" class="text-destructive"
                          :data-testid="`environnement-supprimer-${e.id}`" @click="aSupprimer = e">Supprimer</Button>
                </template>
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="peutRegler" class="flex justify-end border-t border-border bg-surface px-4 py-4 sm:px-6">
      <Button type="button" variant="primary" data-testid="environnement-ajouter" @click="ouvrir('nouveau')">Ajouter un environnement</Button>
    </div>

    <Modal :open="enCours !== null" :title="enCours === 'nouveau' ? 'Ajouter un environnement' : 'Modifier l’environnement'" @close="enCours = null">
      <form id="form-environnement" class="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="environnement-formulaire" @submit.prevent="enregistrer">
        <label class="block"><span class="text-sm font-medium">Nom <span class="text-destructive" aria-hidden="true">*</span></span>
          <input v-model="form.nom" required data-testid="environnement-nom"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        <template v-if="!estDefaut">
          <label class="block"><span class="text-sm font-medium">Nature <span class="text-destructive" aria-hidden="true">*</span></span>
            <select v-model="form.nature" required data-testid="environnement-nature"
                    class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary">
              <option value="" disabled>Choisir…</option>
              <option value="test">Test</option>
              <option value="production">Production</option>
            </select></label>
          <label class="block sm:col-span-2"><span class="text-sm font-medium">Adresse <span class="text-destructive" aria-hidden="true">*</span></span>
            <input v-model="form.base_url" required type="url" placeholder="https://" data-testid="environnement-adresse"
                   class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
          <label class="block"><span class="text-sm font-medium">Version</span>
            <input v-model="form.connector_version" data-testid="environnement-version"
                   class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
          <label v-if="estOdoo" class="block"><span class="text-sm font-medium">Base <span class="text-destructive" aria-hidden="true">*</span></span>
            <input v-model="form.database" required data-testid="environnement-base"
                   class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
          <label class="block sm:col-span-2"><span class="text-sm font-medium">Adresse de l'oracle</span>
            <input v-model="form.oracle_base_url" type="url" placeholder="https://" data-testid="environnement-oracle"
                   class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        </template>
        <p v-if="erreurFormulaire" role="alert" class="text-sm text-destructive sm:col-span-2">{{ erreurFormulaire }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="enCours = null">Annuler</Button>
        <Button type="submit" form="form-environnement" variant="primary" data-testid="environnement-enregistrer"
                :loading="enregistrement" :disabled="!formulaireValide">Enregistrer</Button>
      </template>
    </Modal>

    <ConfirmDialog :open="aSupprimer !== null" title="Supprimer cet environnement ?"
                   :message="`« ${aSupprimer?.nom || ''} » ira à la corbeille ; une planification qui le joue ne se déclenchera plus.`"
                   confirm-label="Supprimer" :busy="suppression" @confirm="supprimer" @cancel="aSupprimer = null" />
  </section>
</template>
