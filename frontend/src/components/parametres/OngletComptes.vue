<script setup lang="ts">
// Onglet « Comptes » (lot PT-01a) — QUI joue les tests. Les comptes de test du projet (lot 07b-1, D8), sortis du bas de la
// fenêtre « Identité et application » : même liste, mêmes routes, mêmes garanties.
//
// Deux invariants repris tels quels :
// 1. un mot de passe est en ÉCRITURE SEULE — jamais réaffiché, et une modification sans nouveau mot de passe ne l'envoie pas
//    (l'envoyer vide l'effacerait) ;
// 2. seuls `admin` et `dev` voient les gestes d'ajout, de modification et de suppression (le serveur tranche aussi).
// Le compte « principal » est celui de la connexion du projet : il se règle encore dans « Identité et application ».
import { onMounted, ref, watch } from 'vue'
import { api, type ProjectAccount, type ProjectSummary } from '../../lib/api'
import Button from '../ui/Button.vue'
import Hint from '../ui/Hint.vue'
import Modal from '../ui/Modal.vue'
import ConfirmDialog from '../ConfirmDialog.vue'

const props = defineProps<{ projet: ProjectSummary; peutGerer: boolean }>()

const comptes = ref<ProjectAccount[]>([])
const chargement = ref(true)
const erreur = ref('')
// `null` = fenêtre fermée ; 'nouveau' = ajout ; un nombre = modification de ce compte.
const enCours = ref<number | 'nouveau' | null>(null)
const form = ref({ label: '', username: '', password: '', business_role: '' })
const enregistrement = ref(false)
const erreurFormulaire = ref('')
const aSupprimer = ref<ProjectAccount | null>(null)
const suppression = ref(false)

async function charger() {
  chargement.value = true
  erreur.value = ''
  try {
    comptes.value = await api.listProjectAccounts(props.projet.id)
  } catch (e: any) {
    comptes.value = []
    erreur.value = e?.message || 'Comptes illisibles.'
  } finally {
    chargement.value = false
  }
}

function ajouter() {
  form.value = { label: '', username: '', password: '', business_role: '' }
  erreurFormulaire.value = ''
  enCours.value = 'nouveau'
}

function modifier(c: ProjectAccount) {
  if (c.id === null) return
  // ⚠️ mot de passe TOUJOURS vide : vide = « inchangé » (l'API ne le renvoie jamais).
  form.value = { label: c.label, username: c.username, password: '', business_role: c.business_role }
  erreurFormulaire.value = ''
  enCours.value = c.id
}

async function enregistrer() {
  if (enCours.value === null || !form.value.label.trim() || !form.value.username.trim()) return
  enregistrement.value = true
  erreurFormulaire.value = ''
  try {
    if (enCours.value === 'nouveau') {
      await api.createProjectAccount(props.projet.id, { ...form.value })
    } else {
      const patch: Record<string, string> = {
        label: form.value.label, username: form.value.username, business_role: form.value.business_role,
      }
      if (form.value.password) patch.password = form.value.password
      await api.updateProjectAccount(props.projet.id, enCours.value, patch)
    }
    enCours.value = null
    await charger()
  } catch (e: any) {
    erreurFormulaire.value = e?.message || 'Enregistrement du compte impossible.'
  } finally {
    enregistrement.value = false
  }
}

async function supprimer() {
  const c = aSupprimer.value
  if (!c || c.id === null) return
  suppression.value = true
  erreur.value = ''
  try {
    await api.deleteProjectAccount(props.projet.id, c.id)
    aSupprimer.value = null
    await charger()
  } catch (e: any) {
    aSupprimer.value = null
    erreur.value = e?.message || 'Suppression du compte impossible.'
  } finally {
    suppression.value = false
  }
}

watch(() => props.projet.id, charger)
onMounted(charger)
</script>

<template>
  <section class="rounded-xl border border-border bg-surface-raised shadow-sm" data-testid="comptes">
    <p v-if="erreur" role="alert" class="m-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive" data-testid="compte-erreur">{{ erreur }}</p>
    <div class="overflow-x-auto overflow-y-hidden">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" class="px-4 py-3 font-medium">
              Nom dans les tests
              <Hint text="Dans un test, « je me connecte en tant que … » suivi de ce nom change d'utilisateur. L'IA ne connaît que ce nom." />
            </th>
            <th scope="col" class="px-4 py-3 font-medium">Identifiant</th>
            <th scope="col" class="px-4 py-3 font-medium">Mot de passe</th>
            <th scope="col" class="px-4 py-3 font-medium">Rôle</th>
            <th scope="col" class="px-4 py-3"><span class="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in comptes" :key="c.id ?? 'principal'" class="border-b border-border/60 last:border-b-0" data-testid="compte-ligne">
            <td class="px-4 py-3 font-semibold">{{ c.label }}</td>
            <td class="px-4 py-3">{{ c.username || '—' }}</td>
            <td class="px-4 py-3" :aria-label="c.has_secret ? 'Mot de passe enregistré' : 'Aucun mot de passe'">{{ c.has_secret ? '••••••••' : '—' }}</td>
            <td class="px-4 py-3">{{ c.business_role || '—' }}</td>
            <td class="px-4 py-2 text-right">
              <span v-if="c.principal" class="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-medium text-primary">Principal</span>
              <span v-else-if="peutGerer" class="inline-flex gap-1.5">
                <Button type="button" variant="ghost" size="sm" @click="modifier(c)">Modifier</Button>
                <Button type="button" variant="ghost" size="sm" class="text-destructive" @click="aSupprimer = c">Supprimer</Button>
              </span>
            </td>
          </tr>
          <tr v-if="!chargement && !comptes.length"><td colspan="5" class="px-4 py-6 text-center text-muted-foreground">Aucun compte.</td></tr>
        </tbody>
      </table>
    </div>
    <div v-if="peutGerer" class="flex justify-end border-t border-border bg-surface px-4 py-4 sm:px-6">
      <Button type="button" variant="primary" data-testid="compte-ajouter" @click="ajouter">Ajouter un compte</Button>
    </div>

    <Modal :open="enCours !== null" :title="enCours === 'nouveau' ? 'Ajouter un compte' : 'Modifier le compte'" @close="enCours = null">
      <form id="form-compte" class="grid grid-cols-1 gap-4 sm:grid-cols-2" data-testid="compte-formulaire" @submit.prevent="enregistrer">
        <label class="block"><span class="text-sm font-medium">Nom dans les tests <span class="text-destructive" aria-hidden="true">*</span></span>
          <input v-model="form.label" required data-testid="compte-libelle"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        <label class="block"><span class="text-sm font-medium">Rôle</span>
          <input v-model="form.business_role"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        <label class="block"><span class="text-sm font-medium">Identifiant <span class="text-destructive" aria-hidden="true">*</span></span>
          <input v-model="form.username" required autocomplete="off" data-testid="compte-identifiant"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        <label class="block"><span class="text-sm font-medium">Mot de passe</span>
          <input v-model="form.password" type="password" autocomplete="new-password" data-testid="compte-mot-de-passe"
                 :placeholder="enCours === 'nouveau' ? '' : 'Inchangé'"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        <p v-if="erreurFormulaire" role="alert" class="text-sm text-destructive sm:col-span-2">{{ erreurFormulaire }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="enCours = null">Annuler</Button>
        <Button type="submit" form="form-compte" variant="primary" data-testid="compte-enregistrer" :loading="enregistrement"
                :disabled="!form.label.trim() || !form.username.trim()">Enregistrer</Button>
      </template>
    </Modal>

    <ConfirmDialog :open="aSupprimer !== null" title="Supprimer ce compte ?"
                   :message="`« ${aSupprimer?.label || ''} » ne pourra plus être utilisé par les tests.`"
                   confirm-label="Supprimer" :busy="suppression" @confirm="supprimer" @cancel="aSupprimer = null" />
  </section>
</template>
