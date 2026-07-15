<script setup lang="ts">
// Point d'entrée : commodité d'auto-sélection quand il n'existe qu'UN projet (on entre
// directement dans son contexte). Sinon → page de gestion des projets. La gestion reste
// toujours atteignable via /projects (cette logique ne s'applique qu'à la racine).
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../lib/api'

const router = useRouter()

onMounted(async () => {
  try {
    const projects = await api.listProjects()
    if (projects.length === 1) {
      router.replace(`/projects/${projects[0].id}/cases`)
    } else {
      router.replace('/projects')
    }
  } catch {
    router.replace('/projects')
  }
})
</script>

<template>
  <div class="grid min-h-[40vh] place-items-center text-sm text-muted-foreground">Chargement…</div>
</template>
