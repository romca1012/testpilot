<script setup lang="ts">
// LA CORBEILLE — ce qui a été supprimé, et comment le récupérer (lot B, 2026-07-24).
//
// Sans cet écran, la suppression douce serait invisible : l'utilisateur verrait ses éléments
// disparaître sans jamais pouvoir les revoir ni les rendre. Archiver sans pouvoir désarchiver
// n'est qu'une destruction qui s'ignore — et le §7 du brief exige l'inverse.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ElementCorbeille } from '../lib/api'
import { formatDate } from '../lib/format'
import Card from '../components/ui/Card.vue'
import Spinner from '../components/ui/Spinner.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)

const elements = ref<ElementCorbeille[]>([])
const chargement = ref(true)
const erreur = ref('')
const enCours = ref<string>('')

// Libellés MÉTIER : le type technique (`specification`, `cas`) ne s'affiche jamais tel quel (§8).
const LIBELLE: Record<string, string> = {
  projet: 'Projet', module: 'Module', specification: 'Spécification', cas: 'Cas de test',
}

async function charger() {
  chargement.value = true
  erreur.value = ''
  try {
    elements.value = await api.listerCorbeille(pid.value)
  } catch (e: any) {
    erreur.value = e?.message || 'Corbeille indisponible.'
  } finally {
    chargement.value = false
  }
}
watch(pid, charger, { immediate: true })

async function restaurer(e: ElementCorbeille) {
  enCours.value = `${e.type}-${e.id}`
  try {
    await api.restaurer(e.type, e.id)
    await charger()
  } catch (err: any) {
    erreur.value = err?.message || 'Restauration impossible.'
  } finally {
    enCours.value = ''
  }
}

async function purger(e: ElementCorbeille) {
  // Double confirmation par le texte : c'est le seul geste irréversible du produit, il ne doit
  // pas pouvoir se déclencher par un clic distrait.
  if (!window.confirm(
    `Détruire définitivement « ${e.titre} » ?\n\n`
    + `Cette action est IRRÉVERSIBLE : son historique (versions, exécutions, coûts) sera perdu.`)) return
  enCours.value = `${e.type}-${e.id}`
  try {
    await api.purger(e.type, e.id)
    await charger()
  } catch (err: any) {
    erreur.value = err?.message || 'Destruction impossible.'
  } finally {
    enCours.value = ''
  }
}
</script>

<template>
  <div class="space-y-6">
    <button class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            @click="router.push({ name: 'cases', params: { pid } })">
      ← Cas de test
    </button>

    <div>
      <h1 class="text-2xl font-semibold tracking-tight">Corbeille</h1>
      <p class="mt-1 text-sm text-muted-foreground">
        Rien n'est détruit par une suppression : ce qui est ici peut être remis en place. La
        destruction définitive est un geste distinct, et irréversible.
      </p>
    </div>

    <div v-if="chargement" class="flex items-center gap-2 text-sm text-muted-foreground">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>

    <p v-else-if="erreur" class="text-sm text-destructive">{{ erreur }}</p>

    <Card v-else>
      <ul v-if="elements.length" class="divide-y divide-border text-sm">
        <li v-for="e in elements" :key="`${e.type}-${e.id}`"
            class="flex flex-wrap items-center justify-between gap-3 py-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="rounded-full bg-secondary px-2 py-0.5 text-[11px] text-muted-foreground">
                {{ LIBELLE[e.type] || e.type }}
              </span>
              <span class="truncate font-medium">{{ e.titre }}</span>
            </div>
            <div class="mt-0.5 text-xs text-muted-foreground">
              Supprimé le {{ formatDate(e.deleted_at) }}
              <!-- Le nom est une signature DÉCLARÉE (lot 2), pas une identité vérifiée : on ne
                   dit donc pas « par X » comme s'il s'agissait d'un fait établi. -->
              <template v-if="e.deleted_by"> — signé <span class="text-foreground/80">{{ e.deleted_by }}</span></template>
            </div>
          </div>
          <div class="flex shrink-0 items-center gap-3">
            <button class="text-sm text-primary hover:underline disabled:opacity-50"
                    :disabled="enCours === `${e.type}-${e.id}`" @click="restaurer(e)">Restaurer</button>
            <button class="text-sm text-destructive hover:underline disabled:opacity-50"
                    :disabled="enCours === `${e.type}-${e.id}`" @click="purger(e)">Détruire</button>
          </div>
        </li>
      </ul>
      <p v-else class="text-sm text-muted-foreground">
        La corbeille est vide — rien n'a été supprimé dans ce projet.
      </p>
    </Card>
  </div>
</template>
