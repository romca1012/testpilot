<script setup lang="ts">
// Onglet « État de départ » (lot PT-01a) — DANS QUEL ÉTAT l'application est remise avant d'être testée. Reprend, tels quels,
// les réglages « bac à sable » (connecteur web, D26/D36/D37) et « calibration en écriture » (Odoo, migration 45) de la fenêtre
// « Identité et application » : mêmes champs, même route, mêmes refus du serveur (une adresse de remise à zéro d'une autre
// application est refusée, 422).
//
// A45 (2026-10-16) : pour Odoo, la case « L'IA peut agir » ne suffit pas — le projet doit aussi se déclarer instance de test.
// C'est la seconde condition d'Odoo, comme l'adresse de remise à zéro est celle du web.
//
// Les deux réglages du bac à sable restent ENSEMBLE : l'autorisation n'a d'effet qu'avec une adresse de remise à zéro, et
// l'adresse ne sert qu'à elle. Les explications longues de l'ancien écran sont portées par une infobulle, pas par l'écran.
import { computed, reactive, ref, watch } from 'vue'
import { api, type ProjectSummary } from '../../lib/api'
import Button from '../ui/Button.vue'
import { projetEnregistre } from './fusion'
import Hint from '../ui/Hint.vue'
import ConfirmDialog from '../ConfirmDialog.vue'

const props = defineProps<{ projet: ProjectSummary; peutRegler: boolean }>()
const emit = defineEmits<{ (e: 'enregistre', projet: ProjectSummary): void; (e: 'modifie', valeur: boolean): void }>()

const form = reactive({ calibration_writes_enabled: false, instance_de_test: false, bac_a_sable_reset: '' })
const initial = ref({ ...form })
const enregistrement = ref(false)
const erreur = ref('')
const enregistreA = ref(false)
const estWeb = computed(() => props.projet.connector_type === 'web')

const modifie = computed(() => form.calibration_writes_enabled !== initial.value.calibration_writes_enabled
  || form.instance_de_test !== initial.value.instance_de_test
  || form.bac_a_sable_reset !== initial.value.bac_a_sable_reset)
watch(modifie, (v) => emit('modifie', v), { immediate: true })
// 3. Revue du 2026-10-13 : depuis que l'adresse du projet se change dans une autre fenêtre, une déclaration de remise à zéro
// peut rester attachée à l'ANCIENNE adresse. Le serveur coupe alors les essais de l'IA (bon sens : rien n'est joué sur la
// nouvelle adresse) — mais l'écran montrait une case cochée et une adresse déclarée, le contraire de l'état réel.
const declarationPerimee = computed(() => {
  const remise = props.projet.bac_a_sable_reset || ''
  if (!remise || !props.projet.base_url) return false   // étape 4 (A71) : tous les connecteurs
  try {
    return new URL(remise).origin !== new URL(props.projet.base_url).origin
  } catch {
    return false  // adresse non absolue : rien à comparer, le serveur fait foi
  }
})
const aConfirmer = ref(false)

function reprendre(p: ProjectSummary) {
  form.calibration_writes_enabled = !!p.calibration_writes_enabled
  form.instance_de_test = !!p.instance_de_test
  form.bac_a_sable_reset = p.bac_a_sable_reset || ''
  initial.value = { ...form }
}
// La page renvoie le projet après chaque enregistrement : on ne reprend ses valeurs que si rien n'est en cours de saisie
// (revue du 2026-10-13 : déclarer la remise à zéro effaçait une adresse tapée mais pas encore enregistrée).
reprendre(props.projet)
watch(() => props.projet, (p) => { if (!modifie.value) reprendre(p) })


async function enregistrer() {
  if (!props.peutRegler || !modifie.value) return
  enregistrement.value = true
  erreur.value = ''
  enregistreA.value = false
  try {
    const patch: Record<string, string | boolean> = { calibration_writes_enabled: form.calibration_writes_enabled }
    // D26 : '' = retirer la déclaration de bac à sable. Étape 4 (A71) : Odoo aussi a une adresse de remise à zéro.
    patch.bac_a_sable_reset = form.bac_a_sable_reset.trim()
    // Revue A47 : envoyée seulement si la personne l'a changée — renvoyer une case lue plus tôt pourrait redéclarer une
    // application qui a changé entre-temps dans un autre onglet. Odoo seulement (A45).
    if (!estWeb.value && form.instance_de_test !== initial.value.instance_de_test) patch.instance_de_test = form.instance_de_test
    const maj = await api.updateProject(props.projet.id, patch)
    const enregistre = projetEnregistre(props.projet, maj)
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
  aConfirmer.value = false
  erreur.value = ''
  try {
    const maj = await api.updateProject(props.projet.id, { bac_a_sable_remis_a_zero: true })
    emit('enregistre', projetEnregistre(props.projet, maj))
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
              :disabled="!peutRegler" @click="aConfirmer = true">L'application a été remise à zéro</Button>
    </div>
    <div v-if="declarationPerimee" role="status" data-testid="declaration-perimee"
         class="m-4 rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm sm:mx-6">
      L'adresse de remise à zéro n'est plus celle de l'application du projet : l'IA ne joue aucune action tant qu'elle n'est pas redéclarée.
    </div>
    <fieldset class="p-4 sm:p-6" :disabled="!peutRegler">
      <legend class="sr-only">État de départ</legend>
      <label class="flex min-h-11 items-center gap-3">
        <input type="checkbox" v-model="form.calibration_writes_enabled" class="h-4 w-4" data-testid="bac-a-sable-autorise" />
        <span class="text-sm font-medium">L'IA peut agir sur cette application pendant la génération</span>
        <Hint v-if="estWeb" text="L'IA joue ses actions pour voir où elles mènent avant d'écrire le test. Seulement avec une adresse de remise à zéro." />
        <Hint v-else text="L'IA soumet un vrai formulaire pour lire le message affiché, puis supprime ce qu'elle a créé. Seulement sur une instance de test déclarée." />
      </label>
      <label v-if="!estWeb" class="mt-3 flex min-h-11 items-center gap-3">
        <input type="checkbox" v-model="form.instance_de_test" class="h-4 w-4" data-testid="instance-de-test" />
        <span class="text-sm font-medium">Instance de test</span>
        <Hint text="Sans cette déclaration, l'IA n'écrit jamais dans une application Odoo, même autorisée." />
      </label>
      <label class="mt-5 block max-w-xl">
        <span class="text-sm font-medium">Adresse de remise à zéro</span>
        <Hint text="Un chemin de l'application qui la remet à son état de départ et répond {&quot;remis_a_zero&quot;: true}. Appelé avant chaque test, qui est alors joué seul, et avant et après chaque essai de l'IA." />
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
    <!-- Ce geste lève la retenue des exécutions : il protège le verdict, il se confirme. -->
    <ConfirmDialog :open="aConfirmer" title="Lever la retenue des exécutions ?"
                   message="À confirmer seulement si l'application a bien été remise dans son état de départ."
                   confirm-label="Confirmer" @confirm="declarerRemisAZero" @cancel="aConfirmer = false" />
  </form>
</template>
