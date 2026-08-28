<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { LIBELLE_ROLE, ROLES, roleSuffisant, type Role } from '../lib/api'
import { DESCRIPTION_ROLE, PERMISSIONS_ROLES } from '../lib/roles'
import Button from '../components/ui/Button.vue'

const route = useRoute()
const router = useRouter()
const role = computed(() => String(route.params.role) as Role)
const valide = computed(() => ROLES.includes(role.value))
const lignes = computed(() => PERMISSIONS_ROLES.map(permission => ({
  ...permission,
  accordee: valide.value && roleSuffisant(role.value, permission.minimum),
})))
</script>

<template>
  <div class="px-4 py-6 sm:px-6 md:px-8">
    <Button variant="ghost" size="sm" @click="router.push({ name: 'utilisateurs', query: { tab: 'roles' } })">← Utilisateurs et rôles</Button>

    <div v-if="!valide" class="mt-5 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive" role="alert">
      Ce rôle n’existe pas.
    </div>

    <template v-else>
      <header class="mt-5 flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Rôle système</div>
          <h1 class="mt-1 text-2xl font-semibold tracking-tight">{{ LIBELLE_ROLE[role] }}</h1>
          <p class="mt-2 max-w-3xl text-sm text-muted-foreground">{{ DESCRIPTION_ROLE[role] }}</p>
        </div>
        <span class="inline-flex w-fit rounded-full bg-secondary px-3 py-1.5 text-xs font-medium text-muted-foreground">Hiérarchie intégrée</span>
      </header>

      <section class="mt-6 rounded-lg border border-info/30 bg-info/10 px-4 py-3 text-sm">
        <h2 class="font-semibold">Fonctionnement actuel</h2>
        <p class="mt-1 text-muted-foreground">Les rôles sont cumulatifs : ce rôle hérite de toutes les permissions des rôles placés avant lui. Cette page décrit les contrôles réellement actifs côté serveur.</p>
      </section>

      <section class="mt-5 overflow-hidden rounded-lg border border-border bg-surface" aria-labelledby="permissions-title">
        <div class="border-b border-border bg-surface-raised px-4 py-3">
          <h2 id="permissions-title" class="font-semibold">Permissions effectives</h2>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full min-w-[720px] text-sm">
            <thead class="bg-surface-raised text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr><th class="px-4 py-3">Domaine</th><th class="px-4 py-3">Action</th><th class="px-4 py-3">État</th><th class="px-4 py-3">Détail</th></tr>
            </thead>
            <tbody>
              <tr v-for="ligne in lignes" :key="`${ligne.groupe}-${ligne.action}`" class="border-t border-border">
                <td class="px-4 py-3 font-medium">{{ ligne.groupe }}</td>
                <td class="px-4 py-3">{{ ligne.action }}</td>
                <td class="px-4 py-3"><span class="inline-flex rounded-full px-2.5 py-1 text-xs font-medium" :class="ligne.accordee ? 'bg-success/10 text-success' : 'bg-secondary text-muted-foreground'">{{ ligne.accordee ? 'Autorisé' : 'Non autorisé' }}</span></td>
                <td class="px-4 py-3 text-muted-foreground">{{ ligne.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <p class="mt-4 text-xs text-muted-foreground">Les permissions ne sont pas modifiables individuellement dans cette version afin d’éviter qu’un réglage visuel diverge des protections du serveur.</p>
    </template>
  </div>
</template>
