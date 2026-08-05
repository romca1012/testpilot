<script setup lang="ts">
// Réglages d'INSTANCE — ils valent pour toute l'installation, pas pour un projet (2026-08-04).
//
// ⚠️ **La PROVENANCE de chaque valeur est affichée**, et ce n'est pas un détail d'esthétique :
// la base l'emporte sur la variable d'environnement, qui l'emporte sur le défaut du code. Un
// exploitant qui a posé `TESTPILOT_SERVICE_ACCOUNT` et qui voit autre chose doit comprendre
// pourquoi en un coup d'œil — sinon il cherche une heure, ou pire, conclut que ça ne marche pas.
import { onMounted, ref } from 'vue'
import { api, type SettingOut } from '../lib/api'

const reglages = ref<SettingOut[]>([])
const brouillon = ref<Record<string, string>>({})
const loading = ref(true)
const enregistrement = ref('')
const erreur = ref('')
const succes = ref('')

const PROVENANCE: Record<string, { label: string; hint: string }> = {
  db: { label: 'réglé ici', hint: 'Valeur enregistrée depuis cet écran. Elle a la priorité sur la variable d\'environnement.' },
  env: { label: 'variable d\'environnement', hint: 'Valeur fournie par la configuration du serveur (TESTPILOT_*). Enregistrer ici la remplacera.' },
  default: { label: 'défaut', hint: 'Personne n\'a rien réglé : c\'est la valeur d\'usine.' },
}

async function charger() {
  loading.value = true
  erreur.value = ''
  try {
    reglages.value = await api.listSettings()
    brouillon.value = Object.fromEntries(reglages.value.map((r) => [r.key, r.value]))
  } catch (e: any) {
    erreur.value = e?.message || 'Impossible de charger les réglages.'
  } finally {
    loading.value = false
  }
}
onMounted(charger)

async function enregistrer(cle: string) {
  enregistrement.value = cle
  erreur.value = ''
  succes.value = ''
  try {
    const maj = await api.setSetting(cle, brouillon.value[cle] ?? '')
    reglages.value = reglages.value.map((r) => (r.key === cle ? maj : r))
    // On réaligne le brouillon sur ce que le SERVEUR a retenu : effacer un réglage rend la main
    // à l'environnement, et le champ doit alors montrer la valeur qui s'applique vraiment — pas
    // la chaîne vide que l'utilisateur vient de saisir.
    brouillon.value[cle] = maj.value
    succes.value = 'Réglage enregistré.'
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrement.value = ''
  }
}
</script>

<template>
  <div class="mx-auto max-w-3xl p-6">
    <!-- ⚠️ Cet écran est HORS du shell de projet (les réglages ne dépendent d'aucun projet) : il
         doit donc porter lui-même son chemin de retour. Sans lui, on y arrive et on y reste. -->
    <RouterLink to="/" class="text-sm text-primary hover:underline">← Retour</RouterLink>
    <h1 class="mt-3 text-xl font-semibold">Réglages de l'instance</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Ces réglages valent pour toute l'installation, quels que soient les projets.
    </p>

    <p v-if="erreur" class="mt-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      {{ erreur }}
    </p>
    <p v-if="succes" class="mt-4 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm text-success">
      {{ succes }}
    </p>

    <p v-if="loading" class="mt-6 text-sm text-muted-foreground">Chargement…</p>

    <section v-for="r in reglages" :key="r.key"
             class="mt-6 rounded-lg border border-border bg-surface-raised p-4">
      <div class="flex items-center gap-2">
        <h2 class="font-medium">Compte de service</h2>
        <span class="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground"
              :title="PROVENANCE[r.source]?.hint">{{ PROVENANCE[r.source]?.label || r.source }}</span>
      </div>
      <p class="mt-1 text-sm text-muted-foreground">{{ r.description }}</p>

      <div class="mt-3 flex gap-2">
        <input v-model="brouillon[r.key]" :placeholder="r.value"
               class="flex-1 rounded-md bg-surface border border-border px-3 py-2 focus:border-primary outline-none" />
        <button class="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
                :disabled="enregistrement === r.key" @click="enregistrer(r.key)">
          {{ enregistrement === r.key ? 'Enregistrement…' : 'Enregistrer' }}
        </button>
      </div>
      <p class="mt-2 text-xs text-muted-foreground/80">
        Laisser le champ VIDE efface le réglage : la variable d'environnement du serveur, puis la
        valeur par défaut, reprennent la main.
      </p>
      <!-- ⚠️ Dit explicitement ce que ce champ n'est PAS. La confusion avec le compte de
           connexion à l'application testée ferait écrire « admin » comme auteur des résultats,
           et un rapport prétendrait qu'un humain a testé à la main. -->
      <p class="mt-1 text-xs text-muted-foreground/80">
        Ce nom signe les résultats produits par une exécution automatique. Il n'a aucun rapport
        avec le compte utilisé pour se connecter à l'application testée.
      </p>
    </section>
  </div>
</template>
