<script setup lang="ts">
// Import de cas de test depuis un cahier de test Excel existant (2026-10-01) — le porteur a été
// explicite : « je n'aurai pas toujours des excels propres à charger ». Deux écrans, jamais un
// aveugle : `preview` (api.previewExcelImport) ne touche JAMAIS la base, seul `confirm` écrit —
// avec le mapping éventuellement CORRIGÉ ici, pas celui deviné automatiquement. Même esprit que
// la relecture « métier » déjà en place pour la génération IA (AddTestCase.vue).
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, type ExcelImportLigne, type ExcelImportPreview, type ModuleSummary } from '../lib/api'
import { useGroupes } from '../lib/donnees'
import { testStatusView } from '../lib/status'
import Button from '../components/ui/Button.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)

const CHAMPS_CIBLES = [
  { v: '', label: '(ignorée)' },
  { v: 'identifiant', label: 'Identifiant' },
  { v: 'titre', label: 'Titre' },
  { v: 'preconditions', label: 'Préconditions' },
  { v: 'etapes', label: 'Étapes' },
  { v: 'resultat_attendu', label: 'Résultat attendu' },
  { v: 'section', label: 'Section (User Story)' },
  { v: 'priorite', label: 'Priorité' },
  { v: 'statut', label: 'Statut' },
  { v: 'testeur', label: 'Testeur' },
  { v: 'date', label: 'Date' },
  { v: 'type', label: 'Type' },
  { v: 'commentaires', label: 'Commentaires' },
]

// ── Module/section cible, même patron que AddManualCase.vue ────────────────────────────────
const modules = ref<ModuleSummary[]>([])
const moduleId = ref<number | null>(null)
const sectionParDefautId = ref<number | null>(null)
const { data: groupesData } = useGroupes(pid)
const sectionsDuModule = computed(() => {
  if (moduleId.value == null) return []
  return (groupesData.value ?? []).filter((g) => g.module_id === moduleId.value)
})

onMounted(async () => {
  modules.value = await api.listModules(pid.value)
  const wanted = Number(route.query.module)
  moduleId.value = modules.value.find((m) => m.id === wanted)?.id ?? modules.value[0]?.id ?? null
})
watch(moduleId, () => { sectionParDefautId.value = null })

// ── Étape 1 : téléversement ──────────────────────────────────────────────────────────────────
const fichier = ref<File | null>(null)
const chargementApercu = ref(false)
const erreur = ref('')
const apercu = ref<ExcelImportPreview | null>(null)
// Copie ÉDITABLE du mapping détecté — jamais celui d'origine modifié en place, pour pouvoir
// comparer « deviné » vs « corrigé » si besoin plus tard.
const mappingEdite = ref<Record<string, string>>({})
// Case à cocher par ligne (numero_ligne -> retenue) — initialisée depuis `ligne.retenue` détecté,
// mais l'utilisateur peut tout changer avant de confirmer.
const retenues = ref<Record<number, boolean>>({})

function onFichierChange(e: Event) {
  const input = e.target as HTMLInputElement
  fichier.value = input.files?.[0] ?? null
}

async function chargerApercu() {
  if (!fichier.value) return
  chargementApercu.value = true
  erreur.value = ''
  apercu.value = null
  try {
    const p = await api.previewExcelImport(moduleId.value!, fichier.value)
    apercu.value = p
    // Une colonne sans synonyme reconnu n'a pas d'entrée dans `p.mapping` — on l'initialise quand
    // même à '' (ignorée) pour que CHAQUE colonne de `entetes_brutes` ait un <select>, y compris
    // celles qu'aucun synonyme n'a devinées (sinon invisible = impossible à corriger à la main).
    mappingEdite.value = Object.fromEntries(
      Object.keys(p.entetes_brutes).map((col) => [col, p.mapping[col] ?? '']))
    retenues.value = Object.fromEntries(p.lignes.map((l) => [l.numero_ligne, l.retenue]))
  } catch (e: any) {
    erreur.value = e?.message || "Lecture du fichier impossible."
  } finally {
    chargementApercu.value = false
  }
}

// ── Étape 2 : aperçu / correction ────────────────────────────────────────────────────────────
const lignesRetenuesCount = computed(() =>
  Object.values(retenues.value).filter(Boolean).length)

function basculerLigne(l: ExcelImportLigne) {
  retenues.value[l.numero_ligne] = !retenues.value[l.numero_ligne]
}

const confirmation = ref<{ cree: number; ignore: number; run_id: number | null } | null>(null)
const confirmantImport = ref(false)

async function confirmerImport() {
  if (!apercu.value || moduleId.value == null) return
  confirmantImport.value = true
  erreur.value = ''
  try {
    const numeros = Object.entries(retenues.value).filter(([, v]) => v).map(([k]) => Number(k))
    const resume = await api.confirmExcelImport(moduleId.value, {
      fichier_hash: apercu.value.fichier_hash, feuille: apercu.value.feuille,
      ligne_entete: apercu.value.ligne_entete, mapping: mappingEdite.value,
      numeros_lignes_retenues: numeros,
      group_id: sectionParDefautId.value ?? undefined,
    })
    confirmation.value = resume
  } catch (e: any) {
    erreur.value = e?.message || "Import impossible."
  } finally {
    confirmantImport.value = false
  }
}

function recommencer() {
  apercu.value = null
  fichier.value = null
  confirmation.value = null
  erreur.value = ''
}

function terminer() {
  router.push({ name: 'cases', params: { pid: pid.value } })
}
</script>

<template>
  <div class="max-w-[900px]">
    <h1 class="text-2xl font-semibold tracking-tight">Importer depuis Excel</h1>
    <p class="mt-1 text-sm text-muted-foreground">
      Chargez un cahier de test existant (<code>.xlsx</code>). Rien n'est écrit tant que vous
      n'avez pas vérifié et confirmé l'aperçu ci-dessous.
    </p>

    <!-- ── Résumé final ──────────────────────────────────────────────────────────────────── -->
    <div v-if="confirmation" class="mt-6 rounded-lg border border-success/40 bg-success/5 p-4">
      <p class="font-medium text-foreground">
        {{ confirmation.cree }} cas créé{{ confirmation.cree > 1 ? 's' : '' }}
        <span v-if="confirmation.ignore"> — {{ confirmation.ignore }} ligne{{ confirmation.ignore > 1 ? 's' : '' }} ignorée{{ confirmation.ignore > 1 ? 's' : '' }}</span>.
      </p>
      <p v-if="confirmation.run_id" class="mt-1 text-sm text-muted-foreground">
        Les résultats déclarés dans le fichier ont été enregistrés dans une campagne manuelle
        dédiée (visible dans « Exécutions et résultats de test »).
      </p>
      <Button class="mt-3" variant="primary" @click="terminer">Voir les cas</Button>
    </div>

    <!-- ── Étape 1 : téléversement ───────────────────────────────────────────────────────── -->
    <template v-else-if="!apercu">
      <div class="mt-6 space-y-5">
        <label class="block">
          <span class="text-sm font-medium">Module cible <span class="text-destructive">*</span></span>
          <select v-if="modules.length" v-model="moduleId"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2">
            <option v-for="m in modules" :key="m.id" :value="m.id">{{ m.name }}</option>
          </select>
          <p v-else class="mt-1 text-xs text-muted-foreground">
            Créez d'abord un module (bouton « Nouveau module »).
          </p>
        </label>

        <label class="block">
          <span class="text-sm font-medium">Section par défaut</span>
          <select v-model="sectionParDefautId"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-3 py-2">
            <option :value="null">Aucune — déduite de la colonne « User Story », ou créée au besoin</option>
            <option v-for="g in sectionsDuModule" :key="g.id" :value="g.id">{{ g.title }}</option>
          </select>
          <p class="mt-1 text-xs text-muted-foreground">
            Utilisée seulement pour les lignes sans section détectée dans le fichier.
          </p>
        </label>

        <label class="block">
          <span class="text-sm font-medium">Fichier Excel <span class="text-destructive">*</span></span>
          <input type="file" accept=".xlsx" @change="onFichierChange"
                 class="mt-1 block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-surface-raised file:px-3 file:py-1.5 file:text-sm file:font-medium" />
        </label>

        <p v-if="erreur" class="text-sm text-destructive">{{ erreur }}</p>

        <Button variant="primary" :loading="chargementApercu"
                :disabled="!fichier || moduleId == null || chargementApercu"
                @click="chargerApercu">
          {{ chargementApercu ? 'Lecture…' : "Analyser le fichier" }}
        </Button>
      </div>
    </template>

    <!-- ── Étape 2 : aperçu / correction ─────────────────────────────────────────────────── -->
    <template v-else>
      <div class="mt-6 rounded-lg border border-border bg-surface-raised/50 p-3 text-sm">
        Feuille détectée : <strong>{{ apercu.feuille }}</strong>
        <span v-if="apercu.feuilles_disponibles.length > 1"> (parmi {{ apercu.feuilles_disponibles.join(', ') }})</span>
        — entête en ligne <strong>{{ apercu.ligne_entete }}</strong>,
        {{ apercu.lignes.length }} ligne{{ apercu.lignes.length > 1 ? 's' : '' }} détectée{{ apercu.lignes.length > 1 ? 's' : '' }}.
      </div>

      <!-- Correction du mapping — le filet de sécurité pour un fichier pas propre. TOUTES les
           colonnes de l'entête sont listées ici, y compris celles qu'aucun synonyme n'a reconnues
           (affichées « (ignorée) ») : sinon une colonne jamais devinée resterait invisible, donc
           impossible à rattacher à un champ à la main. -->
      <div class="mt-4">
        <h2 class="text-sm font-semibold">Colonnes détectées</h2>
        <div class="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2">
          <label v-for="(libelle, col) in apercu.entetes_brutes" :key="col" class="block">
            <span class="text-xs text-muted-foreground">Colonne {{ col }} — « {{ libelle }} »</span>
            <select v-model="mappingEdite[col]"
                    class="mt-0.5 w-full rounded-md bg-surface-raised border border-border px-2 py-1 text-sm">
              <option v-for="c in CHAMPS_CIBLES" :key="c.v" :value="c.v">{{ c.label }}</option>
            </select>
          </label>
        </div>
      </div>

      <!-- Lignes candidates -->
      <div class="mt-5">
        <h2 class="text-sm font-semibold">
          Cas détectés — {{ lignesRetenuesCount }} retenu{{ lignesRetenuesCount > 1 ? 's' : '' }} sur {{ apercu.lignes.length }}
        </h2>
        <div class="mt-2 space-y-2 max-h-[480px] overflow-y-auto">
          <div v-for="l in apercu.lignes" :key="l.numero_ligne"
               class="rounded-lg border border-border p-3"
               :class="retenues[l.numero_ligne] ? 'bg-surface-raised' : 'bg-surface-raised/40 opacity-60'">
            <div class="flex items-start gap-3">
              <input type="checkbox" class="mt-1" :checked="retenues[l.numero_ligne]"
                     @change="basculerLigne(l)" />
              <div class="min-w-0 flex-1">
                <p class="font-medium truncate">{{ l.titre }}</p>
                <p class="text-xs text-muted-foreground">
                  Ligne {{ l.numero_ligne }}
                  <span v-if="l.section"> · {{ l.section }}</span>
                  <span v-if="l.priority"> · {{ l.priority }}</span>
                  <span v-if="l.statut_manuel"> · déclaré « {{ testStatusView(l.statut_manuel).label }} »</span>
                </p>
                <p v-if="l.test_steps.length" class="mt-1 text-xs text-muted-foreground">
                  {{ l.test_steps.length }} étape{{ l.test_steps.length > 1 ? 's' : '' }}
                </p>
                <p v-for="(a, i) in l.avertissements" :key="i"
                   class="mt-1 text-xs text-warning">⚠ {{ a }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p v-if="erreur" class="mt-3 text-sm text-destructive">{{ erreur }}</p>

      <div class="mt-5 flex items-center gap-3">
        <Button variant="primary" :loading="confirmantImport"
                :disabled="lignesRetenuesCount === 0 || confirmantImport"
                @click="confirmerImport">
          {{ confirmantImport ? 'Import…' : `Confirmer l'import (${lignesRetenuesCount})` }}
        </Button>
        <Button variant="secondary" @click="recommencer">Recommencer</Button>
      </div>
    </template>
  </div>
</template>
