<script setup lang="ts">
// Onglet « Configurations » (lot PT-01a) — DANS QUELLES CONDITIONS les tests sont joués. Pour l'instant : le navigateur de
// test (langue, fuseau, taille de fenêtre), tel qu'il existait dans « Identité et application » (lot 07c). Les environnements
// multiples viendront au lot PT-04 ; rien n'est annoncé à l'écran avant d'exister.
//
// Mêmes champs, même route (`PATCH /api/projects/:id`), mêmes règles : une valeur vide rend la main au défaut, une valeur mal
// formée est refusée par le serveur (422). Seuls ces trois champs partent : l'identité et la connexion ne sont jamais renvoyées.
import { computed, reactive, ref, watch } from 'vue'
import { api, type ProjectSummary } from '../../lib/api'
import Button from '../ui/Button.vue'
import { projetEnregistre } from './fusion'

const props = defineProps<{ projet: ProjectSummary; peutRegler: boolean }>()
const emit = defineEmits<{ (e: 'enregistre', projet: ProjectSummary): void; (e: 'modifie', valeur: boolean): void }>()

const form = reactive({ browser_locale: '', browser_timezone: '', browser_viewport: '' })
const initial = ref({ ...form })
const enregistrement = ref(false)
const erreur = ref('')
const enregistreA = ref(false)

const modifie = computed(() => Object.entries(form).some(([k, v]) => (initial.value as Record<string, string>)[k] !== v))
watch(modifie, (v) => emit('modifie', v), { immediate: true })

function reprendre(p: ProjectSummary) {
  form.browser_locale = p.browser_locale || ''
  form.browser_timezone = p.browser_timezone || ''
  form.browser_viewport = p.browser_viewport || ''
  initial.value = { ...form }
}
// La page renvoie le projet après chaque enregistrement : on ne reprend ses valeurs que si rien n'est en cours de saisie
// (revue du 2026-10-13 : déclarer la remise à zéro effaçait une adresse tapée mais pas encore enregistrée).
reprendre(props.projet)
watch(() => props.projet, (p) => { if (!modifie.value) reprendre(p) })


async function enregistrer() {
  if (!props.peutRegler || !modifie.value) return
  enregistrement.value = true
  erreur.value = ''
  enregistreA.value = false
  try {
    const maj = await api.updateProject(props.projet.id, {
      browser_locale: form.browser_locale.trim(),
      browser_timezone: form.browser_timezone.trim(),
      browser_viewport: form.browser_viewport.trim(),
    })
    const enregistre = projetEnregistre(props.projet, maj)
    // L'onglet repart de ce que le serveur a enregistré, sans attendre que la page lui renvoie le projet.
    reprendre(enregistre)
    emit('enregistre', enregistre)
    enregistreA.value = true
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrement.value = false
  }
}
</script>

<template>
  <form class="rounded-xl border border-border bg-surface-raised shadow-sm" data-testid="configurations" @submit.prevent="enregistrer">
    <fieldset class="p-4 sm:p-6" :disabled="!peutRegler">
      <legend class="sr-only">Navigateur de test</legend>
      <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground" aria-hidden="true">Navigateur de test</div>
      <div class="mt-3 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <label class="block"><span class="text-sm font-medium">Langue</span>
          <input v-model="form.browser_locale" data-testid="browser-locale" :placeholder="projet.browser_effectif?.locale || 'fr-FR'"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary disabled:cursor-not-allowed disabled:opacity-60" /></label>
        <label class="block"><span class="text-sm font-medium">Fuseau horaire</span>
          <input v-model="form.browser_timezone" data-testid="browser-timezone" :placeholder="projet.browser_effectif?.timezone || 'Europe/Paris'"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary disabled:cursor-not-allowed disabled:opacity-60" /></label>
        <label class="block"><span class="text-sm font-medium">Taille de fenêtre</span>
          <input v-model="form.browser_viewport" data-testid="browser-viewport" :placeholder="projet.browser_effectif?.viewport || '1440x900'"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary disabled:cursor-not-allowed disabled:opacity-60" /></label>
      </div>
      <!-- Une valeur enregistrée mais mal formée est ÉCARTÉE au profit du défaut : l'écran le dit, jamais en silence. -->
      <ul v-if="projet.browser_avertissements?.length" class="mt-3 text-xs text-warning" data-testid="browser-avertissements">
        <li v-for="a in projet.browser_avertissements" :key="a">{{ a }} — le défaut est utilisé à la place.</li>
      </ul>
    </fieldset>
    <div class="flex items-center justify-end gap-3 border-t border-border bg-surface px-4 py-4 sm:px-6">
      <span v-if="erreur" role="alert" class="mr-auto text-sm text-destructive">{{ erreur }}</span>
      <span v-else-if="enregistreA && !modifie" role="status" class="mr-auto text-sm text-success" data-testid="enregistre">Enregistré</span>
      <Button type="button" variant="secondary" :disabled="!modifie || enregistrement" @click="reprendre(projet)">Annuler</Button>
      <Button type="submit" variant="primary" :loading="enregistrement" :disabled="!peutRegler || !modifie">Enregistrer</Button>
    </div>
  </form>
</template>
