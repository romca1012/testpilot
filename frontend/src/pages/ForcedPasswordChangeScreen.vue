<script setup lang="ts">
// Changement de mot de passe OBLIGATOIRE (audit 2026-09-07, point 1) — affiché à la place de
// l'application tant que `session.must_change_password` est vrai : compte tout juste créé par un
// Admin, ou mot de passe réinitialisé par lui. Le serveur bloque déjà TOUTE autre écriture
// (`api.ts::setPasswordChangeRequiredHandler`) — cet écran n'est pas la seule garde, juste celle
// qui évite à l'utilisateur de buter sur des erreurs 403 sans comprendre pourquoi.
//
// Distinct de `ChangePasswordModal.vue` (changement VOLONTAIRE, dismissable, ouvert depuis
// AccountMenu) : les deux appellent le même endpoint, mais celui-ci ne peut pas se fermer sans
// avoir réussi — sinon l'utilisateur resterait bloqué au prochain appel API de toute façon, pour
// une raison qu'aucun écran ne lui aurait expliquée.
import { computed, ref } from 'vue'
import { api, ApiError } from '../lib/api'
import { useSession } from '../lib/useSession'
import Button from '../components/ui/Button.vue'
import Spinner from '../components/ui/Spinner.vue'

const emit = defineEmits<{ (e: 'changed'): void }>()
const { session, charger: chargerSession } = useSession()

const longueurMin = computed(() => session.value?.password_min_length || 15)

const ancien = ref('')
const nouveau = ref('')
const confirmation = ref('')
const erreur = ref('')
const envoi = ref(false)

async function valider() {
  erreur.value = ''
  if (nouveau.value.length < longueurMin.value) {
    erreur.value = `Le nouveau mot de passe doit compter au moins ${longueurMin.value} caractères.`
    return
  }
  if (nouveau.value !== confirmation.value) {
    erreur.value = 'La confirmation ne correspond pas au nouveau mot de passe.'
    return
  }
  envoi.value = true
  try {
    await api.changePassword(ancien.value, nouveau.value)
    await chargerSession()   // doit refléter must_change_password=false pour le reste de l'app
    emit('changed')
  } catch (e: any) {
    if (e instanceof ApiError && e.code === 'mot_de_passe_incorrect') {
      erreur.value = 'Le mot de passe actuel est incorrect.'
    } else {
      erreur.value = e?.message || 'Le changement de mot de passe a échoué.'
    }
  } finally {
    envoi.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center px-4">
    <form class="w-full max-w-sm space-y-5" @submit.prevent="valider">
      <div>
        <h1 class="text-xl font-semibold tracking-tight">Choisissez votre mot de passe</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Un administrateur a créé votre compte ou réinitialisé son mot de passe. Avant de
          continuer, choisissez-en un que vous seul(e) connaissez.
        </p>
      </div>

      <div>
        <label class="text-sm font-medium">Mot de passe actuel</label>
        <input v-model="ancien" type="password" autocomplete="current-password" required
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
      </div>

      <div>
        <label class="text-sm font-medium">Nouveau mot de passe</label>
        <input v-model="nouveau" type="password" autocomplete="new-password" required
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        <span class="mt-1 block text-xs text-muted-foreground">{{ longueurMin }} caractères minimum — une phrase personnelle plutôt qu'un mot connu.</span>
      </div>

      <div>
        <label class="text-sm font-medium">Confirmer le nouveau mot de passe</label>
        <input v-model="confirmation" type="password" autocomplete="new-password" required
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
      </div>

      <p v-if="erreur" role="alert" class="text-sm text-destructive">{{ erreur }}</p>

      <Button type="submit" class="w-full" :disabled="envoi || !ancien || !nouveau || !confirmation">
        <Spinner v-if="envoi" class="h-4 w-4" />
        <span>{{ envoi ? 'Enregistrement…' : 'Valider mon nouveau mot de passe' }}</span>
      </Button>
    </form>
  </div>
</template>
