<script setup lang="ts">
// Étape 7 (A108, A110) — une fiche de calcul, lue et corrigée sur l'écran de validation des cas : les éléments du calcul
// (chacun avec sa source ; un taux avec sa date de vérification), les étapes, les exemples à retrouver. L'écran ne calcule
// RIEN : chaque modification est vérifiée par le serveur (`/api/calculs/verifier`, le même calculateur que la validation et
// l'exécution), qui dit ce qui manque et si chaque exemple est retrouvé, avec le détail du calcul.
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api, type EtapeDeCalcul, type FicheDeCalcul, type VerificationFiche } from '../../lib/api'
import IconButton from '../ui/IconButton.vue'

const fiche = defineModel<FicheDeCalcul>({ required: true })
const emit = defineEmits<{ verifiee: [utilisable: boolean] }>()

const OPERATIONS: { v: string; label: string }[] = [
  { v: 'additionner', label: 'additionner' }, { v: 'soustraire', label: 'soustraire' },
  { v: 'multiplier', label: 'multiplier' }, { v: 'diviser', label: 'diviser' },
  { v: 'pourcentage', label: 'pourcentage de' }, { v: 'arrondir', label: 'arrondir' },
  { v: 'plafonner', label: 'plafonner à' }, { v: 'plancher', label: 'au moins' },
  { v: 'minimum', label: 'le plus petit de' }, { v: 'maximum', label: 'le plus grand de' },
  { v: 'bareme', label: 'barème' }, { v: 'si', label: 'si … alors … sinon' },
]
const MODES_ARRONDI = [
  { v: 'au_plus_proche', label: 'au plus proche (0,125 → 0,13)' },
  { v: 'au_plus_proche_pair', label: 'au plus proche pair (0,125 → 0,12)' },
  { v: 'inferieur', label: 'vers le bas' }, { v: 'superieur', label: 'vers le haut' }, { v: 'tronquer', label: 'tronquer' },
]
const COMPARATEURS = ['<', '<=', '>', '>=', '=', '!=']
const A_TERMES = ['additionner', 'soustraire', 'multiplier', 'minimum', 'maximum']

const verification = ref<VerificationFiche | null>(null)
const erreurReseau = ref('')
const detailOuvert = ref<number | null>(null)
// Les entrées : les éléments sans valeur fixe — un exemple donne une valeur à chacune.
const entrees = computed(() => fiche.value.elements.filter((e) => !String(e.valeur ?? '').trim()).map((e) => e.nom).filter(Boolean))

function termesTexte(e: EtapeDeCalcul) { return (e.termes ?? []).join(', ') }
function poserTermes(e: EtapeDeCalcul, texte: string) { e.termes = texte.split(',').map((t) => t.trim()).filter(Boolean) }
function changerOperation(e: EtapeDeCalcul, op: string) {
  // Une autre opération repart de ses seuls champs : un champ d'avant (un « par », une condition) ne survit jamais caché.
  const garde = { resultat: e.resultat, operation: op } as EtapeDeCalcul
  if (A_TERMES.includes(op)) garde.termes = ['', '']
  if (op === 'arrondir') Object.assign(garde, { valeur: '', decimales: 2, mode: '' })
  if (op === 'si') Object.assign(garde, { condition: { gauche: '', comparateur: '>=', droite: '' }, alors: '', sinon: '' })
  if (op === 'bareme') Object.assign(garde, { valeur: '', mode: '', tranches: [{ jusqu_a: '', taux: '' }] })
  Object.keys(e).forEach((k) => delete (e as any)[k])
  Object.assign(e, garde)
}
function ajouterElement() { fiche.value.elements.push({ nom: '', valeur: '', source: '' }) }
function ajouterEtape() { fiche.value.etapes.push({ resultat: '', operation: 'multiplier', termes: ['', ''] }) }
function ajouterExemple() { fiche.value.exemples.push({ entrees: {}, attendu: '' }) }

let minuterie: number | undefined
async function verifier() {
  try {
    erreurReseau.value = ''
    // Les champs vides d'une étape ne sont pas envoyés : le calculateur dirait qu'ils sont faux, pas qu'ils manquent.
    verification.value = await api.verifierFiche(fiche.value)
  } catch (e: any) {
    verification.value = null
    erreurReseau.value = e?.message || 'Vérification impossible.'
  }
  emit('verifiee', !!verification.value?.utilisable)
}
watch(fiche, () => {
  window.clearTimeout(minuterie)
  minuterie = window.setTimeout(verifier, 400)
}, { deep: true, immediate: true })
onBeforeUnmount(() => window.clearTimeout(minuterie))
</script>

<template>
  <div class="space-y-3 rounded-md border border-border p-3 text-sm" data-testid="fiche-de-calcul">
    <div class="flex flex-wrap gap-3">
      <label class="flex-1 min-w-48"><span class="text-xs text-muted-foreground">Nom du calcul</span>
        <input v-model="fiche.nom" data-testid="fiche-nom" class="mt-0.5 w-full rounded border border-border bg-surface-raised px-2 py-1" /></label>
      <label class="w-40"><span class="text-xs text-muted-foreground">Unité du résultat</span>
        <input v-model="fiche.unite" placeholder="EUR, %, jours…" class="mt-0.5 w-full rounded border border-border bg-surface-raised px-2 py-1" /></label>
      <label class="w-40"><span class="text-xs text-muted-foreground">Résultat</span>
        <input v-model="fiche.resultat" placeholder="nom de l'étape finale" class="mt-0.5 w-full rounded border border-border bg-surface-raised px-2 py-1" /></label>
    </div>

    <ul v-if="fiche.a_confirmer?.length" class="rounded bg-warning/10 px-3 py-2 text-xs text-warning" data-testid="a-confirmer">
      <li v-for="p in fiche.a_confirmer" :key="p">À confirmer : {{ p }}</li>
    </ul>

    <!-- Les éléments : tout ce qui influence le résultat, chacun avec sa source. Vide = une entrée (donnée de test). -->
    <div>
      <p class="font-medium">Éléments du calcul</p>
      <table class="mt-1 w-full text-xs">
        <thead><tr class="text-left text-muted-foreground">
          <th class="py-1 pr-2 font-normal">Nom</th><th class="py-1 pr-2 font-normal">Valeur fixe (vide = donnée de test)</th>
          <th class="py-1 pr-2 font-normal">Source</th><th class="py-1 pr-2 font-normal">Vérifié le</th><th></th>
        </tr></thead>
        <tbody>
          <tr v-for="(el, k) in fiche.elements" :key="k">
            <td class="py-0.5 pr-2"><input v-model="el.nom" :aria-label="`Nom de l'élément ${k + 1}`" class="w-32 rounded border border-border bg-surface-raised px-1.5 py-1 font-mono" /></td>
            <td class="py-0.5 pr-2"><input v-model="el.valeur" :aria-label="`Valeur de ${el.nom || 'l\'élément'}`" class="w-28 rounded border border-border bg-surface-raised px-1.5 py-1" /></td>
            <td class="py-0.5 pr-2"><input v-model="el.source" :aria-label="`Source de ${el.nom || 'l\'élément'}`" placeholder="d'où vient-il ?" class="w-full rounded border border-border bg-surface-raised px-1.5 py-1" /></td>
            <td class="py-0.5 pr-2"><input v-if="String(el.valeur ?? '').trim()" v-model="el.verifie_le" type="date" :aria-label="`Date de vérification de ${el.nom || 'l\'élément'}`" :data-testid="`verifie-le-${k}`" class="rounded border border-border bg-surface-raised px-1.5 py-1" /></td>
            <td class="py-0.5 text-right"><IconButton size="sm" variant="danger" label="Retirer l'élément" @click="fiche.elements.splice(k, 1)">✕</IconButton></td>
          </tr>
        </tbody>
      </table>
      <button type="button" class="mt-1 text-xs text-primary hover:underline" @click="ajouterElement">+ Ajouter un élément</button>
    </div>

    <!-- Les étapes : des opérations simples, dans l'ordre ; un terme est un élément, une étape précédente ou un nombre. -->
    <div>
      <p class="font-medium">Étapes du calcul</p>
      <div v-for="(e, k) in fiche.etapes" :key="k" class="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
        <input v-model="e.resultat" :aria-label="`Résultat de l'étape ${k + 1}`" placeholder="résultat" class="w-28 rounded border border-border bg-surface-raised px-1.5 py-1 font-mono" />
        <span>=</span>
        <select :value="e.operation" :aria-label="`Opération de l'étape ${k + 1}`" class="rounded border border-border bg-surface-raised px-1 py-1"
                @change="changerOperation(e, ($event.target as HTMLSelectElement).value)">
          <option v-for="o in OPERATIONS" :key="o.v" :value="o.v">{{ o.label }}</option>
        </select>
        <input v-if="A_TERMES.includes(e.operation)" :value="termesTexte(e)" placeholder="a, b" :aria-label="`Termes de l'étape ${k + 1}`"
               class="w-44 rounded border border-border bg-surface-raised px-1.5 py-1" @input="poserTermes(e, ($event.target as HTMLInputElement).value)" />
        <template v-else-if="e.operation === 'diviser'">
          <input v-model="e.valeur" placeholder="valeur" class="w-24 rounded border border-border bg-surface-raised px-1.5 py-1" /> ÷
          <input v-model="e.par" placeholder="par" class="w-24 rounded border border-border bg-surface-raised px-1.5 py-1" />
        </template>
        <template v-else-if="e.operation === 'pourcentage'">
          <input v-model="e.taux" placeholder="taux" class="w-24 rounded border border-border bg-surface-raised px-1.5 py-1" /> % de
          <input v-model="e.de" placeholder="valeur" class="w-24 rounded border border-border bg-surface-raised px-1.5 py-1" />
        </template>
        <template v-else-if="e.operation === 'arrondir'">
          <input v-model="e.valeur" placeholder="valeur" class="w-24 rounded border border-border bg-surface-raised px-1.5 py-1" /> à
          <input v-model.number="e.decimales" type="number" min="0" max="10" class="w-14 rounded border border-border bg-surface-raised px-1.5 py-1" /> décimale(s),
          <select v-model="e.mode" class="rounded border border-border bg-surface-raised px-1 py-1">
            <option value="" disabled>comment ?</option>
            <option v-for="m in MODES_ARRONDI" :key="m.v" :value="m.v">{{ m.label }}</option>
          </select>
        </template>
        <template v-else-if="e.operation === 'plafonner' || e.operation === 'plancher'">
          <input v-model="e.valeur" placeholder="valeur" class="w-24 rounded border border-border bg-surface-raised px-1.5 py-1" />,
          <input v-model="e.limite" placeholder="limite" class="w-24 rounded border border-border bg-surface-raised px-1.5 py-1" />
        </template>
        <template v-else-if="e.operation === 'bareme'">
          <input v-model="e.valeur" placeholder="montant" class="w-24 rounded border border-border bg-surface-raised px-1.5 py-1" />
          <select v-model="e.mode" class="rounded border border-border bg-surface-raised px-1 py-1">
            <option value="" disabled>lecture ?</option>
            <option value="progressif">progressif (chaque tranche à son taux)</option>
            <option value="par_palier">par palier (tout au taux de sa tranche)</option>
          </select>
          <span v-for="(t, j) in e.tranches" :key="j" class="flex items-center gap-1">
            jusqu'à <input v-model="t.jusqu_a" placeholder="sans limite" class="w-20 rounded border border-border bg-surface-raised px-1 py-1" />
            : <input v-model="t.taux" placeholder="taux %" class="w-16 rounded border border-border bg-surface-raised px-1 py-1" />
          </span>
          <button type="button" class="text-primary hover:underline" @click="e.tranches!.push({ jusqu_a: '', taux: '' })">+ tranche</button>
        </template>
        <template v-else-if="e.operation === 'si' && e.condition">
          <input v-model="e.condition.gauche" class="w-20 rounded border border-border bg-surface-raised px-1 py-1" />
          <select v-model="e.condition.comparateur" class="rounded border border-border bg-surface-raised px-1 py-1">
            <option v-for="c in COMPARATEURS" :key="c" :value="c">{{ c }}</option>
          </select>
          <input v-model="e.condition.droite" class="w-20 rounded border border-border bg-surface-raised px-1 py-1" />
          alors <input v-model="e.alors" class="w-20 rounded border border-border bg-surface-raised px-1 py-1" />
          sinon <input v-model="e.sinon" class="w-20 rounded border border-border bg-surface-raised px-1 py-1" />
        </template>
        <IconButton size="sm" variant="danger" label="Retirer l'étape" @click="fiche.etapes.splice(k, 1)">✕</IconButton>
      </div>
      <button type="button" class="mt-1 text-xs text-primary hover:underline" @click="ajouterEtape">+ Ajouter une étape</button>
    </div>

    <!-- Les exemples à retrouver EXACTEMENT : un chiffre écrit dans la spécification en devient un. -->
    <div>
      <p class="font-medium">Exemples à retrouver</p>
      <div v-for="(ex, k) in fiche.exemples" :key="k" class="mt-1 flex flex-wrap items-center gap-1.5 text-xs" :data-testid="`exemple-${k}`">
        <label v-for="n in entrees" :key="n" class="flex items-center gap-1"><span class="font-mono">{{ n }}</span>
          <input v-model="ex.entrees[n]" :aria-label="`${n}, exemple ${k + 1}`" class="w-20 rounded border border-border bg-surface-raised px-1 py-1" /></label>
        <label class="flex items-center gap-1">→ attendu
          <input v-model="ex.attendu" :aria-label="`Résultat attendu, exemple ${k + 1}`" class="w-24 rounded border border-border bg-surface-raised px-1 py-1" /></label>
        <span v-if="verification?.exemples[k]" :class="verification.exemples[k].retrouve ? 'text-success' : 'text-destructive'"
              :data-testid="`exemple-${k}-verdict`">
          {{ verification.exemples[k].retrouve ? '✓ retrouvé' : `✗ le calcul donne ${verification.exemples[k].obtenu}` }}
        </span>
        <button v-if="verification?.exemples[k]?.detail.length" type="button" class="text-primary hover:underline"
                @click="detailOuvert = detailOuvert === k ? null : k">détail</button>
        <IconButton size="sm" variant="danger" label="Retirer l'exemple" @click="fiche.exemples.splice(k, 1)">✕</IconButton>
        <ol v-if="detailOuvert === k" class="basis-full list-decimal pl-6 text-muted-foreground">
          <li v-for="l in verification?.exemples[k]?.detail" :key="l">{{ l }}</li>
        </ol>
      </div>
      <button type="button" class="mt-1 text-xs text-primary hover:underline" @click="ajouterExemple">+ Ajouter un exemple</button>
    </div>

    <p v-if="erreurReseau" class="text-xs text-destructive">{{ erreurReseau }}</p>
    <p v-else-if="verification && !verification.utilisable" class="text-xs text-destructive" data-testid="fiche-a-corriger">
      {{ verification.erreur || 'Un exemple n\'est pas retrouvé : corrigez le calcul ou l\'exemple.' }}
    </p>
    <p v-else-if="verification?.utilisable" class="text-xs text-success" data-testid="fiche-utilisable">Fiche prête : tous les exemples sont retrouvés.</p>
  </div>
</template>
