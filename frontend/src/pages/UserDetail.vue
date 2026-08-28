<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, LIBELLE_ROLE, ROLES, type UserAccount, type UserProjectAccess } from '../lib/api'
import Button from '../components/ui/Button.vue'

const route = useRoute()
const router = useRouter()
const userId = computed(() => Number(route.params.id))
const tabs = ['user', 'access', 'auth', 'projects'] as const
type Tab = typeof tabs[number]
const tab = computed<Tab>(() => tabs.includes(route.query.tab as Tab) ? route.query.tab as Tab : 'user')

const user = ref<UserAccount | null>(null)
const projects = ref<UserProjectAccess[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const profile = ref({ email: '' })
const access = ref({ role: 'testeur', is_active: true })
const password = ref('')

async function load() {
  loading.value = true; error.value = ''; success.value = ''
  try {
    const [account, assigned] = await Promise.all([api.getUser(userId.value), api.getUserProjects(userId.value)])
    user.value = account; projects.value = assigned
    profile.value.email = account.email
    access.value = { role: account.role, is_active: account.is_active }
  } catch (e: any) { error.value = e?.message || 'Impossible de charger cet utilisateur.' }
  finally { loading.value = false }
}
onMounted(load)
watch(userId, load)

function goTab(next: Tab) {
  router.replace({ name: 'utilisateur-detail', params: { id: userId.value }, query: { tab: next } })
  error.value = ''; success.value = ''
}

async function saveProfile() {
  if (!user.value) return
  saving.value = true; error.value = ''; success.value = ''
  try {
    user.value = await api.patchUser(userId.value, { email: profile.value.email.trim() })
    profile.value.email = user.value.email
    success.value = 'Profil enregistré.'
  } catch (e: any) { error.value = e?.message || 'Enregistrement impossible.' }
  finally { saving.value = false }
}

async function saveAccess() {
  if (!user.value) return
  saving.value = true; error.value = ''; success.value = ''
  try {
    user.value = await api.patchUser(userId.value, access.value)
    access.value = { role: user.value.role, is_active: user.value.is_active }
    success.value = 'Accès général enregistré.'
  } catch (e: any) { error.value = e?.message || 'Modification impossible.' }
  finally { saving.value = false }
}

async function savePassword() {
  if (password.value.length < 8) return
  saving.value = true; error.value = ''; success.value = ''
  try {
    await api.patchUser(userId.value, { new_password: password.value })
    password.value = ''; success.value = 'Mot de passe réinitialisé.'
  } catch (e: any) { error.value = e?.message || 'Réinitialisation impossible.' }
  finally { saving.value = false }
}

async function saveProjects() {
  saving.value = true; error.value = ''; success.value = ''
  try {
    projects.value = await api.putUserProjects(userId.value,
      projects.value.filter(p => p.has_access).map(p => ({ project_id: p.project_id, role: p.role })))
    success.value = 'Projets enregistrés.'
  } catch (e: any) { error.value = e?.message || 'Enregistrement des projets impossible.' }
  finally { saving.value = false }
}

const tabLabels: Record<Tab, string> = {
  user: 'UTILISATEUR', access: 'ACCÈS', auth: 'AUTHENTIFICATION', projects: 'PROJETS',
}
</script>

<template>
  <div class="px-4 py-6 sm:px-6 md:px-8">
    <button class="mb-4 min-h-11 text-sm text-primary hover:underline" @click="router.push('/utilisateurs')">← Utilisateurs et rôles</button>

    <div v-if="loading" class="py-10 text-sm text-muted-foreground">Chargement de l’utilisateur…</div>
    <div v-else-if="!user" class="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{{ error }}</div>
    <template v-else>
      <header class="flex flex-wrap items-center gap-3">
        <div class="grid h-11 w-11 place-items-center rounded-full bg-primary text-lg font-semibold text-primary-foreground">{{ user.username.charAt(0).toUpperCase() }}</div>
        <div><div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Modifier l’utilisateur</div><h1 class="text-2xl font-semibold tracking-tight">{{ user.username }}</h1></div>
        <span class="ml-auto rounded-full px-2.5 py-1 text-xs font-medium" :class="user.is_active ? 'bg-success/10 text-success' : 'bg-secondary text-muted-foreground'">{{ user.is_active ? 'Actif' : 'Inactif' }}</span>
      </header>

      <nav class="mt-6 flex gap-5 overflow-x-auto border-b border-border" aria-label="Paramètres utilisateur">
        <button v-for="item in tabs" :key="item" class="min-h-11 shrink-0 border-b-2 px-1 text-sm font-semibold" :class="tab === item ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'" @click="goTab(item)">{{ tabLabels[item] }}</button>
      </nav>

      <p v-if="error" role="alert" class="mt-5 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">{{ error }}</p>
      <p v-if="success" role="status" class="mt-5 rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">{{ success }}</p>

      <section v-if="tab === 'user'" class="mt-5 max-w-3xl rounded-lg border border-border bg-surface p-5">
        <h2 class="text-lg font-semibold">Informations personnelles</h2>
        <div class="mt-5 grid gap-5 sm:grid-cols-2">
          <label class="text-sm font-medium">Identifiant<input :value="user.username" disabled class="mt-1.5 h-11 w-full rounded-md border border-border bg-secondary px-3 text-muted-foreground" /><span class="mt-1 block text-xs font-normal text-muted-foreground">Utilisé pour la connexion et conservé dans l’historique.</span></label>
          <label class="text-sm font-medium">Adresse email<input v-model="profile.email" type="email" class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" /></label>
        </div>
        <Button class="mt-6" variant="primary" :loading="saving" @click="saveProfile">Enregistrer l’utilisateur</Button>
      </section>

      <section v-else-if="tab === 'access'" class="mt-5 max-w-3xl rounded-lg border border-border bg-surface p-5">
        <h2 class="text-lg font-semibold">Accès général</h2><p class="mt-1 text-sm text-muted-foreground">Le rôle d’instance ne remplace pas les droits attribués projet par projet.</p>
        <div class="mt-5 grid gap-5 sm:grid-cols-2">
          <label class="text-sm font-medium">Rôle dans l’instance<select v-model="access.role" class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3"><option v-for="role in ROLES" :key="role" :value="role">{{ LIBELLE_ROLE[role] }}</option></select></label>
          <label class="flex min-h-11 items-center gap-3 self-end rounded-md border border-border px-3 py-2 text-sm"><input v-model="access.is_active" type="checkbox" class="h-4 w-4" /><span><strong>Compte actif</strong><span class="block text-xs text-muted-foreground">Désactiver bloque la connexion sans supprimer l’historique.</span></span></label>
        </div>
        <Button class="mt-6" variant="primary" :loading="saving" @click="saveAccess">Enregistrer l’accès</Button>
      </section>

      <section v-else-if="tab === 'auth'" class="mt-5 max-w-3xl rounded-lg border border-border bg-surface p-5">
        <h2 class="text-lg font-semibold">Authentification</h2><p class="mt-1 text-sm text-muted-foreground">Le mot de passe actuel ne peut jamais être affiché. Définissez-en un nouveau si nécessaire.</p>
        <label class="mt-5 block max-w-md text-sm font-medium">Nouveau mot de passe<input v-model="password" type="password" autocomplete="new-password" class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3" /><span class="mt-1 block text-xs font-normal text-muted-foreground">8 caractères minimum.</span></label>
        <Button class="mt-6" variant="primary" :loading="saving" :disabled="password.length < 8" @click="savePassword">Réinitialiser le mot de passe</Button>
      </section>

      <section v-else class="mt-5 rounded-lg border border-border bg-surface p-5">
        <h2 class="text-lg font-semibold">Accès aux projets</h2><p class="mt-1 text-sm text-muted-foreground">Un projet non coché est entièrement masqué pour cet utilisateur.</p>
        <div class="mt-5 overflow-x-auto rounded-md border border-border"><table class="w-full min-w-[620px] text-sm"><thead class="bg-surface-raised text-left text-xs uppercase tracking-wide text-muted-foreground"><tr><th class="px-4 py-3">Accès</th><th class="px-4 py-3">Projet</th><th class="px-4 py-3">Rôle dans ce projet</th></tr></thead><tbody><tr v-for="project in projects" :key="project.project_id" class="border-t border-border"><td class="px-4 py-3"><input v-model="project.has_access" type="checkbox" class="h-4 w-4" :aria-label="`Autoriser ${project.project_name}`" /></td><td class="px-4 py-3 font-medium">{{ project.project_name }}</td><td class="px-4 py-3"><select v-model="project.role" :disabled="!project.has_access" :aria-label="`Rôle dans ${project.project_name}`" class="h-10 w-full max-w-xs rounded-md border border-border bg-surface px-2 disabled:opacity-50"><option v-for="role in ROLES" :key="role" :value="role">{{ LIBELLE_ROLE[role] }}</option></select></td></tr></tbody></table><p v-if="!projects.length" class="p-5 text-sm text-muted-foreground">Aucun projet disponible.</p></div>
        <Button class="mt-6" variant="primary" :loading="saving" @click="saveProjects">Enregistrer les projets</Button>
      </section>
    </template>
  </div>
</template>
