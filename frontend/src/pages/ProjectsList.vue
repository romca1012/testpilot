<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, type ProjectSummary } from '../lib/api'
import { useProjects } from '../lib/useProjects'
import Card from '../components/ui/Card.vue'
import Button from '../components/ui/Button.vue'
import Icon from '../components/ui/Icon.vue'

const router = useRouter()
const { ensureLoaded } = useProjects()
const projects = ref<ProjectSummary[]>([])
const loading = ref(true)
const error = ref('')

const creating = ref(false)
const newName = ref('')
const createError = ref('')

function open(p: ProjectSummary) {
  router.push(`/projects/${p.id}/cases`)
}

async function load(autoselect = false) {
  try {
    projects.value = await api.listProjects()
    // Auto-sélection si un seul projet : on entre directement dans son contexte.
    if (autoselect && projects.value.length === 1) {
      router.replace(`/projects/${projects.value[0].id}/cases`)
    }
  } catch (e: any) {
    error.value = e?.message || 'Chargement impossible'
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!newName.value.trim()) return
  creating.value = true
  createError.value = ''
  try {
    const p = await api.createProject(newName.value.trim())
    newName.value = ''
    await ensureLoaded(true)
    router.push(`/projects/${p.id}/cases`)
  } catch (e: any) {
    createError.value = e?.message || 'Création impossible'
  } finally {
    creating.value = false
  }
}

onMounted(() => load(true))
</script>

<template>
  <div class="space-y-8">
    <header class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">Projets</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Choisissez un projet pour accéder à ses cas de tests et à ses exécutions.
        </p>
      </div>
    </header>

    <!-- Création -->
    <Card title="Nouveau projet">
      <form class="flex flex-wrap items-center gap-3" @submit.prevent="create">
        <input
          v-model="newName" placeholder="Nom du projet (ex. Odoo)"
          class="h-9 flex-1 min-w-[12rem] rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50"
        />
        <Button type="submit" variant="primary" :loading="creating" :disabled="!newName.trim()">Créer</Button>
      </form>
      <p v-if="createError" class="mt-2 text-xs text-destructive">{{ createError }}</p>
    </Card>

    <!-- Liste -->
    <div v-if="loading" class="text-sm text-muted-foreground">Chargement…</div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>
    <div v-else-if="!projects.length" class="rounded-xl border border-border bg-card px-5 py-12 text-center">
      <p class="text-sm text-muted-foreground">Aucun projet. Créez-en un pour commencer.</p>
    </div>

    <div v-else class="grid gap-3 sm:grid-cols-2">
      <button
        v-for="p in projects" :key="p.id"
        class="group flex items-center justify-between rounded-xl border border-border bg-card p-5 text-left transition-colors hover:border-primary/40 hover:bg-accent/30"
        @click="open(p)"
      >
        <div class="min-w-0">
          <div class="font-medium truncate">{{ p.name }}</div>
          <div class="mt-1 text-xs text-muted-foreground">
            {{ p.module_count }} module{{ p.module_count > 1 ? 's' : '' }} · {{ p.case_count }} cas
          </div>
        </div>
        <Icon name="chevron" class="h-4 w-4 text-muted-foreground/40 transition-transform group-hover:translate-x-0.5 group-hover:text-muted-foreground" />
      </button>
    </div>
  </div>
</template>
