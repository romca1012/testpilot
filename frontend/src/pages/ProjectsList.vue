<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type ProjectSummary } from '../lib/api'
import { useProjects } from '../lib/useProjects'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Icon from '../components/ui/Icon.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const router = useRouter()
const { ensureLoaded } = useProjects()
const projects = ref<ProjectSummary[]>([])
const loading = ref(true)
const error = ref('')

const creating = ref(false)
const createError = ref('')
// Un projet = une application testée, avec son connecteur + sa connexion.
const form = ref({
  name: '', connector_type: 'odoo', base_url: '', database: '', username: '', password: '',
})
const CONNECTORS = [{ value: 'odoo', label: 'Odoo' }]  // extensible (§8 multi-connecteurs)

// Suppression
const toDelete = ref<ProjectSummary | null>(null)
const deleting = ref(false)

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
    form.value = { name: '', connector_type: 'odoo', base_url: '', database: '', username: '', password: '' }
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

onMounted(load)
</script>

<template>
  <div class="space-y-8">
    <header>
      <h1 class="text-2xl font-semibold tracking-tight">Projets</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Un projet regroupe les cas de tests et exécutions d'une application testée.
      </p>
    </header>

    <Card title="Nouveau projet">
      <form class="space-y-4" @submit.prevent="create">
        <div class="grid gap-3 sm:grid-cols-2">
          <label class="block">
            <span class="text-xs text-muted-foreground">Nom de l'application</span>
            <input v-model="form.name" placeholder="ex. Portail Sapian"
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
        </fieldset>

        <div class="flex items-center justify-end">
          <Button type="submit" variant="primary" :loading="creating" :disabled="!form.name.trim()">Créer le projet</Button>
        </div>
      </form>
      <p v-if="createError" class="mt-2 text-xs text-destructive">{{ createError }}</p>
    </Card>

    <div v-if="loading" class="text-sm text-muted-foreground">Chargement…</div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>
    <div v-else-if="!projects.length" class="rounded-xl border border-border bg-card px-5 py-12 text-center">
      <p class="text-sm text-muted-foreground">Aucun projet. Créez-en un pour commencer.</p>
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
        <button
          class="absolute right-3 top-3 rounded-md p-1.5 text-muted-foreground/50 opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
          title="Supprimer le projet"
          @click.stop="toDelete = p"
        >
          <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 7h12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-7 0v11a2 2 0 002 2h4a2 2 0 002-2V7" />
          </svg>
        </button>
      </div>
    </div>

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
