<script setup lang="ts">
// Gestion des comptes — Admin seulement (2026-08-07). Le SERVEUR est la seule vraie garde (403
// sur `/api/admin/users` pour tout autre rôle) ; cet écran affiche juste un message clair au lieu
// de laisser un Testeur/Dev arriver ici pour se voir refuser chaque action une par une.
import { onMounted, ref } from 'vue'
import { api, LIBELLE_ROLE, ROLES, type UserAccount } from '../lib/api'
import { useSession } from '../lib/useSession'
import Button from '../components/ui/Button.vue'
import Modal from '../components/ui/Modal.vue'

const { session } = useSession()

const comptes = ref<UserAccount[]>([])
const loading = ref(true)
const erreur = ref('')

const nouveauNom = ref('')
const nouveauMdp = ref('')
const nouveauRole = ref('testeur')
const nouvelEmail = ref('')
const creation = ref(false)

async function charger() {
  loading.value = true
  erreur.value = ''
  try {
    comptes.value = await api.listUsers()
  } catch (e: any) {
    erreur.value = e?.message || 'Impossible de charger les comptes.'
  } finally {
    loading.value = false
  }
}
onMounted(charger)

async function creer() {
  if (!nouveauNom.value.trim() || !nouveauMdp.value) return
  creation.value = true
  erreur.value = ''
  try {
    const compte = await api.createUser({
      username: nouveauNom.value.trim(), password: nouveauMdp.value, role: nouveauRole.value,
      email: nouvelEmail.value.trim(),
    })
    comptes.value = [...comptes.value, compte]
    nouveauNom.value = ''
    nouveauMdp.value = ''
    nouveauRole.value = 'testeur'
    nouvelEmail.value = ''
  } catch (e: any) {
    erreur.value = e?.message || 'Création impossible.'
  } finally {
    creation.value = false
  }
}

async function changerRole(compte: UserAccount, role: string) {
  try {
    const maj = await api.patchUser(compte.id, { role })
    comptes.value = comptes.value.map((c) => (c.id === compte.id ? maj : c))
  } catch (e: any) {
    erreur.value = e?.message || 'Changement de rôle impossible.'
  }
}

async function changerEmail(compte: UserAccount, email: string) {
  // Nécessaire pour prévenir ce compte par email (2026-08-12) — voir Réglages > Notifications.
  if (email === compte.email) return
  try {
    const maj = await api.patchUser(compte.id, { email })
    comptes.value = comptes.value.map((c) => (c.id === compte.id ? maj : c))
  } catch (e: any) {
    erreur.value = e?.message || "Changement d'email impossible."
  }
}

async function basculerActif(compte: UserAccount) {
  try {
    const maj = await api.patchUser(compte.id, { is_active: !compte.is_active })
    comptes.value = comptes.value.map((c) => (c.id === compte.id ? maj : c))
  } catch (e: any) {
    erreur.value = e?.message || 'Action impossible.'
  }
}

// ── Réinitialisation de mot de passe (2026-08-11) — pour un compte qui a oublié le sien : jusqu'ici
// aucun recours n'existait, un Admin devait modifier la base directement.
const reinitCompte = ref<UserAccount | null>(null)
const nouveauMdpReinit = ref('')
const reinitEnCours = ref(false)
const reinitErreur = ref('')

function ouvrirReinit(compte: UserAccount) {
  reinitCompte.value = compte
  nouveauMdpReinit.value = ''
  reinitErreur.value = ''
}

async function confirmerReinit() {
  if (!reinitCompte.value || !nouveauMdpReinit.value) return
  reinitEnCours.value = true
  reinitErreur.value = ''
  try {
    await api.patchUser(reinitCompte.value.id, { new_password: nouveauMdpReinit.value })
    reinitCompte.value = null
  } catch (e: any) {
    reinitErreur.value = e?.message || 'Réinitialisation impossible.'
  } finally {
    reinitEnCours.value = false
  }
}
</script>

<template>
  <div class="mx-auto max-w-4xl p-6 md:p-8">
    <RouterLink to="/" class="text-sm text-primary hover:underline">← Retour</RouterLink>
    <h1 class="mt-3 text-xl font-semibold">Comptes utilisateurs</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Un compte se crée ici — il n'existe aucune inscription libre. Désactiver un compte ne le
      supprime pas : son historique (cas créés, résultats saisis) reste intact.
    </p>

    <p v-if="session && session.role !== 'admin'"
       class="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      Cet écran est réservé au rôle Admin.
    </p>

    <p v-if="erreur" class="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {{ erreur }}
    </p>

    <section class="mt-6 rounded-lg border border-border bg-surface-raised p-4">
      <h2 class="font-medium">Nouveau compte</h2>
      <div class="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_1fr_auto_auto]">
        <input v-model="nouveauNom" placeholder="Identifiant"
               class="rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none" />
        <input v-model="nouveauMdp" type="password" placeholder="Mot de passe initial"
               class="rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none" />
        <input v-model="nouvelEmail" type="email" placeholder="Email (facultatif)"
               class="rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none" />
        <select v-model="nouveauRole"
                class="rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none">
          <option v-for="r in ROLES" :key="r" :value="r">{{ LIBELLE_ROLE[r] }}</option>
        </select>
        <Button variant="primary" :disabled="creation || !nouveauNom.trim() || !nouveauMdp" @click="creer">
          {{ creation ? 'Création…' : 'Créer' }}
        </Button>
      </div>
    </section>

    <p v-if="loading" class="mt-6 text-sm text-muted-foreground">Chargement…</p>

    <table v-else class="mt-6 w-full border-collapse text-sm">
      <thead>
        <tr class="text-left text-xs uppercase tracking-wider text-muted-foreground">
          <th class="py-2">Identifiant</th>
          <th class="py-2">Rôle</th>
          <th class="py-2">Email</th>
          <th class="py-2">État</th>
          <th class="py-2"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in comptes" :key="c.id" class="border-t border-border">
          <td class="py-2">{{ c.username }}</td>
          <td class="py-2">
            <select :value="c.role" @change="changerRole(c, ($event.target as HTMLSelectElement).value)"
                    class="rounded-md bg-surface border border-border px-2 py-1 focus:border-primary outline-none">
              <option v-for="r in ROLES" :key="r" :value="r">{{ LIBELLE_ROLE[r] }}</option>
            </select>
          </td>
          <td class="py-2">
            <input :value="c.email" type="email" placeholder="—"
                   @change="changerEmail(c, ($event.target as HTMLInputElement).value.trim())"
                   class="w-full rounded-md bg-surface border border-border px-2 py-1 focus:border-primary outline-none" />
          </td>
          <td class="py-2">
            <!-- Jamais la couleur seule : le texte porte l'information. -->
            <span :class="c.is_active ? 'text-success' : 'text-muted-foreground'">
              {{ c.is_active ? 'Actif' : 'Désactivé' }}
            </span>
          </td>
          <td class="py-2 text-right">
            <button class="text-sm text-primary hover:underline" @click="ouvrirReinit(c)">
              Réinitialiser le mot de passe
            </button>
            <button class="ml-3 text-sm text-primary hover:underline" @click="basculerActif(c)">
              {{ c.is_active ? 'Désactiver' : 'Réactiver' }}
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- ════════ Réinitialisation de mot de passe ════════ -->
    <Modal :open="!!reinitCompte"
           :title="reinitCompte ? `Réinitialiser le mot de passe de « ${reinitCompte.username} »` : ''"
           subtitle="Le titulaire devra utiliser ce nouveau mot de passe dès sa prochaine connexion."
           @close="reinitCompte = null">
      <form id="form-reinit-mdp" class="space-y-2" @submit.prevent="confirmerReinit">
        <label class="block">
          <span class="text-sm font-medium">Nouveau mot de passe</span>
          <input v-model="nouveauMdpReinit" type="password" autofocus
                 class="mt-1 w-full rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none" />
        </label>
        <p v-if="reinitErreur" class="text-sm text-destructive">{{ reinitErreur }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="reinitCompte = null">Annuler</Button>
        <Button type="submit" form="form-reinit-mdp" variant="primary" :loading="reinitEnCours" :disabled="!nouveauMdpReinit">Réinitialiser</Button>
      </template>
    </Modal>
  </div>
</template>
