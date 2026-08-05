<script setup lang="ts">
// « Ajouter un résultat » — le geste central de TestRail, repris à l'identique et adapté au
// thème sombre : on ouvre une campagne, on choisit un cas, on pose un statut et un commentaire.
//
// ── Ce qui est repris de TestRail ─────────────────────────────────────────────────────────────
//  • la saisie n'existe QUE dans une campagne (jamais sur un cas isolé) ;
//  • le statut est OBLIGATOIRE et sans valeur par défaut ;
//  • le commentaire est libre, et c'est lui qui porte le « pourquoi » ;
//  • le résultat s'AJOUTE à l'historique — rien n'est écrasé, rien n'est supprimé.
//
// ── Ce qui en diffère, et pourquoi ────────────────────────────────────────────────────────────
//  • **« Untested » n'est pas proposable.** TestRail l'affiche comme statut initial, mais on ne
//    le *saisit* pas : c'est l'absence de résultat. Une ligne « je constate que ce n'est pas
//    testé » n'affirmerait rien qu'un vide ne dise déjà mieux.
//  • Pas de « défauts liés », pas de « temps passé » : arbitrés hors V1. Un champ à moitié tenu
//    ment davantage qu'un champ absent.
//  • Le résultat sera étiqueté **« Manuelle »** partout. TestRail n'a pas besoin de cette
//    distinction — chez lui tout est joué à la main. Ici, la moitié des résultats vient d'une
//    machine, et c'est la seule chose qui empêche les deux de se confondre.
//
// ⚠️ **Cette fenêtre n'existe que dans une campagne MANUELLE** (2026-08-04) : le mode se choisit
// à la création de la campagne, et c'est lui qui décide du geste offert — lancer, ou saisir.
//
// ⚠️ **Les statuts sont ceux que le SERVEUR renvoie** (`statuts_manuels`), itérés tels
// quels. Les retaper ici ferait vivre la même liste à trois endroits — Python, `CHECK` SQL,
// TypeScript — et la divergence serait silencieuse.
import { computed, ref, watch } from 'vue'
import { api, type ResultOut } from '../lib/api'
import { testStatusMeta } from '../lib/status'
import Modal from './ui/Modal.vue'
import Button from './ui/Button.vue'
import ResultHistory from './ResultHistory.vue'

// ⚠️ Type STRUCTUREL, volontairement minimal : `RunDetail.vue` passe un `RunCaseResult` complet
// (statut, mode, axes…) et `RunTestDetail.vue` n'a que ces deux champs sur son objet « test ». Le
// template et `valider()` ne lisent jamais rien d'autre — élargir ici évite un `RunCaseResult`
// bricolé à partir de deux champs pour satisfaire un type qui en exige quinze.
interface CasMinimal { id: number; title: string }

const props = defineProps<{
  open: boolean
  runId: number
  cas: CasMinimal | null
  statuts: string[]
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'saved'): void }>()

const statut = ref('')
const commentaire = ref('')
const envoi = ref(false)
const erreur = ref('')
const historique = ref<ResultOut[]>([])
const chargement = ref(false)

// ── Pièce jointe (2026-08-05) — TOUJOURS optionnelle : un résultat s'enregistre sans elle. Le
// choix du fichier n'entre dans AUCUNE condition de validation (`peutValider` plus bas).
const fichiers = ref<File[]>([])
// Erreur de la pièce jointe, séparée de `erreur` (celle du résultat) : le résultat peut très bien
// être créé alors que l'upload échoue ensuite — les deux ne racontent pas le même échec.
const erreurPieces = ref('')

function fichiersChoisis(e: Event) {
  const input = e.target as HTMLInputElement
  fichiers.value = input.files ? Array.from(input.files) : []
}

// Rien n'est pré-sélectionné à l'ouverture : proposer « Passed » d'avance transformerait la
// saisie en un clic distrait — précisément ce qui vide le mot « testé » de son sens.
//
// ⚠️ `immediate: true` : sans lui, la fenêtre montée DÉJÀ ouverte n'aurait jamais chargé son
// historique — le watcher n'observe qu'un CHANGEMENT. Ça marche par chance depuis l'écran de
// campagne (qui passe de fermé à ouvert), et ça casse partout ailleurs.
watch(() => props.open, async (ouvert) => {
  if (!ouvert || !props.cas) return
  statut.value = ''
  commentaire.value = ''
  erreur.value = ''
  fichiers.value = []
  erreurPieces.value = ''
  chargement.value = true
  try {
    historique.value = await api.listResults(props.runId, props.cas.id)
  } catch {
    historique.value = []   // l'historique est un CONFORT : son échec ne doit pas bloquer la saisie
  } finally {
    chargement.value = false
  }
}, { immediate: true })

const peutValider = computed(() => !!statut.value && !envoi.value)

async function valider() {
  if (!props.cas || !statut.value) return
  envoi.value = true
  erreur.value = ''
  erreurPieces.value = ''
  try {
    const cree = await api.addResult(props.runId, props.cas.id, {
      statut: statut.value, comment: commentaire.value.trim(),
    })
    // ⚠️ Le résultat est déjà enregistré à ce stade : un échec de l'upload NE DOIT PAS le faire
    // disparaître de l'écran. On le dit à part, jamais en écrasant le succès qui précède.
    if (fichiers.value.length) {
      try {
        await api.addAttachments(cree.id, fichiers.value)
      } catch (e: any) {
        erreurPieces.value = e?.message || 'Le fichier n\'a pas pu être joint.'
        emit('saved')
        // Le résultat existe déjà : on ne rejoue PAS `addResult` si l'utilisateur clique encore.
        // Vider le statut désactive le bouton (`peutValider`) sans fermer la fenêtre — l'erreur
        // et l'historique mis à jour restent lisibles jusqu'à ce qu'il ferme lui-même.
        statut.value = ''
        historique.value = await api.listResults(props.runId, props.cas.id).catch(() => historique.value)
        return
      }
    }
    emit('saved')
    emit('close')
  } catch (e: any) {
    erreur.value = e?.message || 'Enregistrement impossible.'
  } finally {
    envoi.value = false
  }
}
</script>

<template>
  <Modal :open="open" max-width="max-w-2xl"
         :title="'Ajouter un résultat'"
         :subtitle="cas ? `C${cas.id} · ${cas.title}` : ''"
         @close="emit('close')">
    <div class="space-y-5">
      <!-- ── STATUT ── obligatoire, sans défaut. Des boutons plutôt qu'une liste déroulante :
           les quatre choix tiennent sur une ligne, et un statut se pose d'un geste. Couleur ET
           mot ET état sélectionné visible — jamais la couleur seule (invariant 4.7). -->
      <div>
        <label class="text-sm font-medium">
          Statut <span class="text-destructive">*</span>
        </label>
        <div class="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <button v-for="code in statuts" :key="code" type="button"
                  class="flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors"
                  :class="statut === code
                    ? 'border-primary bg-primary/10 text-foreground'
                    : 'border-border bg-surface-raised text-muted-foreground hover:text-foreground hover:bg-accent/50'"
                  :aria-pressed="statut === code"
                  @click="statut = code">
            <!-- ⚠️ `.color` rend des composantes HSL BRUTES ("152 56% 46%"), jamais une couleur
                 CSS utilisable telle quelle — il faut l'envelopper dans `hsl(...)`. Oublié ici,
                 la pastille était invisible (fond transparent) ; corrigé partout ailleurs
                 (RunDetail.vue, CourbeResultats.vue), pas ici. -->
            <span class="h-2.5 w-2.5 shrink-0 rounded-full"
                  :style="{ background: `hsl(${testStatusMeta(code).color})` }"></span>
            {{ testStatusMeta(code).label }}
          </button>
        </div>
        <!-- ⚠️ Dire POURQUOI « Untested » manque évite qu'on le cherche : sans cette phrase,
             l'absence passe pour un oubli de l'outil. -->
        <p class="mt-2 text-[11px] text-muted-foreground">
          « Untested » ne se saisit pas : c'est l'absence de résultat, pas un choix.
        </p>
      </div>

      <!-- ── COMMENTAIRE ── libre. C'est ici que se dit ce qu'aucun statut ne peut porter :
           quelle étape a lâché, ce qui a été observé, pourquoi c'est bloqué. -->
      <div>
        <label class="text-sm font-medium">Commentaire</label>
        <textarea v-model="commentaire" rows="4"
                  placeholder="Ce qui a été observé, l'étape qui a échoué, la raison du blocage…"
                  class="mt-2 w-full rounded-md border border-border bg-surface-raised px-3 py-2 text-sm outline-none focus:border-primary"></textarea>
      </div>

      <!-- ── PIÈCE JOINTE ── TOUJOURS optionnelle. La preuve visuelle qu'un test manuel a
           réellement eu lieu — jamais une condition pour enregistrer le résultat. `accept` est
           indicatif seulement : le vrai refus (liste blanche, taille) vient du serveur. -->
      <div>
        <label class="text-sm font-medium">Pièce jointe</label>
        <input type="file" multiple
               accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.log,.csv,.zip"
               class="mt-2 block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-surface-raised file:px-3 file:py-1.5 file:text-sm file:text-foreground hover:file:bg-accent/50"
               @change="fichiersChoisis" />
        <p v-if="fichiers.length" class="mt-1.5 text-[11px] text-muted-foreground">
          {{ fichiers.length }} fichier(s) sélectionné(s) : {{ fichiers.map((f) => f.name).join(', ') }}
        </p>
      </div>

      <!-- L'avertissement d'honnêteté. Il n'est pas décoratif : c'est le contrat que l'outil
           passe avec celui qui lit le rapport ensuite. -->
      <p class="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
        Ce résultat sera enregistré comme joué <strong>manuellement</strong> : aucune machine ne
        l'aura vérifié. Il restera distinct des résultats automatiques partout où il s'affiche.
      </p>

      <p v-if="erreur" class="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
        {{ erreur }}
      </p>
      <!-- Distincte de `erreur` : le résultat est déjà enregistré quand celle-ci apparaît. La
           confondre avec `erreur` laisserait croire que rien n'a été sauvegardé. -->
      <p v-if="erreurPieces" class="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning">
        Résultat enregistré, mais la pièce jointe n'a pas pu être jointe : {{ erreurPieces }}
      </p>

      <div class="border-t border-border pt-4">
        <ResultHistory :results="historique" :loading="chargement" />
      </div>
    </div>

    <template #footer>
      <Button variant="ghost" :disabled="envoi" @click="emit('close')">Annuler</Button>
      <Button variant="primary" :loading="envoi" :disabled="!peutValider" @click="valider">
        Ajouter le résultat
      </Button>
    </template>
  </Modal>
</template>
