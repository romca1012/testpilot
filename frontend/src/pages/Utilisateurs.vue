<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ACCES_PROJET_REFUSE, api, LIBELLE_ROLE, ROLES,
  type ProjectSummary, type UserAccount, type UserCreateResult, type UserGroup, type UserProjectChoice,
} from '../lib/api'
import Button from '../components/ui/Button.vue'
import Modal from '../components/ui/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { DESCRIPTION_ROLE } from '../lib/roles'

const comptes = ref<UserAccount[]>([])
const groupes = ref<UserGroup[]>([])
const route = useRoute()
const router = useRouter()
const projets = ref<ProjectSummary[]>([])
const loading = ref(true)
const erreur = ref('')
const recherche = ref('')
const ongletInitial = route.query.tab === 'roles' ? 'roles' : route.query.tab === 'groups' ? 'groups' : 'users'
const onglet = ref<'users' | 'groups' | 'roles'>(ongletInitial)
const showCreate = ref(false)
const creation = ref(false)
const nouveau = ref({ username: '', password: '', email: '', role: 'testeur' })
// Affiché juste après la création (audit 2026-09-09) : le SEUL moment où le mot de passe
// temporaire est visible si aucun email n'a pu partir — voir `creer()`.
const resultatCreation = ref<UserCreateResult | null>(null)
const accesCreation = ref<Record<number, string>>({})
const showGroup = ref(false)
const savingGroup = ref(false)
const groupForm = ref<{ id: number | null; name: string; user_ids: number[] }>({ id: null, name: '', user_ids: [] })
const groupToDelete = ref<UserGroup | null>(null)
const deletingGroup = ref(false)

const comptesFiltres = computed(() => {
  const q = recherche.value.trim().toLocaleLowerCase('fr')
  if (!q) return comptes.value
  return comptes.value.filter(c => `${c.username} ${c.email}`.toLocaleLowerCase('fr').includes(q))
})

async function charger() {
  loading.value = true
  erreur.value = ''
  try { [comptes.value, projets.value, groupes.value] = await Promise.all([api.listUsers(), api.listAdminProjects(), api.listUserGroups()]) }
  catch (e: any) { erreur.value = e?.message || 'Impossible de charger les utilisateurs.' }
  finally { loading.value = false }
}
onMounted(charger)

function ouvrirCreation() {
  nouveau.value = { username: '', password: '', email: '', role: 'testeur' }
  accesCreation.value = Object.fromEntries(projets.value.map(p => [p.id, ACCES_PROJET_REFUSE]))
  showCreate.value = true
}

function choixProjets(source: Record<number, string>): UserProjectChoice[] {
  return Object.entries(source)
    .filter(([, role]) => role !== ACCES_PROJET_REFUSE)
    .map(([project_id, role]) => ({ project_id: Number(project_id), role }))
}

async function creer() {
  // Le mot de passe est FACULTATIF (audit 2026-09-09) — vide fait générer un temporaire côté
  // serveur, envoyé par email. S'il est saisi, la politique (8 caractères mini) s'applique quand
  // même : un choix explicite reste un choix vérifié.
  if (!nouveau.value.username.trim()) return
  if (nouveau.value.password && nouveau.value.password.length < 8) return
  creation.value = true
  erreur.value = ''
  try {
    const compte = await api.createUser({
      username: nouveau.value.username.trim(), password: nouveau.value.password || undefined,
      email: nouveau.value.email.trim(), role: nouveau.value.role,
      projects: choixProjets(accesCreation.value),
    })
    comptes.value = [...comptes.value, compte].sort((a, b) => a.username.localeCompare(b.username))
    showCreate.value = false
    // Le mot de passe temporaire n'est JAMAIS reconsultable ensuite — c'est maintenant ou jamais.
    if (!compte.email_envoye) resultatCreation.value = compte
  } catch (e: any) { erreur.value = e?.message || 'Création impossible.' }
  finally { creation.value = false }
}

async function ouvrirEdition(c: UserAccount) {
  await router.push({ name: 'utilisateur-detail', params: { id: c.id } })
}

function ouvrirGroupe(groupe?: UserGroup) {
  groupForm.value = groupe
    ? { id: groupe.id, name: groupe.name, user_ids: groupe.members.map(m => m.id) }
    : { id: null, name: '', user_ids: [] }
  showGroup.value = true
}

function basculerMembre(userId: number, checked: boolean) {
  const ids = new Set(groupForm.value.user_ids)
  checked ? ids.add(userId) : ids.delete(userId)
  groupForm.value.user_ids = [...ids]
}

async function enregistrerGroupe() {
  if (!groupForm.value.name.trim()) return
  savingGroup.value = true
  erreur.value = ''
  try {
    const payload = { name: groupForm.value.name.trim(), user_ids: groupForm.value.user_ids }
    const saved = groupForm.value.id
      ? await api.updateUserGroup(groupForm.value.id, payload)
      : await api.createUserGroup(payload)
    groupes.value = [...groupes.value.filter(g => g.id !== saved.id), saved]
      .sort((a, b) => a.name.localeCompare(b.name))
    showGroup.value = false
  } catch (e: any) { erreur.value = e?.message || 'Enregistrement du groupe impossible.' }
  finally { savingGroup.value = false }
}

async function supprimerGroupe() {
  if (!groupToDelete.value) return
  deletingGroup.value = true
  erreur.value = ''
  try {
    await api.deleteUserGroup(groupToDelete.value.id)
    groupes.value = groupes.value.filter(g => g.id !== groupToDelete.value?.id)
    groupToDelete.value = null
  } catch (e: any) { erreur.value = e?.message || 'Suppression du groupe impossible.' }
  finally { deletingGroup.value = false }
}

const actifs = computed(() => comptes.value.filter(c => c.is_active).length)
</script>

<template>
  <div class="px-4 py-6 sm:px-6 md:px-8">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Administration</div>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight">Utilisateurs et rôles</h1>
        <p class="mt-2 max-w-3xl text-sm text-muted-foreground">Gérez les comptes, leurs rôles et les projets auxquels ils peuvent accéder.</p>
        <p v-if="!loading" class="mt-2 text-xs text-muted-foreground">{{ actifs }} actif{{ actifs > 1 ? 's' : '' }} · {{ comptes.length - actifs }} inactif{{ comptes.length - actifs > 1 ? 's' : '' }}</p>
      </div>
      <Button variant="primary" size="lg" @click="ouvrirCreation">+ Ajouter un utilisateur</Button>
    </header>

    <p v-if="erreur" role="alert" class="mt-5 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{{ erreur }}</p>

    <nav class="mt-6 flex gap-6 border-b border-border" aria-label="Gestion des utilisateurs">
      <button class="min-h-11 border-b-2 px-1 text-sm font-semibold" :class="onglet === 'users' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'" @click="onglet = 'users'">UTILISATEURS</button>
      <button class="min-h-11 border-b-2 px-1 text-sm font-semibold" :class="onglet === 'groups' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'" @click="onglet = 'groups'">GROUPES</button>
      <button class="min-h-11 border-b-2 px-1 text-sm font-semibold" :class="onglet === 'roles' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'" @click="onglet = 'roles'">RÔLES</button>
    </nav>

    <section v-if="onglet === 'users'" class="mt-4 overflow-hidden rounded-lg border border-border bg-surface">
      <div class="border-b border-border bg-surface-raised p-3">
        <label class="block max-w-xl"><span class="sr-only">Rechercher un utilisateur</span><input v-model="recherche" type="search" placeholder="Rechercher par identifiant ou adresse email" class="h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
      </div>
      <p v-if="loading" class="p-6 text-sm text-muted-foreground">Chargement…</p>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[860px] text-sm">
          <thead class="bg-surface-raised text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th class="px-4 py-3">Utilisateur</th><th class="px-4 py-3">Adresse email</th><th class="px-4 py-3">Statut</th><th class="px-4 py-3">Rôle</th><th class="px-4 py-3 text-right">Actions</th></tr></thead>
          <tbody><tr v-for="c in comptesFiltres" :key="c.id" class="border-t border-border hover:bg-accent/20">
            <th class="px-4 py-3 text-left font-medium"><button class="text-primary hover:underline" @click="ouvrirEdition(c)">{{ c.username }}</button></th>
            <td class="px-4 py-3 text-muted-foreground">{{ c.email || 'Non renseignée' }}</td>
            <td class="px-4 py-3"><span class="inline-flex rounded-full px-2.5 py-1 text-xs font-medium" :class="c.is_active ? 'bg-success/10 text-success' : 'bg-secondary text-muted-foreground'">{{ c.is_active ? 'Actif' : 'Inactif' }}</span></td>
            <td class="px-4 py-3">{{ LIBELLE_ROLE[c.role] || c.role }}</td>
            <td class="px-4 py-3 text-right"><Button variant="ghost" size="sm" @click="ouvrirEdition(c)">Modifier</Button></td>
          </tr></tbody>
        </table>
        <p v-if="!comptesFiltres.length" class="p-8 text-center text-sm text-muted-foreground">Aucun utilisateur ne correspond à cette recherche.</p>
      </div>
    </section>

    <section v-else-if="onglet === 'groups'" class="mt-4 overflow-hidden rounded-lg border border-border bg-surface">
      <div class="flex items-center justify-between gap-4 border-b border-border bg-surface-raised px-4 py-3">
        <div><h2 class="font-semibold">Groupes d’utilisateurs</h2><p class="mt-1 text-xs text-muted-foreground">Regroupez les membres d’une même équipe pour préparer la gestion collective des accès.</p></div>
        <Button variant="primary" @click="ouvrirGroupe()">+ Ajouter un groupe</Button>
      </div>
      <div v-if="groupes.length" class="divide-y divide-border">
        <div v-for="g in groupes" :key="g.id" class="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div><button class="min-h-11 text-left font-medium text-primary hover:underline" @click="ouvrirGroupe(g)">{{ g.name }}</button><p class="text-sm text-muted-foreground">{{ g.member_count }} membre{{ g.member_count > 1 ? 's' : '' }}<span v-if="g.members.length"> · {{ g.members.map(m => m.username).join(', ') }}</span></p></div>
          <div class="flex gap-2"><Button variant="ghost" size="sm" @click="ouvrirGroupe(g)">Modifier</Button><Button variant="danger" size="sm" @click="groupToDelete = g">Supprimer</Button></div>
        </div>
      </div>
      <div v-else class="p-8 text-center"><p class="font-medium">Aucun groupe</p><p class="mt-1 text-sm text-muted-foreground">Créez un groupe pour rassembler les utilisateurs d’une équipe.</p></div>
    </section>

    <section v-else class="mt-4 overflow-hidden rounded-lg border border-border bg-surface">
      <div class="bg-surface-raised px-4 py-3 text-sm font-medium">Rôle</div>
      <div v-for="r in ROLES" :key="r" class="flex items-center justify-between gap-4 border-t border-border px-4 py-3"><div><button class="min-h-11 text-left font-medium text-primary hover:underline" @click="router.push({ name: 'role-detail', params: { role: r } })">{{ LIBELLE_ROLE[r] }}</button><p class="text-sm text-muted-foreground">{{ DESCRIPTION_ROLE[r] }}</p></div><div class="flex shrink-0 items-center gap-2"><span v-if="r === 'admin'" class="rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success">Administration</span><Button variant="ghost" size="sm" @click="router.push({ name: 'role-detail', params: { role: r } })">Voir les permissions</Button></div></div>
    </section>

    <Modal :open="showCreate" title="Ajouter un utilisateur" subtitle="Créez le compte puis définissez ses accès aux projets." max-width="max-w-3xl" @close="showCreate = false">
      <form id="create-user" class="space-y-5" @submit.prevent="creer">
        <div class="grid gap-4 sm:grid-cols-2">
          <label class="text-sm font-medium">Identifiant *<input v-model="nouveau.username" name="username" autofocus class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" /></label>
          <label class="text-sm font-medium">Adresse email<input v-model="nouveau.email" name="email" type="email" class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" /></label>
          <label class="text-sm font-medium">Mot de passe initial<input v-model="nouveau.password" name="new-password" type="password" autocomplete="new-password" class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" /><span class="mt-1 block text-xs font-normal text-muted-foreground">Facultatif — laissez vide pour en générer un et l’envoyer par email à ce compte (8 caractères minimum si vous le saisissez vous-même).</span></label>
          <label class="text-sm font-medium">Rôle dans l’instance *<select v-model="nouveau.role" class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3"><option v-for="r in ROLES" :key="r" :value="r">{{ LIBELLE_ROLE[r] }}</option></select></label>
        </div>
        <fieldset><legend class="font-semibold">Accès aux projets</legend><p class="mt-1 text-xs text-muted-foreground">« Aucun accès » masque entièrement le projet pour cet utilisateur.</p>
          <div class="mt-3 max-h-64 overflow-y-auto rounded-md border border-border"><div v-for="p in projets" :key="p.id" class="grid items-center gap-3 border-t border-border px-3 py-2 first:border-t-0 sm:grid-cols-[1fr_220px]"><span class="text-sm font-medium">{{ p.name }}</span><select v-model="accesCreation[p.id]" :aria-label="`Accès à ${p.name}`" class="h-10 rounded-md border border-border bg-surface px-2 text-sm"><option :value="ACCES_PROJET_REFUSE">Aucun accès</option><option v-for="r in ROLES" :key="r" :value="r">{{ LIBELLE_ROLE[r] }}</option></select></div><p v-if="!projets.length" class="p-4 text-sm text-muted-foreground">Aucun projet disponible.</p></div>
        </fieldset>
      </form>
      <template #footer><Button @click="showCreate = false">Annuler</Button><Button type="submit" form="create-user" variant="primary" :loading="creation" :disabled="!nouveau.username.trim() || (!!nouveau.password && nouveau.password.length < 8)">Créer l’utilisateur</Button></template>
    </Modal>

    <!-- ══ Mot de passe temporaire — SEUL moment où il est visible (audit 2026-09-09) ══
         N'apparaît QUE si l'email n'a pas pu partir (pas d'adresse, SMTP indisponible…) : c'est
         alors le seul moyen dont dispose l'Admin de transmettre l'accès. -->
    <Modal :open="!!resultatCreation" title="Compte créé" subtitle="Aucun email n'a pu être envoyé — transmettez ce mot de passe temporaire vous-même." @close="resultatCreation = null">
      <div v-if="resultatCreation" class="space-y-3">
        <p class="text-sm text-muted-foreground">Ce mot de passe ne sera plus jamais affiché. Le compte devra de toute façon en choisir un autre à sa première connexion.</p>
        <div class="rounded-md border border-border bg-surface-raised p-3">
          <div class="text-xs text-muted-foreground">Identifiant</div>
          <div class="font-mono text-sm font-medium">{{ resultatCreation.username }}</div>
          <div class="mt-2 text-xs text-muted-foreground">Mot de passe temporaire</div>
          <div class="font-mono text-sm font-medium">{{ resultatCreation.mot_de_passe_initial }}</div>
        </div>
      </div>
      <template #footer><Button variant="primary" @click="resultatCreation = null">J’ai noté le mot de passe</Button></template>
    </Modal>

    <Modal :open="showGroup" :title="groupForm.id ? 'Modifier le groupe' : 'Ajouter un groupe'" subtitle="Le groupe contient la liste complète des utilisateurs sélectionnés." max-width="max-w-2xl" @close="showGroup = false">
      <form id="group-form" class="space-y-5" @submit.prevent="enregistrerGroupe">
        <label class="block text-sm font-medium">Nom du groupe *<input v-model="groupForm.name" autofocus class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" /></label>
        <fieldset><legend class="font-semibold">Membres</legend><p class="mt-1 text-xs text-muted-foreground">Les comptes désactivés restent visibles pour conserver une composition explicite.</p>
          <div class="mt-3 max-h-72 overflow-y-auto rounded-md border border-border">
            <label v-for="c in comptes" :key="c.id" class="flex min-h-11 cursor-pointer items-center gap-3 border-t border-border px-3 py-2 first:border-t-0 hover:bg-accent/20">
              <input type="checkbox" class="h-4 w-4" :checked="groupForm.user_ids.includes(c.id)" @change="basculerMembre(c.id, ($event.target as HTMLInputElement).checked)" />
              <span class="min-w-0 flex-1"><span class="block font-medium">{{ c.username }}</span><span class="block truncate text-xs text-muted-foreground">{{ c.email || LIBELLE_ROLE[c.role] }}</span></span>
              <span v-if="!c.is_active" class="rounded-full bg-secondary px-2 py-1 text-xs text-muted-foreground">Inactif</span>
            </label>
          </div>
        </fieldset>
      </form>
      <template #footer><Button @click="showGroup = false">Annuler</Button><Button type="submit" form="group-form" variant="primary" :loading="savingGroup" :disabled="!groupForm.name.trim()">Enregistrer le groupe</Button></template>
    </Modal>

    <ConfirmDialog :open="Boolean(groupToDelete)" title="Supprimer ce groupe ?" :message="`Le groupe « ${groupToDelete?.name || ''} » sera supprimé. Les comptes utilisateurs ne seront pas supprimés.`" confirm-label="Supprimer le groupe" :busy="deletingGroup" @confirm="supprimerGroupe" @cancel="groupToDelete = null" />

  </div>
</template>
