<script setup lang="ts">
// Onglet « État de départ » (lot PT-01a) — DANS QUEL ÉTAT l'application est remise avant d'être testée. Reprend, tels quels,
// les réglages « bac à sable » (connecteur web, D26/D36/D37) et « calibration en écriture » (Odoo, migration 45) de la fenêtre
// « Identité et application » : mêmes champs, même route, mêmes refus du serveur (une adresse de remise à zéro d'une autre
// application est refusée, 422).
//
// Les deux réglages du bac à sable restent ENSEMBLE : l'autorisation n'a d'effet qu'avec une adresse de remise à zéro, et
// l'adresse ne sert qu'à elle. Les explications longues de l'ancien écran sont portées par une infobulle, pas par l'écran.
import { computed, reactive, ref, watch } from 'vue'
import { api, type ProjectSummary } from '../../lib/api'
import Button from '../ui/Button.vue'
import Hint from '../ui/Hint.vue'

const props = defineProps<{ projet: ProjectSummary; peutRegler: boolean }>()
const emit = defineEmits<{ (e: 'enregistre', projet: ProjectSummary): void; (e: 'modifie', valeur: boolean): void }>()

const form = reactive({ calibration_writes_enabled: false, bac_a_sable_reset: '' })
const initial = ref({ ...form })
const enregistrement = ref(false)
const erreur = ref('')
const enregistreA = ref(false)
const estWeb = computed(() => props.projet.connector_type === 'web')

function reprendre(p: ProjectSummary) {
  form.calibration_writes_enabled = !!p.calibration_writes_enabled
  form.bac_a_sable_reset = p.bac_a_sable_reset || ''
  initial.value = { ...form }
}
watch(() => props.projet, reprendre, { immediate: true })

const modifie = computed(() => form.calibration_writes_enabled !== initial.value.calibration_writes_enabled
  || form.bac_a_sable_reset !== initial.value.bac_a_sable_reset)
watch(modifie, (v) => emit('modifie', v), { immediate: true })

async function enregistrer() {
  if (!props.peutRegler || !modifie.value) return
  enregistrement.value = true
  erreur.value = ''
  enregistreA.value = false
  try {
    const patch: Record<string, string | boolean> = { calibration_writes_enabled: form.calibration_writes_enabled }
    // D26 : '' = retirer la déclaration de bac à sable. Sans objet pour Odoo, qui n'a pas d'adresse de remise à zéro.
    if (estWeb.value) patch.bac_a_sable_reset = form.bac_a_sable_reset.trim()
    const maj = await api.updateProject(props.projet.id, patch)
    const enregistre = { ...props.projet, ...maj }
    // L'onglet repart de ce que le serveur a enregistré, sans attendre que la page lui renvoie le projet.
    reprendre(enregistre)
    emit('enregistre', enregistre)
    enregistreA.value = true
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrement.value = false
  }
}

// D26 : le porteur déclare avoir remis LUI-MÊME l'application à zéro — lève la marque qui retient ses exécutions.
async function declarerRemisAZero() {
  erreur.value = ''
  try {
    const maj = await api.updateProject(props.projet.id, { bac_a_sable_remis_a_zero: true })
    emit('enregistre', { ...props.projet, ...maj })
  } catch (e: any) {
    erreur.value = e?.message || 'Déclaration impossible.'
  }
}
</script>

<template>
  <form class="rounded-xl border border-border bg-surface-raised shadow-sm" data-testid="etat-de-depart" @submit.prevent="enregistrer">
    <div v-if="projet.bac_a_sable_non_remis" role="alert" data-testid="bac-a-sable-non-remis"
         class="m-4 flex flex-wrap items-center gap-3 rounded-lg border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm sm:mx-6">
      <span>Remise à zéro en échec : les exécutions de ce projet sont retenues.</span>
      <Button type="button" variant="secondary" size="sm" class="ml-auto" data-testid="bac-a-sable-declarer-remis"
              :disabled="!peutRegler" @click="declarerRemisAZero">L'application a été remise à zéro</Button>
    </div>
    <fieldset class="space-y-5 p-4 sm:p-6" :disabled="!peutRegler">
      <legend class="sr-only">État de départ</legend>
      <label class="flex min-h-11 items-center gap-3">
        <input type="checkbox" v-model="form.calibration_writes_enabled" class="h-4 w-4" data-testid="bac-a-sable-autorise" />
        <span class="text-sm font-medium">L'IA peut agir sur cette application pendant la génération</span>
        <Hint v-if="estWeb" text="À n'activer que sur une application réservée aux tests, que l'on peut remettre à zéro. L'IA voit alors où mène chaque action avant d'écrire le test." />
        <Hint v-else text="À n'activer que sur un environnement de test : l'IA soumet un vrai formulaire pour lire le message affiché, puis supprime ce qu'elle a créé." />
      </label>
      <label v-if="estWeb" class="block max-w-xl">
        <span class="text-sm font-medium">Adresse de remise à zéro</span>
        <Hint text="Un chemin de l'application, appelé avant et après chaque essai : toute l'application revient à son état de départ. Sans cette adresse, l'IA ne joue aucune action." />
        <input v-model="form.bac_a_sable_reset" type="text" placeholder="/reset" data-testid="bac-a-sable-reset"
               class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary disabled:cursor-not-allowed disabled:opacity-60" />
      </label>
    </fieldset>
    <div class="flex items-center justify-end gap-3 border-t border-border bg-surface px-4 py-4 sm:px-6">
      <span v-if="erreur" role="alert" class="mr-auto text-sm text-destructive">{{ erreur }}</span>
      <span v-else-if="enregistreA && !modifie" role="status" class="mr-auto text-sm text-success" data-testid="enregistre">Enregistré</span>
      <Button type="button" variant="secondary" :disabled="!modifie || enregistrement" @click="reprendre(projet)">Annuler</Button>
      <Button type="submit" variant="primary" :loading="enregistrement" :disabled="!peutRegler || !modifie">Enregistrer</Button>
    </div>
  </form>
</template>
