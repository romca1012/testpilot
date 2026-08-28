<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ACCES_PROJET_REFUSE, api, LIBELLE_ROLE, ROLES,
  type Exploration, type ProjectGroupAccess, type ProjectMember, type ProjectSummary,
  type UserAccount, type UserGroup,
} from '../lib/api'
import { useProjects } from '../lib/useProjects'
import { useSession } from '../lib/useSession'
import Button from '../components/ui/Button.vue'
import Icon from '../components/ui/Icon.vue'
import Modal from '../components/ui/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const router = useRouter()
const route = useRoute()
const adminMode = computed(() => route.name === 'admin-projects')
const { session } = useSession()
const { ensureLoaded } = useProjects()
const projects = ref<ProjectSummary[]>([])
const loading = ref(true)
const error = ref('')

// Création : une modale déclenchée par un bouton (façon TestRail « Add Project »), au lieu d'un
// formulaire toujours déplié qui poussait la liste des projets vers le bas.
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')

function openCreate() {
  form.value = { name: '', connector_type: 'odoo', base_url: '', database: '', username: '', password: '' }
  createError.value = ''
  showCreate.value = true
}
// Un projet = une application testée, avec son connecteur + sa connexion.
const form = ref({
  name: '', connector_type: 'odoo', base_url: '', database: '', username: '', password: '',
})
const CONNECTORS = [{ value: 'odoo', label: 'Odoo' }]  // extensible (§8 multi-connecteurs)

// Suppression
const toDelete = ref<ProjectSummary | null>(null)
const deleting = ref(false)

// ── Membres du projet (Admin) — appartenance et rôle explicites V1 ────────────
const accessProject = ref<ProjectSummary | null>(null)
const accessMembers = ref<ProjectMember[]>([])
const accessLoading = ref(false)
const accessSaving = ref(false)
const memberSaving = ref<number | null>(null)
const memberApiDisponible = ref(true)
const accessError = ref('')
const comptes = ref<UserAccount[]>([])
const nouveauMembreCompte = ref<number | null>(null)
const nouveauMembreRole = ref('testeur')
const groupes = ref<UserGroup[]>([])
const accessGroups = ref<ProjectGroupAccess[]>([])
const nouveauGroupe = ref<number | null>(null)
const nouveauGroupeRole = ref('')
const groupSaving = ref<number | 'new' | null>(null)
const accessTab = ref<'members' | 'groups'>('members')

async function openAccess(p: ProjectSummary) {
  accessProject.value = p
  accessTab.value = 'members'
  accessError.value = ''
  accessLoading.value = true
  try {
    const [users, userGroups, projectAccess] = await Promise.all([
      api.listUsers(), api.listUserGroups(), api.getProjectAccess(p.id),
    ])
    comptes.value = users
    groupes.value = userGroups
    accessGroups.value = projectAccess.group_overrides || []
    try {
      accessMembers.value = await api.listProjectMembers(p.id)
      memberApiDisponible.value = true
    } catch (e: any) {
      if (e?.status !== 404) throw e
      // Compatibilité immédiate avec une API encore démarrée sur le contrat précédent.
      const ancien = await api.getProjectAccess(p.id)
      const overrides = new Map(ancien.overrides.map((o) => [o.user_id, o.role]))
      accessMembers.value = comptes.value.map((c) => {
        const role = overrides.get(c.id) || ancien.default_access || c.role
        return {
          user_id: c.id, username: c.username, email: c.email,
          role: role === ACCES_PROJET_REFUSE ? c.role : role,
          status: role === ACCES_PROJET_REFUSE ? 'removed' : (c.is_active ? 'active' : 'suspended'),
          created_at: c.created_at,
        }
      })
      memberApiDisponible.value = false
    }
  } catch (e: any) {
    accessError.value = e?.message || 'Chargement des accès impossible.'
  } finally {
    accessLoading.value = false
  }
}

async function ajouterMembre() {
  if (!accessProject.value || nouveauMembreCompte.value == null) return
  accessSaving.value = true
  accessError.value = ''
  try {
    const compte = comptes.value.find((c) => c.id === nouveauMembreCompte.value)!
    const membre = memberApiDisponible.value
      ? await api.addProjectMember(accessProject.value.id, nouveauMembreCompte.value, nouveauMembreRole.value)
      : await api.setProjectAccessOverride(accessProject.value.id, nouveauMembreCompte.value,
          nouveauMembreRole.value).then(() => ({
            user_id: compte.id, username: compte.username, email: compte.email,
            role: nouveauMembreRole.value, status: 'active' as const, created_at: compte.created_at,
          }))
    const index = accessMembers.value.findIndex((m) => m.user_id === membre.user_id)
    if (index >= 0) accessMembers.value[index] = membre
    else accessMembers.value.push(membre)
    nouveauMembreCompte.value = null
    nouveauMembreRole.value = 'testeur'
  } catch (e: any) {
    accessError.value = e?.message || 'Ajout impossible.'
  } finally {
    accessSaving.value = false
  }
}

const groupesAjoutables = computed(() => {
  const deja = new Set(accessGroups.value.map(g => g.group_id))
  return groupes.value.filter(g => !deja.has(g.id))
})

async function enregistrerAccesGroupe(groupId: number, role: string, nouveau = false) {
  if (!accessProject.value) return
  groupSaving.value = nouveau ? 'new' : groupId
  accessError.value = ''
  try {
    const result = await api.setProjectGroupAccess(accessProject.value.id, groupId, role)
    accessGroups.value = result.group_overrides || []
    if (nouveau) { nouveauGroupe.value = null; nouveauGroupeRole.value = '' }
  } catch (e: any) { accessError.value = e?.message || 'Attribution du groupe impossible.' }
  finally { groupSaving.value = null }
}

async function retirerAccesGroupe(groupId: number) {
  if (!accessProject.value) return
  groupSaving.value = groupId
  accessError.value = ''
  try {
    const result = await api.removeProjectGroupAccess(accessProject.value.id, groupId)
    accessGroups.value = result.group_overrides || []
  } catch (e: any) { accessError.value = e?.message || 'Retrait du groupe impossible.' }
  finally { groupSaving.value = null }
}

async function modifierMembre(userId: number, patch: { role?: string; status?: 'active' | 'suspended' }) {
  if (!accessProject.value) return
  memberSaving.value = userId
  accessError.value = ''
  try {
    const index = accessMembers.value.findIndex((m) => m.user_id === userId)
    const actuel = accessMembers.value[index]
    const role = patch.role || actuel.role
    const status = patch.status || actuel.status
    const membre = memberApiDisponible.value
      ? await api.patchProjectMember(accessProject.value.id, userId, patch)
      : await api.setProjectAccessOverride(accessProject.value.id, userId,
          status === 'active' ? role : ACCES_PROJET_REFUSE).then(() => ({ ...actuel, role, status }))
    if (index >= 0) accessMembers.value[index] = membre
  } catch (e: any) {
    accessError.value = e?.message || 'Modification impossible.'
  } finally {
    memberSaving.value = null
  }
}

async function retirerMembre(userId: number) {
  if (!accessProject.value) return
  memberSaving.value = userId
  accessError.value = ''
  try {
    const index = accessMembers.value.findIndex((m) => m.user_id === userId)
    const membre = memberApiDisponible.value
      ? await api.removeProjectMember(accessProject.value.id, userId)
      : await api.setProjectAccessOverride(accessProject.value.id, userId,
          ACCES_PROJET_REFUSE).then(() => ({ ...accessMembers.value[index], status: 'removed' as const }))
    if (index >= 0) accessMembers.value[index] = membre
  } catch (e: any) {
    accessError.value = e?.message || 'Retrait impossible.'
  } finally {
    memberSaving.value = null
  }
}

function comptesAjoutables() {
  const presents = new Set(accessMembers.value.filter((m) => m.status !== 'removed').map((m) => m.user_id))
  return comptes.value.filter((c) => c.is_active && !presents.has(c.id))
}

function membresVisibles() {
  return accessMembers.value.filter((m) => m.status !== 'removed')
}

// ── Édition d'un projet et de SA CONNEXION (décision 0005) ────────────────────
// Manquait entièrement : on pouvait créer un projet et le supprimer, pas le corriger. Une faute
// de frappe dans l'URL obligeait à tout recréer — donc à perdre modules, cas et historique.
// C'est aussi le préalable à l'exploration : on ne cartographie pas une application dont on ne
// peut pas rectifier l'adresse.
const editing = ref<ProjectSummary | null>(null)
const saving = ref(false)
const editError = ref('')
const edit = ref({
  name: '', connector_type: 'odoo', base_url: '', database: '', username: '', password: '',
})

function startEdit(p: ProjectSummary) {
  editing.value = p
  editError.value = ''
  edit.value = {
    name: p.name, connector_type: p.connector_type || 'odoo', base_url: p.base_url || '',
    database: p.database || '', username: p.username || '',
    // ⚠️ TOUJOURS vide : l'API ne renvoie jamais le mot de passe (write-only). Le champ vide
    // signifie « inchangé », jamais « efface-le » — d'où le filtrage à l'enregistrement.
    password: '',
  }
}

// ── Exploration : cartographier l'application du projet ──────────────────────
// Étape 2 du flux produit : projet → connecteur → EXPLORATION → génération. Payée une fois par
// projet ; ensuite la génération lit cette mesure au lieu de deviner routes et champs.
const explorations = ref<Record<number, Exploration>>({})
const exploring = ref<number | null>(null)
let pollTimer: number | undefined

async function loadExplorations() {
  for (const p of projects.value) {
    try {
      explorations.value[p.id] = await api.getExploration(p.id)
    } catch { /* best-effort : l'état de la carto ne doit jamais casser la liste des projets */ }
  }
}

async function explore(p: ProjectSummary) {
  exploring.value = p.id
  error.value = ''
  try {
    const e = await api.startExploration(p.id)
    explorations.value[p.id] = e
    pollExploration(p.id)
  } catch (e: any) {
    exploring.value = null
    error.value = e?.message || 'Exploration impossible'
  }
}

function pollExploration(id: number) {
  pollTimer = window.setInterval(async () => {
    try {
      const e = await api.getExploration(id)
      explorations.value[id] = e
      if (e.running) return
      window.clearInterval(pollTimer)
      exploring.value = null
      // L'échec est REMONTÉ, jamais avalé : une carto absente rend la génération aveugle.
      if (e.error) error.value = e.error
    } catch {
      window.clearInterval(pollTimer)
      exploring.value = null
    }
  }, 3000)
}

onUnmounted(() => { if (pollTimer) window.clearInterval(pollTimer) })

async function saveEdit() {
  if (!editing.value || !edit.value.name.trim()) return
  saving.value = true
  editError.value = ''
  try {
    const patch: Record<string, string> = {
      name: edit.value.name.trim(),
      connector_type: edit.value.connector_type,
      base_url: edit.value.base_url,
      database: edit.value.database,
      username: edit.value.username,
    }
    // Le mot de passe n'est envoyé QUE s'il a été saisi. L'omettre laisse le secret intact ;
    // envoyer "" l'effacerait — et toutes les exécutions du projet échoueraient ensuite.
    if (edit.value.password) patch.password = edit.value.password
    await api.updateProject(editing.value.id, patch)
    editing.value = null
    await ensureLoaded(true)
    await load()
  } catch (e: any) {
    editError.value = e?.message || 'Enregistrement impossible'
  } finally {
    saving.value = false
  }
}

function open(p: ProjectSummary) {
  router.push(`/projects/${p.id}/cases`)
}

async function load() {
  loading.value = true
  try {
    projects.value = await (adminMode.value ? api.listAdminProjects() : api.listProjects())
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!form.value.name.trim()) return
  creating.value = true
  createError.value = ''
  try {
    const p = await api.createProject({ ...form.value, name: form.value.name.trim() })
    showCreate.value = false
    await ensureLoaded(true)
    router.push(`/projects/${p.id}/cases`)
  } catch (e: any) {
    createError.value = e?.message || 'Création impossible'
  } finally {
    creating.value = false
  }
}

const deleteMessage = () => {
  const p = toDelete.value
  if (!p) return ''
  const parts = [`« ${p.name} » sera supprimé définitivement.`]
  if (p.module_count || p.case_count) {
    parts.push(`Cela supprimera aussi ${p.module_count} module(s) et ${p.case_count} cas de test, avec leurs versions et exécutions.`)
  }
  parts.push('Cette action est irréversible.')
  return parts.join('\n')
}

async function confirmDelete() {
  if (!toDelete.value) return
  deleting.value = true
  try {
    await api.deleteProject(toDelete.value.id)
    toDelete.value = null
    await ensureLoaded(true)
    await load()
  } catch (e: any) {
    error.value = e?.message || 'Suppression impossible'
  } finally {
    deleting.value = false
  }
}

onMounted(async () => { await load(); await loadExplorations() })
</script>

<template>
  <div class="space-y-6 p-6 md:p-8">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Projets</h1>
        <p class="mt-1 text-sm text-muted-foreground">{{ adminMode
          ? 'Configurez les projets, leurs applications et leurs accès.'
          : 'Choisissez le projet sur lequel vous souhaitez travailler.' }}</p>
      </div>
      <Button v-if="adminMode" variant="primary" @click="openCreate">
        <Icon name="plus" class="h-4 w-4" /> Nouveau projet
      </Button>
    </header>

    <div v-if="loading" class="text-sm text-muted-foreground">Chargement…</div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>
    <div v-else-if="!projects.length"
         class="flex flex-col items-center gap-3 rounded-xl border border-border bg-card px-5 py-16 text-center">
      <div class="grid h-12 w-12 place-items-center rounded-full border border-border bg-surface text-muted-foreground">
        <Icon name="folder" class="h-5 w-5" />
      </div>
      <p class="text-sm text-muted-foreground">{{ adminMode ? 'Aucun projet pour le moment.' : 'Aucun projet ne vous est actuellement attribué.' }}</p>
      <p v-if="!adminMode" class="max-w-md text-xs leading-5 text-subtle-foreground">Contactez un administrateur TestPilot pour demander l’accès à un projet.</p>
      <Button v-if="adminMode" variant="primary" @click="openCreate">
        <Icon name="plus" class="h-4 w-4" /> Créer le premier projet
      </Button>
    </div>

    <div v-else class="overflow-hidden rounded-lg border border-border bg-surface">
      <div class="border-b border-border bg-surface-raised px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Projet</div>
      <div
        v-for="p in projects" :key="p.id"
        class="group relative border-b border-border bg-surface p-4 transition-colors last:border-b-0 hover:bg-accent/20"
      >
        <button class="flex w-full items-center justify-between text-left" @click="open(p)">
          <div class="min-w-0">
            <div class="font-medium truncate pr-8 text-primary">{{ p.name }}</div>
            <div class="mt-1 text-xs text-muted-foreground">
              {{ p.module_count }} module{{ p.module_count > 1 ? 's' : '' }} · {{ p.case_count }} cas
            </div>
          </div>
          <span v-if="!adminMode" class="inline-flex min-h-9 shrink-0 items-center rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground">Ouvrir</span>
          <Icon v-else name="chevron" class="h-4 w-4 shrink-0 text-muted-foreground/40 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
        </button>
        <!-- Connexion en clair sur la carte : c'est ce qui distingue deux projets du même
             connecteur, et ce qu'on vient vérifier quand une exécution tape la mauvaise instance. -->
        <div v-if="adminMode && p.base_url" class="mt-2 truncate text-xs text-subtle-foreground" :title="p.base_url">
          {{ p.connector_type }} · {{ p.base_url }}<span v-if="p.database"> · {{ p.database }}</span>
        </div>
        <div v-else-if="adminMode" class="mt-2 text-xs text-warning">Aucune connexion configurée</div>

        <!-- ══ Cartographie de l'application (étape 2 du flux) ══
             La DATE est toujours affichée : c'est une photo, et elle vieillit. Un projet non
             exploré le dit clairement plutôt que de laisser croire que la génération sait où
             elle va. -->
        <div v-if="adminMode" class="mt-3 border-t border-border/60 pt-2.5 md:ml-6">
          <div class="text-[11px] font-medium uppercase tracking-wide text-subtle-foreground">Exploration</div>
          <div class="mt-1 flex items-center gap-2">
          <div class="min-w-0 flex-1 text-xs">
            <template v-if="explorations[p.id]?.running || exploring === p.id">
              <span class="text-primary">Exploration en cours… (quelques minutes)</span>
            </template>
            <template v-else-if="explorations[p.id]?.explored">
              <span class="text-muted-foreground">
                {{ explorations[p.id].pages }} routes · {{ explorations[p.id].transitions }} transitions
                · {{ explorations[p.id].champs }} champs
              </span>
              <!-- Les RÈGLES DE VALIDATION lues dans les formulaires (« 7 chiffres exactement »,
                   « 25 caractères max »…). Affichées parce qu'elles sont ce qui empêche l'IA
                   d'écrire une valeur que le formulaire refuse — auquel cas le test accuserait
                   l'application à tort. Zéro règle sur un portail qui en a = mesure à refaire. -->
              <span v-if="explorations[p.id].contraintes" class="text-muted-foreground">
                · {{ explorations[p.id].contraintes }} règles de saisie
              </span>
              <span class="text-subtle-foreground"> — mesuré le {{ explorations[p.id].mesure_le }}</span>
            </template>
            <template v-else>
              <span class="text-subtle-foreground">Application non explorée</span>
            </template>
          </div>
          <Button
            variant="secondary" size="sm"
            :disabled="!p.base_url || explorations[p.id]?.running || exploring === p.id"
            :title="!p.base_url ? 'Renseignez d\'abord la connexion du projet'
                    : explorations[p.id]?.explored ? 'Re-mesurer l\'application' : 'Cartographier l\'application'"
            @click.stop="explore(p)"
          >
            {{ explorations[p.id]?.explored ? 'Actualiser' : 'Explorer' }}
          </Button>
          </div>
        </div>

        <div v-if="adminMode" class="mt-3 border-t border-border/60 pt-2.5 md:ml-6">
          <div class="text-[11px] font-medium uppercase tracking-wide text-subtle-foreground">Paramètres du projet</div>
          <div class="mt-1.5 flex flex-wrap gap-1.5">
            <Button
              variant="secondary"
              size="sm"
              :title="`Modifier l'identité et l'application de ${p.name}`"
              @click.stop="startEdit(p)"
            >
              Identité et application
            </Button>
            <Button v-if="session?.role === 'admin'" variant="secondary" size="sm" @click.stop="openAccess(p)">
              Accès
            </Button>
            <Button variant="ghost" size="sm" class="text-destructive" @click.stop="toDelete = p">
              Supprimer
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- ════════ Création d'un projet (façon TestRail « Add Project », + notre CONNEXION) ════════ -->
    <Modal :open="showCreate" title="Nouveau projet"
           subtitle="Un projet = une application testée, avec le connecteur et la connexion que l'exploration et les exécutions utiliseront."
           @close="showCreate = false">
      <form id="form-create-project" class="space-y-4" @submit.prevent="create">
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block">
            <span class="text-xs text-muted-foreground">Nom de l'application <span class="text-destructive">*</span></span>
            <input v-model="form.name" placeholder="ex. Portail Sapian" autofocus
                   class="mt-1 h-9 w-full rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />
          </label>
          <label class="block">
            <span class="text-xs text-muted-foreground">Connecteur</span>
            <select v-model="form.connector_type"
                    class="mt-1 h-9 w-full rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50">
              <option v-for="c in CONNECTORS" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </label>
        </div>

        <fieldset class="rounded-lg border border-border p-3">
          <legend class="px-1 text-xs uppercase tracking-wide text-muted-foreground">Connexion</legend>
          <div class="grid gap-3 sm:grid-cols-2">
            <input v-model="form.base_url" placeholder="URL (ex. http://localhost:10017)"
                   class="h-9 rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />
            <input v-model="form.database" placeholder="Base de données"
                   class="h-9 rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />
            <input v-model="form.username" placeholder="Utilisateur"
                   class="h-9 rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />
            <input v-model="form.password" type="password" placeholder="Mot de passe"
                   class="h-9 rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />
          </div>
          <p class="mt-2 text-xs text-muted-foreground">
            Facultatif ici — vous pourrez la renseigner et la corriger ensuite. Sans elle, aucune
            exploration ni exécution n'est possible.
          </p>
        </fieldset>

        <p v-if="createError" class="text-xs text-destructive">{{ createError }}</p>
      </form>

      <template #footer>
        <Button type="button" variant="secondary" @click="showCreate = false">Annuler</Button>
        <Button type="submit" form="form-create-project" variant="primary" :loading="creating" :disabled="!form.name.trim()">Créer le projet</Button>
      </template>
    </Modal>

    <!-- ════════ Édition d'un projet et de sa connexion ════════ -->
    <Modal :open="!!editing" :title="editing ? `Paramètres du projet — ${editing.name}` : ''"
           subtitle="La connexion désigne l'application réellement testée : c'est elle que les exécutions et l'exploration utiliseront."
           @close="editing = null">
      <form id="form-edit-project" class="space-y-3" @submit.prevent="saveEdit">
        <fieldset class="rounded-lg border border-border p-3">
          <legend class="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Identité</legend>
          <label class="block">
            <span class="text-sm font-medium">Nom <span class="text-destructive">*</span></span>
            <input v-model="edit.name" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          </label>
        </fieldset>
        <fieldset class="rounded-lg border border-border p-3">
          <legend class="px-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Application cible</legend>
          <label class="block">
            <span class="text-sm font-medium">Connecteur</span>
            <select v-model="edit.connector_type" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2">
              <option v-for="c in CONNECTORS" :key="c.value" :value="c.value">{{ c.label }}</option>
            </select>
          </label>
          <div class="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label class="block"><span class="text-sm font-medium">URL</span><input v-model="edit.base_url" placeholder="http://localhost:10017" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" /></label>
            <label class="block"><span class="text-sm font-medium">Base de données</span><input v-model="edit.database" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" /></label>
            <label class="block"><span class="text-sm font-medium">Utilisateur</span><input v-model="edit.username" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" /></label>
            <label class="block"><span class="text-sm font-medium">Mot de passe</span><input v-model="edit.password" type="password" placeholder="Inchangé" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" /></label>
          </div>
          <p class="mt-2 text-xs text-muted-foreground">Le mot de passe n'est jamais réaffiché. Laissez ce champ vide pour le conserver tel quel.</p>
        </fieldset>
        <p v-if="editError" class="text-sm text-destructive">{{ editError }}</p>
      </form>

      <template #footer>
        <Button type="button" variant="secondary" @click="editing = null">Annuler</Button>
        <Button type="submit" form="form-edit-project" variant="primary" :loading="saving" :disabled="!edit.name.trim()">Enregistrer</Button>
      </template>
    </Modal>

    <!-- ════════ Membres et rôles du projet (Admin) ════════ -->
    <Modal :open="!!accessProject" :title="accessProject ? `Paramètres du projet — Accès à ${accessProject.name}` : ''"
           subtitle="Gérez séparément les accès individuels et ceux accordés aux groupes."
           max-width="max-w-4xl"
           @close="accessProject = null">
      <div class="space-y-5">
        <p v-if="accessError" role="alert" class="text-sm text-destructive">{{ accessError }}</p>
        <p v-if="accessLoading" class="text-sm text-muted-foreground">Chargement…</p>

        <template v-else>
          <nav class="flex gap-6 border-b border-border" aria-label="Types d’accès au projet">
            <button class="min-h-11 border-b-2 px-1 text-sm font-semibold" :class="accessTab === 'members' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'" @click="accessTab = 'members'">UTILISATEURS</button>
            <button class="min-h-11 border-b-2 px-1 text-sm font-semibold" :class="accessTab === 'groups' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'" @click="accessTab = 'groups'">GROUPES</button>
          </nav>

          <div v-if="accessTab === 'members'">
            <div class="flex items-start justify-between gap-4"><div><h3 class="text-sm font-semibold">Accès individuels</h3><p class="mt-1 text-xs text-muted-foreground">Une suspension retire l’accès sans supprimer le compte.</p></div><span class="shrink-0 rounded-full bg-secondary px-2.5 py-1 text-xs text-muted-foreground">{{ membresVisibles().length }} compte{{ membresVisibles().length > 1 ? 's' : '' }}</span></div>
            <div v-if="membresVisibles().length" class="mt-3 overflow-x-auto rounded-md border border-border">
            <table class="w-full min-w-[720px] table-fixed border-collapse text-sm">
              <thead class="text-left text-xs text-muted-foreground">
                <tr class="bg-surface-raised"><th class="w-[34%] px-3 py-2.5">Compte</th><th class="w-[23%] px-3">Rôle projet</th><th class="w-[14%] px-3">Statut</th><th class="w-[29%] px-3 text-right">Actions</th></tr>
              </thead>
              <tbody>
                <tr v-for="m in membresVisibles()" :key="m.user_id" class="border-t border-border">
                  <td class="px-3 py-2.5">
                    <span class="block truncate font-medium">{{ m.username }}</span>
                    <span v-if="m.email" class="block truncate text-xs text-muted-foreground" :title="m.email">{{ m.email }}</span>
                  </td>
                  <td class="px-3 py-2.5">
                    <label :for="`member-role-${m.user_id}`" class="sr-only">Rôle projet de {{ m.username }}</label>
                    <select :id="`member-role-${m.user_id}`" :value="m.role"
                            :disabled="memberSaving === m.user_id"
                            @change="modifierMembre(m.user_id, { role: ($event.target as HTMLSelectElement).value })"
                            class="h-10 w-full rounded-md bg-surface-raised border border-border px-2 focus:border-primary outline-none">
                      <option v-for="r in ROLES" :key="r" :value="r">{{ LIBELLE_ROLE[r] }}</option>
                    </select>
                  </td>
                  <td class="px-3 py-2.5">
                    <span :class="m.status === 'active' ? 'text-success' : 'text-muted-foreground'">
                      {{ m.status === 'active' ? 'Actif' : 'Suspendu' }}
                    </span>
                  </td>
                  <td class="px-3 py-2.5"><div class="flex justify-end gap-2 whitespace-nowrap">
                    <Button v-if="m.status === 'active'" variant="ghost" size="sm" :disabled="memberSaving === m.user_id" @click="modifierMembre(m.user_id, { status: 'suspended' })">Suspendre</Button>
                    <Button v-else variant="ghost" size="sm" :disabled="memberSaving === m.user_id" @click="modifierMembre(m.user_id, { status: 'active' })">Réactiver</Button>
                    <Button variant="danger" size="sm" :disabled="memberSaving === m.user_id" @click="retirerMembre(m.user_id)">Retirer</Button>
                  </div>
                  </td>
                </tr>
              </tbody>
            </table>
            </div>
            <p v-else class="mt-2 text-sm text-muted-foreground">Aucun membre actif sur ce projet.</p>

            <div class="mt-5 grid grid-cols-1 items-end gap-3 rounded-md border border-border bg-surface-raised p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
              <label class="text-sm">
                <span class="mb-1 block font-medium">Compte à ajouter</span>
                <select v-model="nouveauMembreCompte"
                      class="h-10 w-full min-w-0 rounded-md bg-surface border border-border px-2 text-sm focus:border-primary outline-none">
                  <option :value="null" disabled>Choisir un compte…</option>
                  <option v-for="c in comptesAjoutables()" :key="c.id" :value="c.id">{{ c.username }}</option>
                </select>
              </label>
              <label class="text-sm">
                <span class="mb-1 block font-medium">Rôle dans ce projet</span>
                <select v-model="nouveauMembreRole"
                      class="h-10 w-full min-w-0 rounded-md bg-surface border border-border px-2 text-sm focus:border-primary outline-none">
                  <option v-for="r in ROLES" :key="r" :value="r">{{ LIBELLE_ROLE[r] }}</option>
                </select>
              </label>
              <Button variant="secondary" :loading="accessSaving" :disabled="nouveauMembreCompte == null"
                      @click="ajouterMembre">
                Ajouter
              </Button>
            </div>
            <p v-if="!comptesAjoutables().length" class="mt-2 text-xs text-muted-foreground">
              Aucun autre compte actif n'est disponible.
              <RouterLink to="/utilisateurs" class="text-primary hover:underline" @click="accessProject = null">
                Créer ou réactiver un compte
              </RouterLink>
              avant de l'ajouter au projet.
            </p>
          </div>

          <div v-else>
            <h3 class="text-sm font-semibold">Accès des groupes</h3>
            <p class="mt-1 text-xs text-muted-foreground">Les groupes se cumulent ; un accès individuel reste prioritaire.</p>
            <div v-if="accessGroups.length" class="mt-3 divide-y divide-border rounded-md border border-border">
              <div v-for="g in accessGroups" :key="g.group_id" class="grid items-center gap-3 px-3 py-2 sm:grid-cols-[1fr_190px_auto]">
                <div><span class="font-medium">{{ g.group_name }}</span><span class="ml-2 text-xs text-muted-foreground">{{ g.member_count }} membre{{ g.member_count > 1 ? 's' : '' }}</span></div>
                <select :value="g.role" :disabled="groupSaving === g.group_id" :aria-label="`Rôle du groupe ${g.group_name}`" class="h-10 rounded-md border border-border bg-surface-raised px-2 text-sm" @change="enregistrerAccesGroupe(g.group_id, ($event.target as HTMLSelectElement).value)">
                  <option value="">Rôle global de chaque membre</option><option :value="ACCES_PROJET_REFUSE">Aucun accès accordé</option><option v-for="r in ROLES" :key="r" :value="r">{{ LIBELLE_ROLE[r] }}</option>
                </select>
                <Button variant="danger" size="sm" :loading="groupSaving === g.group_id" @click="retirerAccesGroupe(g.group_id)">Retirer</Button>
              </div>
            </div>
            <div class="mt-4 grid grid-cols-1 items-end gap-3 rounded-md border border-border bg-surface-raised p-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,220px)_auto]">
              <label class="text-sm"><span class="mb-1 block font-medium">Groupe à ajouter</span><select v-model="nouveauGroupe" class="h-10 w-full rounded-md border border-border bg-surface-raised px-2"><option :value="null" disabled>Choisir un groupe…</option><option v-for="g in groupesAjoutables" :key="g.id" :value="g.id">{{ g.name }}</option></select></label>
              <label class="text-sm"><span class="mb-1 block font-medium">Accès</span><select v-model="nouveauGroupeRole" class="h-10 w-full rounded-md border border-border bg-surface-raised px-2"><option value="">Rôle global</option><option :value="ACCES_PROJET_REFUSE">Aucun accès</option><option v-for="r in ROLES" :key="r" :value="r">{{ LIBELLE_ROLE[r] }}</option></select></label>
              <Button variant="secondary" :loading="groupSaving === 'new'" :disabled="nouveauGroupe == null" @click="enregistrerAccesGroupe(nouveauGroupe!, nouveauGroupeRole, true)">Ajouter</Button>
            </div>
            <p v-if="!groupes.length" class="mt-3 text-xs text-muted-foreground">Aucun groupe disponible. <RouterLink to="/utilisateurs?tab=groups" class="text-primary hover:underline" @click="accessProject = null">Créer un groupe</RouterLink>.</p>
          </div>
        </template>
      </div>

      <template #footer>
        <Button type="button" variant="secondary" @click="accessProject = null">Fermer</Button>
      </template>
    </Modal>

    <ConfirmDialog
      :open="!!toDelete"
      title="Supprimer ce projet ?"
      :message="deleteMessage()"
      confirm-label="Supprimer définitivement"
      :busy="deleting"
      @confirm="confirmDelete"
      @cancel="toDelete = null"
    />
  </div>
</template>
