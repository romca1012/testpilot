<script setup lang="ts">
import { computed } from 'vue'
import ThemeSwitch from './ThemeSwitch.vue'
import AccountMenu from './AccountMenu.vue'
import { useSettings } from '../lib/useSettings'

const { get } = useSettings()
const nomInstance = computed(() => get('instance_name') || 'TestPilot')
</script>

<template>
  <div class="min-h-screen bg-background">
    <header class="border-b border-border bg-surface/90 backdrop-blur-sm">
      <div class="mx-auto flex min-h-16 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <RouterLink to="/projects"
                    class="inline-flex min-h-11 items-center text-lg font-semibold text-foreground">
          TestPilot
        </RouterLink>
        <div class="h-6 w-px bg-border" aria-hidden="true"></div>
        <div class="min-w-0 flex-1">
          <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Instance</div>
          <div class="truncate font-semibold">{{ nomInstance }}</div>
        </div>
        <div class="flex items-center gap-3"><ThemeSwitch /><AccountMenu /></div>
      </div>
    </header>

    <div class="mx-auto grid max-w-7xl grid-cols-1 md:grid-cols-[240px_minmax(0,1fr)]">
      <aside class="border-b border-border bg-surface/50 px-4 py-3 md:min-h-[calc(100vh-4rem)] md:border-b-0 md:border-r md:px-3 md:py-6">
        <nav aria-label="Administration de l’instance" class="flex gap-2 overflow-x-auto md:flex-col md:overflow-visible">
          <RouterLink to="/admin/projects"
                      class="inline-flex min-h-11 shrink-0 items-center rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
                      active-class="bg-primary/10 text-primary">
            Projets
          </RouterLink>
          <RouterLink to="/utilisateurs"
                      class="inline-flex min-h-11 shrink-0 items-center rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
                      active-class="bg-primary/10 text-primary">
            Utilisateurs et rôles
          </RouterLink>
          <RouterLink to="/settings"
                      class="inline-flex min-h-11 shrink-0 items-center rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
                      active-class="bg-primary/10 text-primary">
            Intégrations
          </RouterLink>
          <RouterLink to="/settings/general"
                      class="inline-flex min-h-11 shrink-0 items-center rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
                      active-class="bg-primary/10 text-primary">
            Paramètres du site
          </RouterLink>
          <RouterLink to="/settings/security"
                      class="inline-flex min-h-11 shrink-0 items-center rounded-md px-3 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
                      active-class="bg-primary/10 text-primary">
            Sécurité
          </RouterLink>
        </nav>
        <p class="mt-5 hidden border-t border-border pt-4 text-xs leading-5 text-subtle-foreground md:block">
          Ces réglages valent pour toute l’installation, indépendamment du projet sélectionné.
        </p>
      </aside>

      <main class="min-w-0">
        <slot />
      </main>
    </div>
  </div>
</template>
