<script setup lang="ts">
/**
 * Arbre Modules → Cas du projet (colonne de l'explorateur « Gestion des cas »).
 *
 * But : percevoir toute la structure d'un projet d'un coup d'œil, sans ouvrir les modules un par
 * un. Le module est un dossier repliable ; déplié, il montre SES cas directement.
 *
 * ⚠️ Arbre à DEUX niveaux, volontairement NON récursif : la hiérarchie est Projet → Module → Cas
 * (décision 0004). Il n'existe pas de sous-module ; rendre l'arbre récursif promettrait une
 * profondeur que le modèle de données n'a pas (piège « affiché ≠ réel », invariant 4.6).
 *
 * ⚠️ Aucune pastille de statut FUSIONNÉE sur un cas : un point unique « OK/KO » violerait
 * l'invariant 4.1 (les deux axes ne fusionnent jamais). L'arbre ne porte que l'ÉTAT du cas
 * (Nouveau/Conception/Prêt/Obsolète), qui ne parle pas d'exécution du tout ; les deux axes
 * restent dans la table et le détail.
 *
 * Aucun appel réseau ici : le parent fournit modules + cas (déjà chargés par l'API existante),
 * le groupage est local.
 */
import { computed } from 'vue'
import type { CaseSummary, ModuleSummary } from '../lib/api'
import { etatView, prettyModule, toneClasses } from '../lib/status'
import Icon from './ui/Icon.vue'

const props = defineProps<{
  modules: ModuleSummary[]
  cases: CaseSummary[]
  projectId: string
  /** Ids des modules dépliés (état porté par le parent → persistable). */
  expanded: number[]
  selectedCaseId?: number | null
  selectedModuleId?: number | null
}>()

const emit = defineEmits<{
  (e: 'toggle', moduleId: number): void
  (e: 'expand-all'): void
  (e: 'collapse-all'): void
}>()

/** Cas groupés par module. Compte RÉEL (les cas affichés), pas `case_count` du DTO : l'arbre ne
 *  doit jamais annoncer un nombre que sa propre liste contredit. */
const casesByModule = computed(() => {
  const map = new Map<number, CaseSummary[]>()
  for (const m of props.modules) map.set(m.id, [])
  for (const c of props.cases) {
    if (c.module_id == null) continue
    const bucket = map.get(c.module_id)
    if (bucket) bucket.push(c)
  }
  return map
})

const casesOf = (moduleId: number) => casesByModule.value.get(moduleId) || []
const isExpanded = (moduleId: number) => props.expanded.includes(moduleId)
const allExpanded = computed(() =>
  props.modules.length > 0 && props.modules.every((m) => isExpanded(m.id)))

/** Cas orphelins (module_id null) : on les EXPOSE au lieu de les cacher — un cas invisible dans
 *  l'arbre serait un cas qu'on croit inexistant. */
const orphans = computed(() => props.cases.filter((c) => c.module_id == null))

/** Indicateur d'ÉTAT compact pour l'arbre : ICÔNE (dont la forme change selon l'état) + le mot
 *  en infobulle. Pas de chip complet — il écraserait les titres dans une colonne étroite ; pas
 *  non plus un simple point coloré, la couleur seule ne portant jamais un statut (règle de
 *  `Chip`, invariant 4.7). ⚠️ L'État décrit l'avancement du DOCUMENT, jamais un résultat de
 *  test : aucun risque de le confondre avec un verdict, donc aucune fusion d'axes (4.1). */
const etat = (code: string | null) => etatView(code)
</script>

<template>
  <div class="flex h-full flex-col">
    <div class="flex items-center justify-between gap-2 px-2 pb-2">
      <span class="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        Structure
      </span>
      <button
        v-if="modules.length"
        class="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
        @click="allExpanded ? emit('collapse-all') : emit('expand-all')"
      >
        {{ allExpanded ? 'Tout replier' : 'Tout déplier' }}
      </button>
    </div>

    <p v-if="!modules.length && !orphans.length" class="px-2 py-3 text-xs text-muted-foreground">
      Aucun module dans ce projet.
    </p>

    <ul v-else class="space-y-0.5 overflow-y-auto pr-1">
      <li v-for="m in modules" :key="m.id">
        <!-- Nœud MODULE : le chevron/la ligne replie ; le nom mène à la page du module. -->
        <div
          class="group flex items-center gap-1 rounded-md pr-1.5 text-sm transition-colors"
          :class="selectedModuleId === m.id
            ? 'bg-primary/15 text-foreground'
            : 'text-muted-foreground hover:bg-accent/40 hover:text-foreground'"
        >
          <button class="grid h-6 w-5 shrink-0 place-items-center" :aria-expanded="isExpanded(m.id)"
                  :title="isExpanded(m.id) ? 'Replier' : 'Déplier'" @click="emit('toggle', m.id)" :aria-label="isExpanded(m.id) ? 'Replier' : 'Déplier'">
            <Icon name="chevron" class="h-3 w-3 transition-transform"
                  :class="isExpanded(m.id) ? 'rotate-90' : ''" />
          </button>
          <RouterLink :to="`/projects/${projectId}/modules/${m.id}`" :title="prettyModule(m.name)"
                      class="flex min-w-0 flex-1 items-center gap-1.5 py-1.5">
            <Icon name="folder" class="h-3.5 w-3.5 shrink-0 opacity-60" />
            <span class="truncate">{{ prettyModule(m.name) }}</span>
          </RouterLink>
          <span class="shrink-0 text-[11px] tabular-nums text-muted-foreground/70">
            {{ casesOf(m.id).length }}
          </span>
        </div>

        <!-- Enfants : les CAS du module (ce que le prototype ne montrait pas), rattachés par un
             connecteur d'arborescence façon `tree` — « ├─ » pour les intermédiaires, « └─ »
             pour le DERNIER : c'est ce coude final qui ferme visuellement la fratrie. -->
        <ul v-if="isExpanded(m.id)" class="mt-0.5 space-y-0.5 pl-2.5">
          <li v-for="(c, i) in casesOf(m.id)" :key="c.id">
            <RouterLink
              :to="`/projects/${projectId}/cases/${c.id}`" :title="c.title"
              class="flex items-center gap-1.5 rounded-md py-1.5 pr-1.5 text-sm transition-colors"
              :class="selectedCaseId === c.id
                ? 'bg-primary/15 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.3)]'
                : 'text-muted-foreground hover:bg-accent/40 hover:text-foreground'"
            >
              <span aria-hidden="true"
                    class="shrink-0 select-none font-mono text-xs leading-none text-muted-foreground/40">
                {{ i === casesOf(m.id).length - 1 ? '└─' : '├─' }}
              </span>
              <!-- Icône DOCUMENT, pas dossier : dans l'arbre un cas est une FEUILLE, il ne se
                   déplie pas. Un dossier promettrait un contenu qu'on ne peut pas ouvrir
                   (« affiché ≠ réel », 4.6). L'appartenance est portée par le connecteur. -->
              <Icon name="file" class="h-3.5 w-3.5 shrink-0 opacity-60" />
              <span class="min-w-0 flex-1 truncate">{{ c.title }}</span>
              <!-- ÉTAT du document seulement. Jamais un badge de verdict fusionné (4.1). -->
              <span class="shrink-0 rounded-full border p-0.5" :class="toneClasses(etat(c.etat).tone)"
                    :title="`État : ${etat(c.etat).label}`">
                <Icon :name="etat(c.etat).icon" class="h-3 w-3" />
              </span>
            </RouterLink>
          </li>
          <li v-if="!casesOf(m.id).length"
              class="flex items-center gap-1.5 py-1.5 text-xs text-muted-foreground/70">
            <span aria-hidden="true" class="select-none font-mono leading-none text-muted-foreground/40">└─</span>
            Aucun cas dans ce module.
          </li>
        </ul>
      </li>

      <!-- Cas sans module : montrés explicitement plutôt qu'omis en silence. -->
      <li v-if="orphans.length" class="pt-1">
        <div class="px-2 py-1 text-[11px] text-muted-foreground/70">Sans module</div>
        <RouterLink
          v-for="(c, i) in orphans" :key="c.id" :to="`/projects/${projectId}/cases/${c.id}`" :title="c.title"
          class="flex items-center gap-1.5 rounded-md py-1.5 pl-2.5 pr-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent/40 hover:text-foreground"
        >
          <span aria-hidden="true"
                class="shrink-0 select-none font-mono text-xs leading-none text-muted-foreground/40">
            {{ i === orphans.length - 1 ? '└─' : '├─' }}
          </span>
          <Icon name="file" class="h-3.5 w-3.5 shrink-0 opacity-60" />
          <span class="min-w-0 flex-1 truncate">{{ c.title }}</span>
          <span class="shrink-0 rounded-full border p-0.5" :class="toneClasses(etat(c.etat).tone)"
                :title="`État : ${etat(c.etat).label}`">
            <Icon :name="etat(c.etat).icon" class="h-3 w-3" />
          </span>
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
