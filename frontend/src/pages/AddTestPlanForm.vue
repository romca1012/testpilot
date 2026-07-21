<script setup lang="ts">
// « Ajouter un plan de test » — formulaire UI. Un plan est un CONTENEUR de runs (aucun cas
// directement). Champs réduits (pas de « Assigner à », pas de sélection de cas). Le bloc
// « ajouter des exécutions » simule localement l'ajout de runs (aucune sauvegarde réelle).
// Sauvegarde et génération réelle → backend (§7), donc submit « à venir ».
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const pid = route.params.pid as string

const form = ref({ name: '', refs: '', description: '', startDate: '', endDate: '' })
// Simulation locale des runs ajoutés au plan (pour visualiser le comportement) — non persisté.
const runsInPlan = ref<string[]>([])

function addRunLocally() {
  runsInPlan.value.push(`Exécution ${runsInPlan.value.length + 1}`)
}
function cancel() { router.push({ name: 'executions', params: { pid } }) }
function submit() { window.alert('Créer un plan de test — à venir (backend §7).') }
function comingSoon(w: string) { window.alert(`${w} — à venir.`) }
</script>

<template>
  <div class="max-w-[700px]">
    <h1 class="text-2xl font-semibold tracking-tight">Ajouter un plan de test</h1>

    <form class="mt-6 space-y-5" @submit.prevent="submit">
      <label class="block">
        <span class="text-sm font-medium">Nom <span class="text-destructive">*</span></span>
        <input v-model="form.name" required
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        <span class="text-xs text-muted-foreground">Ex. : Tous les navigateurs pris en charge ou les combinaisons OS/base de données.</span>
      </label>

      <label class="block">
        <span class="text-sm font-medium">Références</span>
        <textarea v-model="form.refs" rows="2"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
        <span class="text-xs text-muted-foreground">Ajoutez des ID de référence aux tickets externes ici.</span>
      </label>

      <label class="block">
        <span class="text-sm font-medium">Jalon</span>
        <select disabled class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 opacity-60" @click="comingSoon('Jalons')">
          <option>Aucun (à venir)</option>
        </select>
      </label>

      <label class="block">
        <span class="text-sm font-medium">Description</span>
        <textarea v-model="form.description" rows="3"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
      </label>

      <div class="grid grid-cols-2 gap-4">
        <label class="block">
          <span class="text-sm font-medium">Date de début</span>
          <input v-model="form.startDate" type="date"
                 class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          <span class="text-xs text-muted-foreground">La date de début prévue ou programmée.</span>
        </label>
        <label class="block">
          <span class="text-sm font-medium">Date de fin</span>
          <input v-model="form.endDate" type="date"
                 class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
          <span class="text-xs text-muted-foreground">La date d'échéance ou de fin prévue.</span>
        </label>
      </div>

      <!-- Bloc « ajouter des exécutions » — un plan se peuple de runs, pas de cas -->
      <div class="rounded-lg border border-dashed border-border p-4">
        <p class="text-sm">Ajoutez des exécutions de test à ce plan.</p>
        <p class="text-xs text-muted-foreground mt-1">
          Pour chaque entrée et/ou configuration ajoutée, une exécution de test correspondante est
          démarrée automatiquement.
        </p>
        <ul v-if="runsInPlan.length" class="mt-3 space-y-1">
          <li v-for="(r, i) in runsInPlan" :key="i" class="text-sm flex items-center gap-2">
            <svg class="w-3.5 h-3.5 text-success" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 12.5l4.2 4.2L19 6.8"/></svg>
            {{ r }} <span class="text-xs text-muted-foreground">(ajoutée localement, non enregistrée)</span>
          </li>
        </ul>
        <button type="button" class="mt-3 rounded-md bg-surface-raised border border-border px-3 py-1.5 text-sm flex items-center gap-1.5 hover:border-primary/40" @click="addRunLocally">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          Ajouter une exécution de test
        </button>
      </div>

      <div class="flex items-center gap-3 pt-2">
        <button type="submit" class="rounded-md bg-success text-white font-semibold px-4 py-2 flex items-center gap-2 hover:bg-success/90">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 12.5l4.2 4.2L19 6.8"/></svg>
          Ajouter un plan de test
        </button>
        <button type="button" class="rounded-md border border-destructive/50 text-destructive px-4 py-2 hover:bg-destructive/10" @click="cancel">Annuler</button>
      </div>
    </form>
  </div>
</template>
