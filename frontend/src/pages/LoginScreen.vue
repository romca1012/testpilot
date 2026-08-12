<script setup lang="ts">
// Écran de connexion — comptes utilisateurs réels (2026-08-07, remplace le mot de passe
// d'instance partagé du lot 2). Identifiant + mot de passe d'un COMPTE créé par un Admin — plus
// de nom librement déclaré au clavier.
import { ref } from 'vue'
import { api } from '../lib/api'
import { useSession } from '../lib/useSession'
import Button from '../components/ui/Button.vue'
import Spinner from '../components/ui/Spinner.vue'

const emit = defineEmits<{ (e: 'connected'): void }>()
const { charger: chargerSession } = useSession()

const identifiant = ref('')
const motDePasse = ref('')
const erreur = ref('')
const envoi = ref(false)

async function connecter() {
  erreur.value = ''
  if (!identifiant.value.trim() || !motDePasse.value) {
    erreur.value = 'Identifiant et mot de passe sont obligatoires.'
    return
  }
  envoi.value = true
  try {
    await api.login(identifiant.value.trim(), motDePasse.value)
    await chargerSession()   // rafraîchit l'état partagé (rôle compris) pour le reste de l'app
    emit('connected')
  } catch (e: any) {
    erreur.value = e?.status === 401
      ? 'Identifiant ou mot de passe incorrect.'
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
          Connectez-vous avec votre compte.
        </p>
      </div>

      <div>
        <label class="text-sm font-medium">Identifiant</label>
        <input v-model="identifiant" autofocus placeholder="ex. awa"
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
      </div>

      <div>
        <label class="text-sm font-medium">Mot de passe</label>
        <input v-model="motDePasse" type="password"
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
      </div>

      <p v-if="erreur" class="text-sm text-destructive">{{ erreur }}</p>

      <Button type="submit" class="w-full" :disabled="envoi">
        <Spinner v-if="envoi" class="h-4 w-4" />
        <span>{{ envoi ? 'Connexion…' : 'Entrer' }}</span>
      </Button>

      <p class="text-xs text-muted-foreground">
        Pas de compte ? Demandez-en un à un administrateur — la création est réservée à ce rôle.
      </p>
    </form>
  </div>
</template>
