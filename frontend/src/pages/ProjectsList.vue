<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type Exploration, type ProjectSummary } from '../lib/api'
import { useProjects } from '../lib/useProjects'
import Button from '../components/ui/Button.vue'
import Icon from '../components/ui/Icon.vue'
import Modal from '../components/ui/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const router = useRouter()
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
    projects.value = await api.listProjects()
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
  <div class="space-y-8">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Projets</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Un projet regroupe les cas de tests et exécutions d'une application testée.
        </p>
      </div>
      <Button variant="primary" @click="openCreate">
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
      <p class="text-sm text-muted-foreground">Aucun projet pour le moment.</p>
      <Button variant="primary" @click="openCreate">
        <Icon name="plus" class="h-4 w-4" /> Créer le premier projet
      </Button>
    </div>

    <div v-else class="grid gap-3 sm:grid-cols-2">
      <div
        v-for="p in projects" :key="p.id"
        class="group relative rounded-xl border border-border bg-card p-5 transition-colors hover:border-primary/40 hover:bg-accent/30"
      >
        <button class="flex w-full items-center justify-between text-left" @click="open(p)">
          <div class="min-w-0">
            <div class="font-medium truncate pr-8">{{ p.name }}</div>
            <div class="mt-1 text-xs text-muted-foreground">
              {{ p.module_count }} module{{ p.module_count > 1 ? 's' : '' }} · {{ p.case_count }} cas
            </div>
          </div>
          <Icon name="chevron" class="h-4 w-4 shrink-0 text-muted-foreground/40 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
        </button>
        <!-- Connexion en clair sur la carte : c'est ce qui distingue deux projets du même
             connecteur, et ce qu'on vient vérifier quand une exécution tape la mauvaise instance. -->
        <div v-if="p.base_url" class="mt-2 truncate text-[11px] text-muted-foreground/70" :title="p.base_url">
          {{ p.connector_type }} · {{ p.base_url }}<span v-if="p.database"> · {{ p.database }}</span>
        </div>
        <div v-else class="mt-2 text-[11px] text-warning">Aucune connexion configurée</div>

        <!-- ══ Cartographie de l'application (étape 2 du flux) ══
             La DATE est toujours affichée : c'est une photo, et elle vieillit. Un projet non
             exploré le dit clairement plutôt que de laisser croire que la génération sait où
             elle va. -->
        <div class="mt-3 flex items-center gap-2 border-t border-border/60 pt-2.5">
          <div class="min-w-0 flex-1 text-[11px]">
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
              <span class="text-muted-foreground/60"> — mesuré le {{ explorations[p.id].mesure_le }}</span>
            </template>
            <template v-else>
              <span class="text-muted-foreground/70">Application non explorée</span>
            </template>
          </div>
          <button
            class="shrink-0 rounded-md border border-border px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!p.base_url || explorations[p.id]?.running || exploring === p.id"
            :title="!p.base_url ? 'Renseignez d\'abord la connexion du projet'
                    : explorations[p.id]?.explored ? 'Re-mesurer l\'application' : 'Cartographier l\'application'"
            @click.stop="explore(p)"
          >
            {{ explorations[p.id]?.explored ? 'Ré-explorer' : 'Explorer' }}
          </button>
        </div>

        <button
          class="absolute right-10 top-3 rounded-md p-1.5 text-muted-foreground/50 opacity-0 transition-opacity hover:bg-accent hover:text-foreground group-hover:opacity-100"
          title="Modifier le projet et sa connexion"
          @click.stop="startEdit(p)"
         aria-label="Modifier le projet et sa connexion">
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M11 4H4v16h16v-7M18.5 2.5a2.1 2.1 0 013 3L12 15l-4 1 1-4z" />
          </svg>
        </button>
        <button
          class="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground/50 opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
          title="Supprimer le projet"
          @click.stop="toDelete = p"
         aria-label="Supprimer le projet">
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 7h12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-7 0v11a2 2 0 002 2h4a2 2 0 002-2V7" />
          </svg>
        </button>
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
          <legend class="px-1 text-[11px] uppercase tracking-wide text-muted-foreground">Connexion</legend>
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
          <p class="mt-2 text-[11px] text-muted-foreground">
            Facultatif ici — vous pourrez la renseigner et la corriger ensuite. Sans elle, aucune
            exploration ni exécution n'est possible.
          </p>
        </fieldset>

        <p v-if="createError" class="text-xs text-destructive">{{ createError }}</p>
      </form>

      <template #footer>
        <button type="button" class="rounded-md border border-border px-4 h-9 text-sm hover:border-primary/40" @click="showCreate = false">Annuler</button>
        <Button type="submit" form="form-create-project" variant="primary" :loading="creating" :disabled="!form.name.trim()">Créer le projet</Button>
      </template>
    </Modal>

    <!-- ════════ Édition d'un projet et de sa connexion ════════ -->
    <Modal :open="!!editing" :title="editing ? `Modifier « ${editing.name} »` : ''"
           subtitle="La connexion désigne l'application réellement testée : c'est elle que les exécutions et l'exploration utiliseront."
           @close="editing = null">
      <form id="form-edit-project" class="space-y-3" @submit.prevent="saveEdit">
        <label class="block">
          <span class="text-sm font-medium">Nom <span class="text-destructive">*</span></span>
          <input v-model="edit.name" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        </label>
        <label class="block">
          <span class="text-sm font-medium">Connecteur</span>
          <select v-model="edit.connector_type" class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2">
            <option v-for="c in CONNECTORS" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
        </label>
        <div class="grid grid-cols-2 gap-3">
          <label class="block">
            <span class="text-sm font-medium">URL</span>
            <input v-model="edit.base_url" placeholder="http://localhost:10017"
                   class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium">Base de données</span>
            <input v-model="edit.database"
                   class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium">Utilisateur</span>
            <input v-model="edit.username"
                   class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          </label>
          <label class="block">
            <span class="text-sm font-medium">Mot de passe</span>
            <input v-model="edit.password" type="password" placeholder="Inchangé"
                   class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          </label>
        </div>
        <p class="text-[11px] text-muted-foreground">
          Le mot de passe n'est jamais réaffiché. Laissez ce champ vide pour le conserver tel quel.
        </p>
        <p v-if="editError" class="text-sm text-destructive">{{ editError }}</p>
      </form>

      <template #footer>
        <button type="button" class="rounded-md border border-border px-4 h-9 text-sm hover:border-primary/40" @click="editing = null">Annuler</button>
        <Button type="submit" form="form-edit-project" variant="primary" :loading="saving" :disabled="!edit.name.trim()">Enregistrer</Button>
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
