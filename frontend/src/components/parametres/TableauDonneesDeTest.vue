<script setup lang="ts">
// « Données de test » (lot PT-02a, décisions A26 à A31) — le TABLEAU d'un projet : une ligne par variable, une colonne par
// jeu de données, comme dans TestRail. Un test écrit la variable entre doubles accolades ; au lancement on choisit une ou
// plusieurs colonnes, et l'outil pose les valeurs dans le test.
//
// - La colonne « Par défaut » vient en tête ; une case laissée vide dans une autre colonne en reprend la valeur (A27) :
//   elle est montrée en gris dans la case, pour que l'héritage se voie.
// - Ajouter et modifier : testeurs et plus (`peutModifier`). Supprimer — une mise à la corbeille, restaurable — :
//   l'administrateur du projet (`peutSupprimer`). Avant de supprimer une variable, l'écran montre les tests qui l'utilisent.
// - Le serveur valide chaque nom et chaque valeur avec les règles du remplacement ; son refus est montré tel quel.
import { computed, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { api, type DonneesDeTest, type ImportDonnees, type JeuDeDonnees, type ProjectSummary, type VariableDeTest } from '../../lib/api'
import Button from '../ui/Button.vue'
import Modal from '../ui/Modal.vue'
import ConfirmDialog from '../ConfirmDialog.vue'

const props = defineProps<{ projet: ProjectSummary; peutModifier: boolean; peutSupprimer: boolean }>()
const emit = defineEmits<{ (e: 'modifie', valeur: boolean): void }>()

const tableau = ref<DonneesDeTest>({ variables: [], jeux: [] })
const chargement = ref(true)
const erreur = ref('')
const enregistrement = ref(false)
const enregistreA = ref(false)
// La saisie en cours : `saisie[id du jeu][id de la variable]` — repartie du serveur à chaque chargement.
const saisie = reactive<Record<string, Record<string, string>>>({})

const ecrite = (nom: string) => `{{${nom}}}`   // jamais écrit en dur dans le gabarit : Vue y lirait une expression
const jeuParDefaut = computed(() => tableau.value.jeux.find((j) => j.est_defaut) || null)

function reprendre(t: DonneesDeTest) {
  tableau.value = t
  for (const cle of Object.keys(saisie)) delete saisie[cle]
  for (const jeu of t.jeux) {
    saisie[jeu.id] = {}
    for (const v of t.variables) saisie[jeu.id][v.id] = jeu.valeurs[String(v.id)] ?? ''
  }
}

// Les cases dont la saisie diffère de ce que le serveur a enregistré, par jeu.
const modifications = computed(() => {
  const parJeu: Record<string, Record<string, string>> = {}
  for (const jeu of tableau.value.jeux) {
    for (const v of tableau.value.variables) {
      const tapee = (saisie[jeu.id]?.[v.id] ?? '').trim()
      if (tapee !== (jeu.valeurs[String(v.id)] ?? '')) (parJeu[jeu.id] ||= {})[String(v.id)] = tapee
    }
  }
  return parJeu
})
const modifie = computed(() => Object.keys(modifications.value).length > 0)
watch(modifie, (v) => emit('modifie', v), { immediate: true })

async function charger() {
  chargement.value = true
  erreur.value = ''
  try {
    reprendre(await api.getTestData(props.projet.id))
  } catch (e: any) {
    erreur.value = e?.message || 'Les données de test n\'ont pas pu être chargées.'
  } finally {
    chargement.value = false
  }
}
onMounted(charger)
watch(() => props.projet.id, charger)

async function enregistrer() {
  if (!props.peutModifier || !modifie.value) return
  enregistrement.value = true
  erreur.value = ''
  enregistreA.value = false
  try {
    // Jeu par jeu : chaque réponse devient la référence AVANT le jeu suivant — si l'un est refusé, ceux déjà enregistrés ne
    // s'affichent plus comme modifiés, et la saisie refusée reste à l'écran.
    for (const [jeuId, valeurs] of Object.entries(modifications.value)) {
      tableau.value = await api.setDatasetValues(props.projet.id, Number(jeuId), valeurs)
    }
    reprendre(tableau.value)
    enregistreA.value = true
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrement.value = false
  }
}

// ── Ajouter une variable ──────────────────────────────────────────────────────────────────────────────────────────────
const nouvelleVariable = ref('')
const ajoutVariable = ref(false)
async function ajouterVariable() {
  const nom = nouvelleVariable.value.trim()
  if (!props.peutModifier || !nom || modifie.value) return
  ajoutVariable.value = true
  erreur.value = ''
  try {
    reprendre(await api.createTestVariable(props.projet.id, { nom }))
    nouvelleVariable.value = ''
  } catch (e: any) {
    erreur.value = e?.message || 'Ajout impossible.'
  } finally {
    ajoutVariable.value = false
  }
}

// ── Ajouter ou renommer un jeu ────────────────────────────────────────────────────────────────────────────────────────
// `null` = fenêtre fermée ; 'nouveau' = ajout ; un nombre = le jeu à renommer.
const jeuEnCours = ref<number | 'nouveau' | null>(null)
const nomDuJeu = ref('')
const erreurJeu = ref('')
const enregistrementJeu = ref(false)
function ouvrirJeu(jeu?: JeuDeDonnees) {
  nomDuJeu.value = jeu?.nom || ''
  erreurJeu.value = ''
  jeuEnCours.value = jeu ? jeu.id : 'nouveau'
}
async function enregistrerJeu() {
  if (!props.peutModifier || jeuEnCours.value === null || !nomDuJeu.value.trim()) return
  enregistrementJeu.value = true
  erreurJeu.value = ''
  try {
    const t = jeuEnCours.value === 'nouveau'
      ? await api.createTestDataset(props.projet.id, { nom: nomDuJeu.value.trim() })
      : await api.renameTestDataset(props.projet.id, jeuEnCours.value, { nom: nomDuJeu.value.trim() })
    reprendre(t)
    jeuEnCours.value = null
  } catch (e: any) {
    erreurJeu.value = e?.message || 'Enregistrement impossible.'
  } finally {
    enregistrementJeu.value = false
  }
}

// ── Supprimer (corbeille) ─────────────────────────────────────────────────────────────────────────────────────────────
type ASupprimer = { genre: 'variable' | 'jeu'; id: number; titre: string; message: string }
const aSupprimer = ref<ASupprimer | null>(null)
const suppression = ref(false)
async function demanderSuppressionVariable(v: VariableDeTest) {
  erreur.value = ''
  try {
    const usages = await api.testVariableUsages(props.projet.id, v.id)
    const noms = usages.slice(0, 3).map((u) => `« ${u.title} »`).join(', ')
    const message = usages.length
      ? `Utilisée par ${usages.length} test${usages.length > 1 ? 's' : ''} : ${noms}${usages.length > 3 ? '…' : ''}. `
        + `${usages.length > 1 ? 'Ils sortiront' : 'Il sortira'} « bloqué » tant qu'elle sera à la corbeille.`
      : 'Aucun test ne l\'utilise. Elle ira à la corbeille.'
    aSupprimer.value = { genre: 'variable', id: v.id, titre: `Supprimer ${ecrite(v.nom)} ?`, message }
  } catch (e: any) {
    erreur.value = e?.message || 'Les tests concernés n\'ont pas pu être listés.'
  }
}
function demanderSuppressionJeu(jeu: JeuDeDonnees) {
  aSupprimer.value = { genre: 'jeu', id: jeu.id, titre: `Supprimer « ${jeu.nom} » ?`, message: 'Le jeu de données ira à la corbeille.' }
}
async function supprimer() {
  const cible = aSupprimer.value
  if (!cible) return
  suppression.value = true
  try {
    if (cible.genre === 'variable') await api.deleteTestVariable(props.projet.id, cible.id)
    else await api.deleteTestDataset(props.projet.id, cible.id)
    aSupprimer.value = null
    await charger()
  } catch (e: any) {
    erreur.value = e?.message || 'Suppression impossible.'
    aSupprimer.value = null
  } finally {
    suppression.value = false
  }
}

// ── Excel (A37) : « Exporter » donne le tableau (et le modèle) ; « Importer » COMPLÈTE le tableau, après un aperçu ─────────
const fichierImport = ref<HTMLInputElement | null>(null)
// `shallowRef` : un `File` ne se rend pas réactif en profondeur.
const aImporter = shallowRef<{ fichier: File; apercu: ImportDonnees } | null>(null)
const importEnCours = ref(false)
const rienAChanger = computed(() => !!aImporter.value && !aImporter.value.apercu.nouvelles_variables.length
  && !aImporter.value.apercu.nouveaux_jeux.length && !aImporter.value.apercu.cases.length)
async function fichierChoisi(e: Event) {
  const input = e.target as HTMLInputElement
  const fichier = input.files?.[0]
  input.value = ''   // le même fichier, choisi de nouveau, doit relancer l'aperçu
  if (!fichier) return
  erreur.value = ''
  try {
    aImporter.value = { fichier, apercu: await api.previewTestDataImport(props.projet.id, fichier) }
  } catch (err: any) {
    erreur.value = err?.message || 'Fichier illisible.'
  }
}
async function importer() {
  const demande = aImporter.value
  if (!demande || demande.apercu.erreurs.length) return
  importEnCours.value = true
  try {
    reprendre(await api.importTestData(props.projet.id, demande.fichier))
    aImporter.value = null
    enregistreA.value = true
  } catch (err: any) {
    aImporter.value = { fichier: demande.fichier, apercu: { ...demande.apercu, erreurs: [err?.message || 'Import impossible.'] } }
  } finally {
    importEnCours.value = false
  }
}
</script>

<template>
  <section class="rounded-xl border border-border bg-surface-raised shadow-sm" data-testid="donnees-de-test">
    <p v-if="erreur" role="alert" class="m-4 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive" data-testid="donnees-erreur">{{ erreur }}</p>
    <p v-if="chargement" class="p-4 text-sm text-muted-foreground" aria-live="polite">Chargement…</p>

    <!-- `relative` : sans lui, un libellé masqué (`sr-only`, positionné en absolu) échappe au défilement et élargit toute la page. -->
    <div v-else class="relative overflow-x-auto">
      <!-- A54 (2026-10-16) : comme le « Data Table » de QTP/UFT et Excel — les variables en colonnes, UNE LIGNE par jeu de
           valeurs (une itération au lancement). Le jeu « Par défaut » reste la première ligne ; une case vide en reprend la
           valeur (A27), montrée en gris. -->
      <table v-if="tableau.variables.length" class="w-full text-sm" data-testid="tableau-donnees">
        <thead>
          <tr class="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
            <th scope="col" class="px-4 py-3 font-medium sm:px-6">Ligne</th>
            <th v-for="v in tableau.variables" :key="v.id" scope="col" class="min-w-44 px-3 py-3 font-medium" data-testid="variable">
              <span class="flex items-center justify-between gap-2">
                <span class="font-mono normal-case tracking-normal text-foreground">{{ ecrite(v.nom) }}</span>
                <Button v-if="peutSupprimer" type="button" variant="ghost" size="sm" class="shrink-0 normal-case tracking-normal text-destructive"
                        :aria-label="`Supprimer la variable ${v.nom}`" @click="demanderSuppressionVariable(v)">Supprimer</Button>
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(jeu, i) in tableau.jeux" :key="jeu.id" class="border-b border-border last:border-0" :data-testid="`jeu-${jeu.id}`">
            <th scope="row" class="whitespace-nowrap px-4 py-2 text-left font-medium sm:px-6">
              <span class="flex items-center gap-2">
                <span class="w-5 text-right text-xs font-normal tabular-nums text-muted-foreground" :data-testid="`numero-${jeu.id}`">{{ i + 1 }}</span>
                <span>{{ jeu.nom }}</span>
                <span v-if="!jeu.est_defaut" class="flex shrink-0 gap-1">
                  <Button v-if="peutModifier" type="button" variant="ghost" size="sm" :aria-label="`Renommer ${jeu.nom}`" @click="ouvrirJeu(jeu)">Renommer</Button>
                  <Button v-if="peutSupprimer" type="button" variant="ghost" size="sm" class="text-destructive" :aria-label="`Supprimer ${jeu.nom}`" @click="demanderSuppressionJeu(jeu)">Supprimer</Button>
                </span>
              </span>
            </th>
            <td v-for="v in tableau.variables" :key="v.id" class="px-3 py-2">
              <input v-model="saisie[jeu.id][v.id]" :disabled="!peutModifier" :data-testid="`case-${jeu.id}-${v.id}`"
                     :aria-label="`${v.nom} pour ${jeu.nom}`"
                     :placeholder="jeu.est_defaut ? '' : (jeuParDefaut ? saisie[jeuParDefaut.id]?.[v.id] || '' : '')"
                     class="h-10 w-full rounded-md border border-border bg-surface px-3 outline-none placeholder:text-muted-foreground/70 focus:border-primary disabled:cursor-not-allowed disabled:opacity-60" />
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="px-4 py-6 text-sm text-muted-foreground sm:px-6" data-testid="aucune-variable">Aucune variable</p>
    </div>

    <div v-if="!chargement" class="flex flex-wrap items-center gap-3 border-t border-border bg-surface px-4 py-4 sm:px-6">
      <form v-if="peutModifier" class="flex min-w-0 flex-wrap items-center gap-2" data-testid="form-variable" @submit.prevent="ajouterVariable">
        <label class="sr-only" for="nouvelle-variable">Nouvelle variable</label>
        <input id="nouvelle-variable" v-model="nouvelleVariable" placeholder="nom_de_variable" maxlength="40" data-testid="nouvelle-variable"
               class="h-10 w-full min-w-0 rounded-md border border-border bg-surface px-3 font-mono text-sm outline-none focus:border-primary sm:w-48" />
        <Button type="submit" variant="secondary" class="whitespace-nowrap" data-testid="variable-ajouter" :loading="ajoutVariable" :disabled="!nouvelleVariable.trim() || modifie">Ajouter une variable</Button>
      </form>
      <Button v-if="peutModifier && tableau.variables.length" type="button" variant="secondary" data-testid="jeu-ajouter" :disabled="modifie" @click="ouvrirJeu()">Ajouter une ligne</Button>
      <a :href="api.exportTestDataUrl(projet.id)" download class="text-sm text-primary hover:underline" data-testid="donnees-exporter">Exporter</a>
      <template v-if="peutModifier">
        <input ref="fichierImport" type="file" accept=".xlsx" class="sr-only" data-testid="donnees-fichier" @change="fichierChoisi" />
        <button type="button" class="text-sm text-primary hover:underline disabled:opacity-50" data-testid="donnees-importer"
                :disabled="modifie" @click="fichierImport?.click()">Importer</button>
      </template>
      <span v-if="enregistreA && !modifie" role="status" class="ml-auto text-sm text-success" data-testid="enregistre">Enregistré</span>
      <span v-else class="ml-auto" />
      <Button v-if="peutModifier" type="button" variant="secondary" :disabled="!modifie || enregistrement" @click="reprendre(tableau)">Annuler</Button>
      <Button v-if="peutModifier" type="button" variant="primary" data-testid="donnees-enregistrer" :loading="enregistrement" :disabled="!modifie" @click="enregistrer">Enregistrer</Button>
    </div>

    <Modal :open="jeuEnCours !== null" :title="jeuEnCours === 'nouveau' ? 'Ajouter un jeu de données' : 'Renommer le jeu de données'" @close="jeuEnCours = null">
      <form id="form-jeu" data-testid="jeu-formulaire" @submit.prevent="enregistrerJeu">
        <label class="block"><span class="text-sm font-medium">Nom <span class="text-destructive" aria-hidden="true">*</span></span>
          <input v-model="nomDuJeu" required maxlength="60" placeholder="Grosse commande" data-testid="jeu-nom"
                 class="mt-1.5 h-11 w-full rounded-md border border-border bg-surface px-3 outline-none focus:border-primary" /></label>
        <p v-if="erreurJeu" role="alert" class="mt-3 text-sm text-destructive">{{ erreurJeu }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="jeuEnCours = null">Annuler</Button>
        <Button type="submit" form="form-jeu" variant="primary" data-testid="jeu-enregistrer" :loading="enregistrementJeu" :disabled="!nomDuJeu.trim()">Enregistrer</Button>
      </template>
    </Modal>

    <!-- A37 : ce que l'import ajoute et change, AVANT d'enregistrer ; une erreur dans le fichier, et rien n'est importé. -->
    <Modal :open="aImporter !== null" title="Importer" :subtitle="aImporter?.fichier.name" @close="aImporter = null">
      <div v-if="aImporter" class="space-y-3 text-sm" data-testid="import-apercu">
        <ul v-if="aImporter.apercu.erreurs.length" class="space-y-1 text-destructive" role="alert" data-testid="import-erreurs">
          <li v-for="e in aImporter.apercu.erreurs" :key="e">{{ e }}</li>
        </ul>
        <template v-else>
          <p v-if="rienAChanger" class="text-muted-foreground">Aucun changement</p>
          <p v-if="aImporter.apercu.nouvelles_variables.length">
            <span class="text-muted-foreground">Variables ajoutées :</span>
            <span class="ml-1 font-mono">{{ aImporter.apercu.nouvelles_variables.map(ecrite).join(', ') }}</span>
          </p>
          <p v-if="aImporter.apercu.nouveaux_jeux.length">
            <span class="text-muted-foreground">Jeux ajoutés :</span> {{ aImporter.apercu.nouveaux_jeux.join(', ') }}
          </p>
          <table v-if="aImporter.apercu.cases.length" class="w-full text-xs" data-testid="import-cases">
            <tbody>
              <tr v-for="c in aImporter.apercu.cases" :key="`${c.variable}|${c.jeu}`" class="border-b border-border last:border-0">
                <th scope="row" class="py-1.5 pr-3 text-left font-mono font-normal">{{ ecrite(c.variable) }}</th>
                <td class="py-1.5 pr-3 text-muted-foreground">{{ c.jeu }}</td>
                <td class="py-1.5 break-all"><span v-if="c.avant" class="text-muted-foreground line-through">{{ c.avant }}</span> {{ c.apres }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>
      <template #footer>
        <Button type="button" variant="secondary" @click="aImporter = null">Annuler</Button>
        <Button type="button" variant="primary" data-testid="import-confirmer" :loading="importEnCours"
                :disabled="!!aImporter?.apercu.erreurs.length || rienAChanger" @click="importer">Importer</Button>
      </template>
    </Modal>

    <ConfirmDialog :open="aSupprimer !== null" :title="aSupprimer?.titre || ''" :message="aSupprimer?.message || ''"
                   confirm-label="Supprimer" :busy="suppression" @confirm="supprimer" @cancel="aSupprimer = null" />
  </section>
</template>
