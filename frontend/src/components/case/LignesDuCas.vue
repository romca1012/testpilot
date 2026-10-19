<script setup lang="ts">
// Décisions A57 et A58 (2026-10-19) : les lignes PROPRES À CE CAS — ses classes de valeurs (« 17 ans → Accès refusé »),
// une itération par ligne quand on lance ce cas. Les colonnes sont des variables du projet ; une case vide reprend la valeur
// du projet (affichée « — »). Le tableau du projet garde ce qui est partagé par plusieurs cas.
import { computed, onMounted, ref } from 'vue'
import { api, type VariableDeTest } from '../../lib/api'
import Button from '../ui/Button.vue'

const props = defineProps<{ caseId: number | string; peutModifier: boolean }>()

interface Ligne { id?: number; nom: string; valeurs: Record<string, string> }

const variables = ref<VariableDeTest[]>([])
const lignes = ref<Ligne[]>([])
const colonnes = ref<string[]>([])          // ids des variables affichées, dans l'ordre du projet
const edition = ref(false)
const brouillon = ref<Ligne[]>([])
const colonnesBrouillon = ref<string[]>([])
const enregistrement = ref(false)
const erreur = ref('')
const ecarts = ref<string[]>([])   // le test n'emploie pas une variable des lignes : il ne se joue pas

const nomDe = (id: string) => variables.value.find((v) => String(v.id) === id)?.nom ?? '?'
const affichees = computed(() => (edition.value ? colonnesBrouillon.value : colonnes.value))
const ajoutables = computed(() => variables.value.filter((v) => !colonnesBrouillon.value.includes(String(v.id))))

function colonnesDe(ls: Ligne[]): string[] {
  const vues = new Set(ls.flatMap((l) => Object.keys(l.valeurs)))
  return variables.value.map((v) => String(v.id)).filter((id) => vues.has(id))
}

async function charger() {
  try {
    const d = await api.getCaseData(props.caseId)
    variables.value = d.variables
    lignes.value = d.lignes.map((l) => ({ id: l.id, nom: l.nom, valeurs: { ...l.valeurs } }))
    colonnes.value = colonnesDe(lignes.value)
    ecarts.value = d.ecarts ?? []
  } catch { variables.value = [] }   // illisible : la section ne s'affiche pas, la fiche reste utilisable
}

function modifier() {
  brouillon.value = lignes.value.map((l) => ({ id: l.id, nom: l.nom, valeurs: { ...l.valeurs } }))
  colonnesBrouillon.value = [...colonnes.value]
  if (!brouillon.value.length) brouillon.value.push({ nom: '', valeurs: {} })
  erreur.value = ''
  edition.value = true
}

function ajouterColonne(id: string) {
  if (!id) return
  colonnesBrouillon.value = variables.value.map((v) => String(v.id)).filter((v) => v === id || colonnesBrouillon.value.includes(v))
}

function retirerColonne(id: string) {
  colonnesBrouillon.value = colonnesBrouillon.value.filter((c) => c !== id)
  for (const l of brouillon.value) delete l.valeurs[id]
}

async function enregistrer() {
  enregistrement.value = true
  erreur.value = ''
  try {
    const envoi = brouillon.value.map((l) => ({
      ...(l.id ? { id: l.id } : {}),
      nom: l.nom.trim(),
      valeurs: Object.fromEntries(colonnesBrouillon.value.map((id) => [id, (l.valeurs[id] ?? '').trim()]).filter(([, v]) => v !== '')),
    }))
    const d = await api.setCaseData(props.caseId, envoi)
    lignes.value = d.lignes.map((l) => ({ id: l.id, nom: l.nom, valeurs: { ...l.valeurs } }))
    colonnes.value = colonnesDe(lignes.value)
    ecarts.value = d.ecarts ?? []
    edition.value = false
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrement.value = false
  }
}

onMounted(charger)
</script>

<template>
  <section v-if="variables.length" class="mt-6" data-testid="lignes-du-cas">
    <h2 class="flex items-center justify-between gap-3 border-b border-border pb-2 font-semibold">
      <span>Données de test de ce cas</span>
      <span class="flex items-center gap-3 text-xs font-normal text-muted-foreground">
        <span v-if="!edition && lignes.length && !ecarts.length" data-testid="nombre-iterations">{{ lignes.length }} itération{{ lignes.length > 1 ? 's' : '' }}</span>
        <span v-else-if="!edition && ecarts.length" class="text-warning" data-testid="non-joue">Non joué</span>
        <Button v-if="peutModifier && !edition" variant="ghost" size="sm" data-testid="modifier-lignes" @click="modifier">Modifier</Button>
      </span>
    </h2>

    <p v-if="!edition && ecarts.length" class="mt-3 rounded-md border border-warning/30 bg-warning/10 px-3 py-2 text-sm"
       role="status" data-testid="ecarts-lignes">{{ ecarts.join(' ; ') }}. Citez-la dans les étapes ou le résultat attendu du cas puis régénérez le test, ou retirez cette colonne.</p>
    <p v-if="!edition && !lignes.length" class="mt-3 text-muted-foreground">Aucune : le cas est joué avec les valeurs du projet.</p>

    <div v-else class="mt-3 overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b border-border text-left text-xs text-muted-foreground">
            <th scope="col" class="w-8 py-1.5 pr-2 font-medium"></th>
            <th scope="col" class="py-1.5 pr-3 font-medium">Ligne</th>
            <th v-for="id in affichees" :key="id" scope="col" class="py-1.5 pr-3 font-mono font-normal" data-testid="colonne">
              <span class="inline-flex items-center gap-1">{{ '{' + '{' + nomDe(id) + '}' + '}' }}
                <button v-if="edition" type="button" class="text-muted-foreground hover:text-destructive"
                        :aria-label="`Retirer la colonne ${nomDe(id)}`" @click="retirerColonne(id)">×</button>
              </span>
            </th>
            <th v-if="edition && ajoutables.length" scope="col" class="py-1.5 font-normal">
              <select class="rounded border border-border bg-background px-1 py-0.5 text-xs text-foreground" aria-label="Ajouter une colonne"
                      data-testid="ajouter-colonne" @change="ajouterColonne(($event.target as HTMLSelectElement).value); ($event.target as HTMLSelectElement).value = ''">
                <option value="">+ Colonne</option>
                <option v-for="v in ajoutables" :key="v.id" :value="String(v.id)">{{ v.nom }}</option>
              </select>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(l, i) in (edition ? brouillon : lignes)" :key="i" class="border-b border-border last:border-0" data-testid="ligne">
            <td class="py-1.5 pr-2 text-xs tabular-nums text-muted-foreground">{{ i + 1 }}</td>
            <td class="py-1.5 pr-3">
              <input v-if="edition" v-model="l.nom" :aria-label="`Nom de la ligne ${i + 1}`" maxlength="60"
                     class="w-36 rounded border border-border bg-background px-1.5 py-1" />
              <template v-else>{{ l.nom || `Ligne ${i + 1}` }}</template>
            </td>
            <td v-for="id in affichees" :key="id" class="py-1.5 pr-3">
              <input v-if="edition" v-model="l.valeurs[id]" :aria-label="`${nomDe(id)}, ligne ${i + 1}`" placeholder="valeur du projet"
                     class="w-36 rounded border border-border bg-background px-1.5 py-1" :data-testid="`case-${i}-${id}`" />
              <span v-else-if="l.valeurs[id]" class="break-all">{{ l.valeurs[id] }}</span>
              <span v-else class="text-muted-foreground" title="Valeur du projet">—</span>
            </td>
            <td v-if="edition" class="py-1.5 text-right">
              <button type="button" class="text-muted-foreground hover:text-destructive" :aria-label="`Retirer la ligne ${i + 1}`"
                      @click="brouillon.splice(i, 1)">×</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="edition" class="mt-3 flex flex-wrap items-center gap-2">
      <Button variant="secondary" size="sm" data-testid="ajouter-ligne" @click="brouillon.push({ nom: '', valeurs: {} })">Ajouter une ligne</Button>
      <span class="flex-1"></span>
      <span v-if="erreur" class="text-sm text-destructive" role="alert">{{ erreur }}</span>
      <Button variant="ghost" size="sm" @click="edition = false">Annuler</Button>
      <Button size="sm" :disabled="enregistrement" data-testid="enregistrer-lignes" @click="enregistrer">Enregistrer</Button>
    </div>
  </section>
</template>
