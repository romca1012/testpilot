<script setup lang="ts">
// « Ajouter une exécution de test » — formulaire UI (pas de fausse donnée : ce sont des champs).
// La sauvegarde attend le backend « Exécution nommée transverse » (§7) → submit « à venir ».
// Jalons / Assignation ne sont pas au modèle → selects désactivés « à venir ».
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const pid = route.params.pid as string

const today = new Date().toISOString().slice(0, 10)
const form = ref({
  name: `Exécution de test ${today}`,
  refs: '',
  description: '',
  startDate: '',
  endDate: '',
  selection: 'all' as 'all' | 'specific' | 'dynamic',
})

function cancel() { router.push({ name: 'executions', params: { pid } }) }
function submit() { window.alert('Créer une exécution de test — à venir (backend Exécution nommée §7).') }
function comingSoon(w: string) { window.alert(`${w} — à venir.`) }

const SELECTIONS = [
  { key: 'all', title: 'Inclure tous les cas de test',
    desc: 'Inclut tous les cas de test dans cette exécution. Les nouveaux cas ajoutés au référentiel y sont automatiquement inclus.' },
  { key: 'specific', title: 'Sélectionner des cas de test spécifiques',
    desc: 'Vous choisissez les cas à inclure. Les nouveaux cas ne sont pas automatiquement ajoutés à cette exécution.' },
  { key: 'dynamic', title: 'Filtrage dynamique',
    desc: 'Les cas sont ajoutés automatiquement selon un filtre. De nouveaux cas rejoignent l\'exécution s\'ils correspondent (sauf si elle est terminée).' },
] as const
</script>

<template>
  <div class="max-w-[700px]">
    <h1 class="text-2xl font-semibold tracking-tight">Ajouter une exécution de test</h1>

    <form class="mt-6 space-y-5" @submit.prevent="submit">
      <label class="block">
        <span class="text-sm font-medium">Nom <span class="text-destructive">*</span></span>
        <input v-model="form.name" required
               class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none" />
        <span class="text-xs text-muted-foreground">Ex. : Exécution de test 2014-08-01, Build 240 ou Version 3.0</span>
      </label>

      <label class="block">
        <span class="text-sm font-medium">Références</span>
        <textarea v-model="form.refs" rows="2"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 focus:border-primary outline-none"></textarea>
        <span class="text-xs text-muted-foreground">Ajoutez des ID de référence aux tickets externes ici.</span>
      </label>

      <div class="grid grid-cols-2 gap-4">
        <label class="block">
          <span class="text-sm font-medium">Jalon</span>
          <select disabled class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 opacity-60" @click="comingSoon('Jalons')">
            <option>Aucun (à venir)</option>
          </select>
        </label>
        <label class="block">
          <span class="text-sm font-medium">Assigner à</span>
          <select disabled class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2 opacity-60" @click="comingSoon('Assignation')">
            <option>Aucun (à venir)</option>
          </select>
        </label>
      </div>

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

      <!-- Sélection des cas -->
      <div>
        <span class="text-sm font-medium">Sélection des cas de test <span class="text-destructive">*</span></span>
        <div class="mt-2 space-y-2">
          <label v-for="s in SELECTIONS" :key="s.key"
                 class="flex gap-3 rounded-md border p-3 cursor-pointer transition-colors"
                 :class="form.selection === s.key ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'">
            <input type="radio" :value="s.key" v-model="form.selection" class="mt-1 accent-[hsl(var(--primary))]" />
            <div>
              <div class="text-sm font-medium">{{ s.title }}</div>
              <p class="text-xs text-muted-foreground mt-0.5">{{ s.desc }}</p>
              <button v-if="s.key === 'specific' && form.selection === 'specific'" type="button"
                      class="mt-2 text-xs text-primary hover:underline" @click="comingSoon('Changer la sélection')">Changer la sélection…</button>
              <button v-if="s.key === 'dynamic' && form.selection === 'dynamic'" type="button"
                      class="mt-2 text-xs text-primary hover:underline" @click="comingSoon('Définir un filtre')">Définir un filtre…</button>
            </div>
          </label>
        </div>
      </div>

      <div class="flex items-center gap-3 pt-2">
        <button type="submit" class="rounded-md bg-success text-white font-semibold px-4 py-2 flex items-center gap-2 hover:bg-success/90">
          <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M5 12.5l4.2 4.2L19 6.8"/></svg>
          Ajouter une exécution de test
        </button>
        <button type="button" class="rounded-md border border-destructive/50 text-destructive px-4 py-2 hover:bg-destructive/10" @click="cancel">Annuler</button>
      </div>
    </form>
  </div>
</template>
