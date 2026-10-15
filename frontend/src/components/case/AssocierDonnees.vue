<script setup lang="ts">
// Étape E1 (A39) : associer d'un clic un test déjà écrit aux données de test du projet. Le SERVEUR propose — une proposition
// par variable, avec toutes ses lignes : elle s'applique en entier ou pas du tout — et écrit ; l'écran ne fait que montrer
// l'avant/après et cocher, il n'envoie jamais de texte (vérifications comprises, ouvertes à tous : A40). Rien à proposer :
// le bouton n'apparaît pas.
import { computed, onMounted, ref, watch } from 'vue'
import { api, type Associations } from '../../lib/api'
import Button from '../ui/Button.vue'
import Modal from '../ui/Modal.vue'

const props = defineProps<{ caseId: number; versionId: number | null }>()
const emit = defineEmits<{ associe: [] }>()

const associations = ref<Associations | null>(null)
const ouvert = ref(false)
const choix = ref<string[]>([])
const envoi = ref(false)
const erreur = ref('')
const ecrite = (nom: string) => `{{${nom}}}`   // jamais écrit en dur dans le gabarit : Vue y lirait une expression

async function charger() {
  associations.value = null
  if (!props.versionId) return
  try {
    const trouve = await api.associationsDuCas(props.caseId)
    if (trouve.version_id === props.versionId) associations.value = trouve
  } catch { associations.value = null }   // illisible : pas de bouton, le reste de la fiche est intact
}
onMounted(charger)
watch(() => props.versionId, charger)

const propositions = computed(() => associations.value?.propositions ?? [])
function ouvrir() {
  choix.value = propositions.value.map((p) => p.id)
  erreur.value = ''
  ouvert.value = true
}
async function associer() {
  if (!associations.value || !choix.value.length) return
  envoi.value = true
  erreur.value = ''
  try {
    await api.associerDonnees(props.caseId, associations.value.version_id, choix.value)
    ouvert.value = false
    emit('associe')
  } catch (e: any) {
    erreur.value = e?.message || 'Association impossible.'
  } finally {
    envoi.value = false
  }
}
</script>

<template>
  <span v-if="propositions.length">
    <button type="button" class="text-sm text-primary hover:underline" data-testid="associer-donnees" @click="ouvrir">
      Associer aux données de test
    </button>
    <Modal :open="ouvert" title="Associer aux données de test" @close="ouvert = false">
      <ul class="space-y-4 text-sm" data-testid="associations">
        <li v-for="p in propositions" :key="p.id">
          <label class="flex min-h-11 cursor-pointer items-start gap-3">
            <input v-model="choix" type="checkbox" :value="p.id" :data-testid="`association-${p.id}`"
                   class="mt-1 accent-[hsl(var(--primary))]" />
            <span class="min-w-0 flex-1">
              <span class="font-medium">{{ p.valeur }}</span>
              <span class="mx-1 text-muted-foreground">→</span>
              <span class="font-mono">{{ ecrite(p.variable) }}</span>
              <span v-for="l in p.lignes" :key="l.ligne" class="mt-1 block font-mono text-xs">
                <span class="block text-muted-foreground line-through">{{ l.ligne }}  {{ l.avant }}</span>
                <span class="block">{{ l.ligne }}  {{ l.apres }}</span>
              </span>
            </span>
          </label>
        </li>
      </ul>
      <p v-if="erreur" role="alert" class="mt-3 text-sm text-destructive">{{ erreur }}</p>
      <template #footer>
        <Button type="button" variant="secondary" @click="ouvert = false">Annuler</Button>
        <Button type="button" variant="primary" data-testid="associer-confirmer" :loading="envoi" :disabled="!choix.length"
                @click="associer">Associer</Button>
      </template>
    </Modal>
  </span>
</template>
