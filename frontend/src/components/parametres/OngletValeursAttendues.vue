<script setup lang="ts">
// Onglet « Valeurs attendues » (lot PT-03) — COMMENT l'application écrit ses nombres, pour que l'outil les lise correctement.
// Un réglage déclaré par une personne : l'écriture des nombres (« 1.234 » : mille deux cent trente-quatre, ou un virgule
// deux cent trente-quatre ?), plus les unités que le projet ajoute lui-même. Rien de choisi = rien de déclaré : l'outil ne
// suppose rien. Aucune base toute faite (A38, porteur, 2026-10-15) : pas de monnaie du projet.
// Les règles de calcul rejoindront cet onglet au lot PT-06 ; rien n'est annoncé à l'écran avant d'exister.
//
// Les choix proposés viennent du serveur (`/api/settings/options/valeurs-du-projet`) : l'écran ne tient pas sa propre liste.
// Seul ce champ part dans l'enregistrement.
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, type ProjectSummary, type ValeursDuProjetOptions } from '../../lib/api'
import Button from '../ui/Button.vue'
import UnitesAjoutees from './UnitesAjoutees.vue'
import { projetEnregistre } from './fusion'

const props = defineProps<{ projet: ProjectSummary; peutRegler: boolean }>()
const emit = defineEmits<{ (e: 'enregistre', projet: ProjectSummary): void; (e: 'modifie', valeur: boolean): void }>()

const form = reactive({ format_nombre: '' })
const initial = ref({ ...form })
const options = ref<ValeursDuProjetOptions>({ formats_nombre: [] })
const enregistrement = ref(false)
const erreur = ref('')
const enregistreA = ref(false)

const modifie = computed(() => Object.entries(form).some(([k, v]) => (initial.value as Record<string, string>)[k] !== v))
watch(modifie, (v) => emit('modifie', v), { immediate: true })

// Une écriture enregistrée reste proposée, elle aussi — sous un libellé, jamais sous sa clé (aucune valeur brute à l'écran).
const formats = computed(() => {
  const connus = [...options.value.formats_nombre]
  if (form.format_nombre && !connus.some((f) => f.cle === form.format_nombre)) connus.push({ cle: form.format_nombre, libelle: 'Écriture enregistrée' })
  return connus
})

function reprendre(p: ProjectSummary) {
  form.format_nombre = p.format_nombre || ''
  initial.value = { ...form }
}
// Même règle que les autres onglets : une saisie en cours n'est pas écrasée quand la page renvoie le projet.
reprendre(props.projet)
watch(() => props.projet, (p) => { if (!modifie.value) reprendre(p) })

onMounted(async () => {
  try {
    options.value = await api.valeursDuProjetOptions()
  } catch (e: any) {
    erreur.value = e?.message || 'Les choix proposés n\'ont pas pu être chargés.'
  }
})

async function enregistrer() {
  if (!props.peutRegler || !modifie.value) return
  enregistrement.value = true
  erreur.value = ''
  enregistreA.value = false
  try {
    const maj = await api.updateProject(props.projet.id, { format_nombre: form.format_nombre })
    const enregistre = projetEnregistre(props.projet, maj)
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
  <div>
  <form class="rounded-xl border border-border bg-surface-raised shadow-sm" data-testid="valeurs-attendues" @submit.prevent="enregistrer">
    <fieldset class="p-4 sm:p-6" :disabled="!peutRegler">
      <legend class="sr-only">Écriture des valeurs</legend>
      <div class="text-xs font-medium uppercase tracking-wide text-muted-foreground" aria-hidden="true">Écriture des valeurs</div>
      <div class="mt-3 grid grid-cols-1 gap-4 sm:max-w-sm">
        <label class="block"><span class="text-sm font-medium">Écriture des nombres</span>
          <select v-model="form.format_nombre" data-testid="format-nombre"
                  class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary disabled:cursor-not-allowed disabled:opacity-60">
            <option value="">Non déclarée</option>
            <option v-for="f in formats" :key="f.cle" :value="f.cle">{{ f.libelle }}</option>
          </select></label>
      </div>
    </fieldset>
    <div class="flex items-center justify-end gap-3 border-t border-border bg-surface px-4 py-4 sm:px-6">
      <span v-if="erreur" role="alert" class="mr-auto text-sm text-destructive">{{ erreur }}</span>
      <span v-else-if="enregistreA && !modifie" role="status" class="mr-auto text-sm text-success" data-testid="enregistre">Enregistré</span>
      <Button type="button" variant="secondary" :disabled="!modifie || enregistrement" @click="reprendre(projet)">Annuler</Button>
      <Button type="submit" variant="primary" :loading="enregistrement" :disabled="!peutRegler || !modifie">Enregistrer</Button>
    </div>
  </form>
  <!-- Les unités s'enregistrent une à une, dans leur propre fenêtre : elles ne dépendent pas du bouton ci-dessus. -->
  <UnitesAjoutees :projet="projet" :peut-regler="peutRegler" />
  </div>
</template>
