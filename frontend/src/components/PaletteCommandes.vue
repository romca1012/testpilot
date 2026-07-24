<script setup lang="ts">
// LA PALETTE DE COMMANDES (Ctrl/⌘ + K) — lot D, 2026-07-24.
//
// ── Pourquoi ────────────────────────────────────────────────────────────────────────────────
// Le public de cet outil est un public d'usage RÉPÉTÉ : un QA y revient tous les jours, fait les
// mêmes gestes, et connaît son référentiel. Pour lui, le chemin le plus court vers une action ne
// doit pas être « la souris, trois menus et un clic ». La palette met tout à une frappe, et
// **affiche le raccourci à côté de chaque entrée** — c'est ainsi qu'on les apprend, sans jamais
// avoir à lire une documentation.
//
// ── Ce qu'elle fait, et ce qu'elle ne fait pas ──────────────────────────────────────────────
// Elle NAVIGUE et elle OUVRE. Elle ne supprime pas, ne lance pas de campagne, ne dépense rien :
// une palette est un accélérateur de déplacement, et une action irréversible atteinte par une
// frappe distraite serait exactement le contraire d'un gain.
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCas } from '../lib/donnees'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string | undefined)

const ouverte = ref(false)
const requete = ref('')
const index = ref(0)
const champ = ref<HTMLInputElement | null>(null)

// Les cas viennent du cache partagé (lot A) : ouvrir la palette ne déclenche aucune requête.
const { data: casData } = useCas(computed(() => pid.value || ''))

interface Entree {
  id: string
  libelle: string
  detail?: string
  raccourci?: string
  aller: () => void
}

const commandes = computed<Entree[]>(() => {
  if (!pid.value) return []
  const p = pid.value
  const vers = (name: string, params: any = {}) => () => router.push({ name, params: { pid: p, ...params } })
  return [
    { id: 'cases', libelle: 'Cas de test', detail: 'Aller à la liste', aller: vers('cases') },
    { id: 'case-new', libelle: 'Générer des cas de test', detail: 'Depuis une spécification', aller: vers('case-new') },
    { id: 'case-manual', libelle: 'Ajouter un cas de test', detail: 'Saisie manuelle, sans IA', aller: vers('case-manual') },
    { id: 'exec', libelle: 'Exécutions et résultats', aller: vers('executions') },
    { id: 'run-new', libelle: 'Créer une campagne', aller: vers('run-new') },
    { id: 'quality', libelle: 'Qualité de génération', aller: vers('quality') },
    { id: 'corbeille', libelle: 'Corbeille', detail: 'Restaurer un élément supprimé', aller: vers('corbeille') },
    { id: 'projects', libelle: 'Gérer les projets', aller: () => router.push('/projects') },
  ]
})

// Les CAS eux-mêmes sont des entrées : « ouvre C12 » est le geste le plus fréquent d'un QA qui
// sait ce qu'il cherche. Bornés à 8 — une palette qui déroule 400 lignes n'aide plus personne.
const resultats = computed<Entree[]>(() => {
  const q = requete.value.trim().toLowerCase()
  const cmds = commandes.value.filter((c) => !q || c.libelle.toLowerCase().includes(q))
  if (!q) return cmds
  const cas = (casData.value ?? [])
    .filter((c) => `c${c.id}`.includes(q) || c.title.toLowerCase().includes(q))
    .slice(0, 8)
    .map((c) => ({
      id: `cas-${c.id}`,
      libelle: c.title,
      detail: `C${c.id} · ${c.module || ''}`,
      aller: () => router.push({ name: 'case-detail', params: { pid: pid.value!, id: String(c.id) } }),
    }))
  return [...cmds, ...cas]
})

watch(requete, () => { index.value = 0 })

function ouvrir() {
  ouverte.value = true
  requete.value = ''
  index.value = 0
  nextTick(() => champ.value?.focus())
}
function fermer() { ouverte.value = false }

function executer(e?: Entree) {
  const cible = e || resultats.value[index.value]
  if (!cible) return
  fermer()
  cible.aller()
}

function onKey(e: KeyboardEvent) {
  // ⚠️ `metaKey` ET `ctrlKey` : ⌘K sur Mac, Ctrl+K ailleurs. N'en gérer qu'un rendrait la
  // palette inatteignable pour la moitié des postes.
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    ouverte.value ? fermer() : ouvrir()
    return
  }
  if (!ouverte.value) return
  if (e.key === 'Escape') { e.preventDefault(); fermer() }
  else if (e.key === 'ArrowDown') { e.preventDefault(); index.value = Math.min(index.value + 1, resultats.value.length - 1) }
  else if (e.key === 'ArrowUp') { e.preventDefault(); index.value = Math.max(index.value - 1, 0) }
  else if (e.key === 'Enter') { e.preventDefault(); executer() }
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
defineExpose({ ouvrir })
</script>

<template>
  <!-- ⚠️ La palette ne se rend QUE sous un projet : ses commandes ont toutes besoin d'un `pid`,
       et les proposer hors contexte mènerait à des liens cassés. -->
  <div v-if="ouverte && pid" class="fixed inset-0 z-50 grid place-items-start justify-center bg-black/50 p-4 pt-[12vh]"
       @click.self="fermer">
    <div class="w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface-overlay shadow-2xl"
         role="dialog" aria-modal="true" aria-label="Palette de commandes">
      <div class="flex items-center gap-2 border-b border-border px-4 py-3">
        <svg class="h-4 w-4 shrink-0 text-muted-foreground" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        <input ref="champ" v-model="requete" type="text"
               placeholder="Aller à… ou chercher un cas de test"
               aria-label="Rechercher une commande ou un cas de test"
               class="w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground/70" />
        <kbd class="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">Échap</kbd>
      </div>

      <ul class="max-h-80 overflow-y-auto py-1">
        <li v-for="(e, i) in resultats" :key="e.id">
          <button class="flex w-full items-center gap-3 px-4 py-2 text-left text-sm"
                  :class="i === index ? 'bg-primary/15 text-foreground' : 'hover:bg-accent/50'"
                  @click="executer(e)" @mousemove="index = i">
            <span class="min-w-0 flex-1 truncate">{{ e.libelle }}</span>
            <span v-if="e.detail" class="shrink-0 text-xs text-muted-foreground">{{ e.detail }}</span>
          </button>
        </li>
        <li v-if="!resultats.length" class="px-4 py-6 text-center text-sm text-muted-foreground">
          Rien ne correspond à « {{ requete }} ».
        </li>
      </ul>

      <!-- Les raccourcis s'affichent ICI : c'est en les voyant qu'on les apprend. -->
      <div class="flex items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-muted-foreground">
        <span><kbd class="rounded border border-border px-1">↑</kbd> <kbd class="rounded border border-border px-1">↓</kbd> naviguer</span>
        <span><kbd class="rounded border border-border px-1">Entrée</kbd> ouvrir</span>
        <span class="flex-1"></span>
        <span><kbd class="rounded border border-border px-1">Ctrl</kbd> + <kbd class="rounded border border-border px-1">K</kbd> à tout moment</span>
      </div>
    </div>
  </div>
</template>
