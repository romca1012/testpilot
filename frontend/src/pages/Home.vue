<script setup lang="ts">
// Point d'entrée unique : après connexion, l'utilisateur choisit toujours son projet.
// Même avec un seul projet, cette étape rend le contexte explicite et donne accès à sa gestion.
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

onMounted(() => { router.replace('/projects') })
</script>

<template>
  <div class="grid min-h-[40vh] place-items-center text-sm text-muted-foreground">Chargement…</div>
</template>
