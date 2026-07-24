<script setup lang="ts">
// Écran de connexion — verrou d'instance (2026-07-24, lot 2 du déploiement).
//
// Ce n'est PAS un système de comptes (hors V1, §8 du brief) : un mot de passe unique partagé par
// l'équipe, plus un nom libre. Le texte de l'écran doit le dire — laisser croire à un compte
// personnel serait un « affiché ≠ réel » sur la sécurité elle-même, le pire endroit pour en faire.
import { ref } from 'vue'
import { api } from '../lib/api'
import Button from '../components/ui/Button.vue'
import Spinner from '../components/ui/Spinner.vue'

const emit = defineEmits<{ (e: 'connected', name: string): void }>()

const nom = ref(localStorage.getItem('testpilot.nom') || '')
const motDePasse = ref('')
const erreur = ref('')
const envoi = ref(false)

async function connecter() {
  erreur.value = ''
  if (!nom.value.trim()) { erreur.value = 'Indiquez votre nom : il signera les cas que vous créez.'; return }
  envoi.value = true
  try {
    const session = await api.login(motDePasse.value, nom.value.trim())
    // Mémorisé pour la prochaine ouverture — confort, pas sécurité : ce nom n'est pas un secret.
    localStorage.setItem('testpilot.nom', session.name)
    emit('connected', session.name)
  } catch (e: any) {
    erreur.value = e?.status === 401
      ? "Mot de passe incorrect."
      : (e?.message || 'Connexion impossible.')
  } finally {
    envoi.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center px-4">
    <form class="w-full max-w-sm space-y-5" @submit.prevent="connecter">
      <div>
        <h1 class="text-xl font-semibold tracking-tight">TestPilot</h1>
        <p class="mt-1 text-sm text-muted-foreground">
          Cette instance est protégée par un mot de passe partagé.
        </p>
      </div>

      <div>
        <label class="text-sm font-medium">Votre nom</label>
        <input v-model="nom" autofocus placeholder="ex. Awa"
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        <p class="mt-1 text-xs text-muted-foreground">
          Il signe les cas que vous créez et les relectures que vous validez. Il n'est pas vérifié —
          c'est une signature, pas une identité.
        </p>
      </div>

      <div>
        <label class="text-sm font-medium">Mot de passe de l'instance</label>
        <input v-model="motDePasse" type="password"
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
      </div>

      <p v-if="erreur" class="text-sm text-destructive">{{ erreur }}</p>

      <Button type="submit" class="w-full" :disabled="envoi">
        <Spinner v-if="envoi" class="h-4 w-4" />
        <span>{{ envoi ? 'Connexion…' : 'Entrer' }}</span>
      </Button>
    </form>
  </div>
</template>
