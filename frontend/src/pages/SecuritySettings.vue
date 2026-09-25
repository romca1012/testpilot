<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api, type SecurityStatus } from '../lib/api'
import Button from '../components/ui/Button.vue'

const etat = ref<SecurityStatus | null>(null)

// 120 → « 2 h », 90 → « 1 h 30 », 45 → « 45 min » : un délai d'inactivité se lit en heures dès qu'il en vaut une.
function dureeLisible(minutes: number): string {
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `${h} h ${String(m).padStart(2, '0')}` : `${h} h`
}
const loading = ref(true)
const erreur = ref('')

async function charger() {
  loading.value = true
  erreur.value = ''
  try { etat.value = await api.getSecurityStatus() }
  catch (e: any) {
    erreur.value = e?.message === 'Failed to fetch'
      ? 'Le serveur TestPilot est momentanément inaccessible. Vérifiez que l’API est démarrée, puis réessayez.'
      : (e?.message || 'Impossible de vérifier la configuration de sécurité.')
  }
  finally { loading.value = false }
}
onMounted(charger)
</script>

<template>
  <div class="mx-auto max-w-5xl px-4 py-6 sm:px-6 md:py-8">
    <header class="max-w-3xl">
      <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Administration</div>
      <h1 class="mt-1 text-2xl font-semibold tracking-tight">Sécurité</h1>
      <p class="mt-2 text-sm leading-6 text-muted-foreground">
        Vérifiez les protections réellement actives sur cette instance. Les secrets ne sont jamais affichés.
      </p>
    </header>

    <div v-if="erreur" role="alert" class="mt-5 flex flex-col gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive sm:flex-row sm:items-center sm:justify-between">
      <span>{{ erreur }}</span>
      <Button type="button" variant="secondary" size="sm" class="shrink-0" @click="charger">Réessayer</Button>
    </div>
    <p v-if="loading" class="mt-6 text-sm text-muted-foreground" aria-live="polite">Vérification de la configuration…</p>

    <template v-else-if="etat">
      <section class="mt-6 rounded-xl border p-4 sm:p-5"
               :class="etat.production_ready ? 'border-success/30 bg-success/10' : 'border-warning/40 bg-warning/10'">
        <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 class="font-semibold">État pour la production</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              {{ etat.production_ready ? 'Les protections indispensables sont configurées.' : 'Une action de déploiement reste nécessaire.' }}
            </p>
          </div>
          <span class="w-fit rounded-full px-3 py-1 text-xs font-semibold"
                :class="etat.production_ready ? 'bg-success/15 text-success' : 'bg-warning/20 text-warning'">
            {{ etat.production_ready ? 'Prêt' : 'À compléter' }}
          </span>
        </div>
      </section>

      <div class="mt-6 grid gap-4 md:grid-cols-2">
        <section class="rounded-xl border border-border bg-surface-raised p-5">
          <h2 class="font-semibold">Mots de passe</h2>
          <dl class="mt-4 space-y-3 text-sm">
            <div class="flex justify-between gap-4"><dt class="text-muted-foreground">Longueur minimale</dt><dd class="font-medium">{{ etat.password_min_length }} caractères</dd></div>
          </dl>
        </section>

        <section class="rounded-xl border border-border bg-surface-raised p-5">
          <h2 class="font-semibold">Sessions</h2>
          <dl class="mt-4 space-y-3 text-sm">
            <div class="flex justify-between gap-4"><dt class="text-muted-foreground">Déconnexion après inactivité</dt><dd class="font-medium">{{ dureeLisible(etat.session_idle_minutes) }}</dd></div>
            <div class="flex justify-between gap-4"><dt class="text-muted-foreground">Durée maximale d'une session</dt><dd class="font-medium">{{ etat.session_max_hours }} h</dd></div>
            <div class="flex justify-between gap-4"><dt class="text-muted-foreground">Cookie HttpOnly</dt><dd class="font-medium text-success">Actif</dd></div>
            <div class="flex justify-between gap-4"><dt class="text-muted-foreground">SameSite</dt><dd class="font-medium">{{ etat.cookie_same_site }}</dd></div>
          </dl>
        </section>

        <section class="rounded-xl border border-border bg-surface-raised p-5">
          <h2 class="font-semibold">Tentatives de connexion</h2>
          <p class="mt-3 text-sm leading-6 text-muted-foreground">
            Après {{ etat.login_max_failures }} échecs, les nouvelles tentatives sont bloquées pendant
            {{ etat.login_window_minutes }} minutes pour cet identifiant et cette adresse réseau.
          </p>
          <span class="mt-3 inline-flex rounded-full bg-success/10 px-2.5 py-1 text-xs font-medium text-success">Protection active</span>
        </section>

      </div>
    </template>
  </div>
</template>
