<script setup lang="ts">
// L'HISTORIQUE des résultats d'un cas dans une campagne — le « Results » de TestRail.
//
// ⚠️ **Pourquoi cette liste existe, et pourquoi elle ne se purge pas.** Corriger un résultat,
// c'est en AJOUTER un nouveau ; l'ancien reste. Sans cette liste, cette règle serait invisible et
// une correction ressemblerait à une réécriture du passé. C'est la même discipline que la
// suppression douce : on masque, on ne détruit pas.
//
// Chaque entrée dit trois choses, dans cet ordre : **comment** le résultat a été obtenu, **ce
// qu'il vaut**, **qui l'a posé et quand**. Le mode d'exécution passe en premier parce que c'est
// lui qui qualifie tout le reste — un « Passed » automatique et un « Passed » manuel ne se lisent
// pas de la même façon.
import { computed } from 'vue'
import { API_BASE, type ResultOut } from '../lib/api'
import { testStatusMeta } from '../lib/status'
import ResultMode from './ResultMode.vue'

const props = defineProps<{ results: ResultOut[]; loading?: boolean }>()

// Le plus RÉCENT en haut : c'est celui qui fait foi, et celui qu'on vient d'écrire.
const ordre = computed(() => [...props.results].reverse())

function quand(iso: string): string {
  if (!iso) return ''
  return iso.slice(0, 16).replace('T', ' à ')
}

// Lien de TÉLÉCHARGEMENT direct : un `<a href>` cliqué est une navigation de premier niveau, le
// cookie de session part avec (SameSite=Lax l'autorise) — même en dev où le front (:5173) et
// l'API (:8000) sont deux origines. Pas besoin d'un `fetch` ni d'un blob intermédiaire.
function urlPiece(resultId: number, attachmentId: number): string {
  return `${API_BASE}/api/results/${resultId}/attachments/${attachmentId}`
}
function taille(octets: number): string {
  if (octets < 1024) return `${octets} o`
  if (octets < 1024 * 1024) return `${Math.round(octets / 1024)} Ko`
  return `${(octets / (1024 * 1024)).toFixed(1)} Mo`
}
</script>

<template>
  <div>
    <h3 class="text-sm font-semibold">
      Résultats
      <span v-if="results.length" class="font-normal text-muted-foreground">({{ results.length }})</span>
    </h3>

    <p v-if="loading" class="mt-2 text-sm text-muted-foreground">Chargement…</p>

    <!-- ⚠️ « Aucun résultat » et non « Non testé » : ici on décrit l'historique, pas un statut.
         Les confondre laisserait croire qu'un verdict « non testé » a été posé par quelqu'un. -->
    <p v-else-if="!results.length" class="mt-2 text-sm text-muted-foreground italic">
      Aucun résultat pour ce cas dans cette campagne.
    </p>

    <ul v-else class="mt-3 space-y-3">
      <li v-for="r in ordre" :key="r.id"
          class="rounded-lg border border-border bg-surface-raised/50 p-3">
        <div class="flex flex-wrap items-center gap-2">
          <ResultMode :mode="r.mode" />
          <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-[12px] font-semibold"
                :class="testStatusMeta(r.statut).badge">
            {{ testStatusMeta(r.statut).label }}
          </span>
          <span class="ml-auto text-[11px] text-muted-foreground">
            <!-- Le nom est une SIGNATURE déclarée, pas une identité vérifiée (§8 du brief) :
                 « — » quand personne n'était connecté, jamais un nom deviné. -->
            {{ r.created_by || '—' }} · {{ quand(r.created_at) }}
          </span>
        </div>

        <p v-if="r.comment" class="mt-2 whitespace-pre-wrap text-sm text-foreground/90">{{ r.comment }}</p>

        <!-- Pièces jointes — la preuve visuelle d'un constat manuel. Un résultat automatique
             n'en a normalement pas (il a sa propre trace, ci-dessous), mais rien ne l'interdit :
             on affiche la liste dès qu'elle existe, quel que soit le mode. -->
        <ul v-if="r.attachments?.length" class="mt-2 flex flex-wrap gap-2">
          <li v-for="p in r.attachments" :key="p.id">
            <a :href="urlPiece(r.id, p.id)" target="_blank" rel="noopener"
               class="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1 text-[12px] text-primary hover:border-primary/40 hover:underline">
              <svg class="h-3.5 w-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" />
              </svg>
              <span class="max-w-[14rem] truncate">{{ p.filename }}</span>
              <span class="text-muted-foreground">({{ taille(p.size_bytes) }})</span>
            </a>
          </li>
        </ul>

        <!-- Un résultat AUTOMATIQUE a une trace : on la nomme, plutôt que de la laisser deviner. -->
        <p v-if="r.mode === 'automatique' && r.execution_id"
           class="mt-2 text-[11px] text-muted-foreground">
          Exécution #{{ r.execution_id }} — rapport détaillé et trace brute disponibles.
        </p>
      </li>
    </ul>
  </div>
</template>
