<script setup lang="ts">
// Un titulaire de compte change SON PROPRE mot de passe (2026-09-03) — jusqu'ici, seul un Admin
// pouvait en réinitialiser un (Réglages > Utilisateurs), jamais le titulaire lui-même. Ouverte
// depuis AccountMenu.vue, accessible à tout rôle connecté (y compris Lecture seule : sécuriser
// son propre compte n'est pas un geste à restreindre, voir `access.py::_ECRITURES_TOUJOURS_AUTORISEES`
// côté serveur).
import { ref, watch } from 'vue'
import { api, ApiError } from '../lib/api'
import Modal from './ui/Modal.vue'
import Button from './ui/Button.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const ancien = ref('')
const nouveau = ref('')
const confirmation = ref('')
const enCours = ref(false)
const erreur = ref('')
const succes = ref(false)

// Repart d'un formulaire propre à chaque ouverture — sinon l'ancien mot de passe saisi resterait
// visible (dans le DOM, même masqué) d'une tentative à l'autre.
watch(() => props.open, (v) => {
  if (!v) return
  ancien.value = ''
  nouveau.value = ''
  confirmation.value = ''
  erreur.value = ''
  succes.value = false
})

const LONGUEUR_MIN = 8

function fermer() {
  emit('close')
}

async function valider() {
  erreur.value = ''
  if (nouveau.value.length < LONGUEUR_MIN) {
    erreur.value = `Le nouveau mot de passe doit compter au moins ${LONGUEUR_MIN} caractères.`
    return
  }
  if (nouveau.value !== confirmation.value) {
    erreur.value = 'La confirmation ne correspond pas au nouveau mot de passe.'
    return
  }
  enCours.value = true
  try {
    await api.changePassword(ancien.value, nouveau.value)
    succes.value = true
  } catch (e: any) {
    // `mot_de_passe_incorrect` est LE cas attendu (ancien mot de passe faux) — message ciblé,
    // pas la phrase générique du serveur pour les autres refus (trop court, panne...).
    if (e instanceof ApiError && e.code === 'mot_de_passe_incorrect') {
      erreur.value = 'L’ancien mot de passe est incorrect.'
    } else {
      erreur.value = e?.message || 'Le changement de mot de passe a échoué.'
    }
  } finally {
    enCours.value = false
  }
}
</script>

<template>
  <Modal :open="open" title="Changer mon mot de passe"
         subtitle="La session en cours reste ouverte après le changement." @close="fermer">
    <div v-if="succes" class="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success" role="status">
      Mot de passe changé avec succès.
    </div>
    <form v-else id="change-password" class="space-y-4" @submit.prevent="valider">
      <p v-if="erreur" role="alert" class="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{{ erreur }}</p>
      <label class="block text-sm font-medium">Mot de passe actuel *
        <input v-model="ancien" name="old-password" type="password" autocomplete="current-password" required
               class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" />
      </label>
      <label class="block text-sm font-medium">Nouveau mot de passe *
        <input v-model="nouveau" name="new-password" type="password" autocomplete="new-password" required
               class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" />
        <span class="mt-1 block text-xs font-normal text-muted-foreground">{{ LONGUEUR_MIN }} caractères minimum</span>
      </label>
      <label class="block text-sm font-medium">Confirmer le nouveau mot de passe *
        <input v-model="confirmation" name="confirm-password" type="password" autocomplete="new-password" required
               class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" />
      </label>
    </form>
    <template #footer>
      <Button v-if="!succes" @click="fermer">Annuler</Button>
      <Button v-if="!succes" type="submit" form="change-password" variant="primary" :loading="enCours"
              :disabled="!ancien || nouveau.length < LONGUEUR_MIN || !confirmation">Changer le mot de passe</Button>
      <Button v-else variant="primary" @click="fermer">Fermer</Button>
    </template>
  </Modal>
</template>
