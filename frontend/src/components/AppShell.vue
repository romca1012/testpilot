<script setup lang="ts">
// Coque applicative. Le PROJET est le contexte de premier niveau (sélecteur en haut de
// sidebar) ; SOUS lui, la séparation §8 reste structurelle : deux onglets Gestion / Exécution.
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjects } from '../lib/useProjects'
import Icon from './ui/Icon.vue'

const route = useRoute()
const router = useRouter()
const { projects, ensureLoaded, projectById } = useProjects()

const pid = computed(() => route.params.pid as string | undefined)
const currentProject = computed(() => projectById(pid.value))
const menuOpen = ref(false)

onMounted(() => ensureLoaded())
watch(pid, () => ensureLoaded())

const tabs = computed(() => [
  { to: `/projects/${pid.value}/cases`, label: 'Gestion des cas', match: 'cases',
    icon: 'M4 6a2 2 0 012-2h12a2 2 0 012 2v2H4V6zM4 10h16v8a2 2 0 01-2 2H6a2 2 0 01-2-2v-8z' },
  { to: `/projects/${pid.value}/executions`, label: 'Exécution', match: 'executions',
    icon: 'M14.752 11.168l-5.197-3.03A1 1 0 008 9.002v5.996a1 1 0 001.555.832l5.197-3.03a1 1 0 000-1.632z' },
])

function isTabActive(match: string) {
  return route.path.includes(`/${match}`)
}
function switchProject(id: number) {
  menuOpen.value = false
  // Reste sur le même onglet, change juste de projet.
  const tab = isTabActive('executions') ? 'executions' : 'cases'
  router.push(`/projects/${id}/${tab}`)
}
</script>

<template>
  <div class="app-bg min-h-screen flex flex-col md:flex-row">
    <aside class="shrink-0 md:w-64 border-b md:border-b-0 md:border-r border-border bg-surface/60 backdrop-blur-sm">
      <RouterLink to="/projects" class="h-14 flex items-center gap-2 px-4 border-b border-border">
        <div class="h-6 w-6 rounded-md bg-primary/15 grid place-items-center">
          <span class="h-2 w-2 rounded-full bg-primary" />
        </div>
        <span class="font-semibold tracking-tight">Test<span class="text-primary">Pilot</span></span>
      </RouterLink>

      <!-- Sélecteur de projet (contexte de premier niveau) -->
      <div v-if="pid" class="relative px-3 pt-3">
        <span class="px-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Projet</span>
        <button
          class="mt-1 flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface-raised px-3 py-2 text-sm hover:border-primary/40 transition-colors"
          @click="menuOpen = !menuOpen"
        >
          <span class="truncate font-medium">{{ currentProject?.name || '…' }}</span>
          <Icon name="chevron" class="h-3.5 w-3.5 rotate-90 text-muted-foreground shrink-0" />
        </button>
        <div v-if="menuOpen"
             class="absolute left-3 right-3 z-30 mt-1 rounded-md border border-border bg-surface-overlay py-1 shadow-xl">
          <button
            v-for="p in projects" :key="p.id"
            class="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent/60"
            :class="p.id === Number(pid) ? 'text-primary' : 'text-foreground'"
            @click="switchProject(p.id)"
          >
            <span class="truncate">{{ p.name }}</span>
            <Icon v-if="p.id === Number(pid)" name="check" class="h-3.5 w-3.5" />
          </button>
          <div class="my-1 border-t border-border" />
          <RouterLink to="/projects" class="block px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                      @click="menuOpen = false">
            Gérer les projets…
          </RouterLink>
        </div>
      </div>

      <!-- Onglets Gestion / Exécution — scopés sur le projet courant -->
      <nav v-if="pid" class="flex md:flex-col gap-1 p-3">
        <RouterLink
          v-for="item in tabs" :key="item.to" :to="item.to"
          class="group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors"
          :class="isTabActive(item.match)
            ? 'bg-primary/15 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.3)]'
            : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'"
        >
          <svg class="w-4 h-4 shrink-0" :class="isTabActive(item.match) && 'text-primary'"
               fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" :d="item.icon" />
          </svg>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>
    </aside>

    <div class="flex-1 flex flex-col min-w-0">
      <main class="flex-1 overflow-y-auto">
        <div class="mx-auto max-w-5xl p-5 md:p-8 animate-fade-in">
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>
