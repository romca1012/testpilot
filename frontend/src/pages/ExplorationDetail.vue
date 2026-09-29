<script setup lang="ts">
// Écran de consultation de la cartographie explorée — voir CE que le crawl a vu (routes, champs,
// actions, liens, formulaires), aussi bien pour investiguer un souci que simplement parcourir ce
// qu'une exploration a capturé, sans se connecter au serveur ni ouvrir `data/domain/…json` à la
// main. Pure lecture : rien ici ne relance une exploration ni ne modifie le projet.
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, type Exploration, type ExplorationPage, type ProjectSummary } from '../lib/api'
import Card from '../components/ui/Card.vue'
import Spinner from '../components/ui/Spinner.vue'
import Chip from '../components/ui/Chip.vue'
import Icon from '../components/ui/Icon.vue'
import StatTile from '../components/StatTile.vue'

const route = useRoute()
const pid = route.params.pid as string

const projet = ref<ProjectSummary | null>(null)
const etat = ref<Exploration | null>(null)
const pages = ref<ExplorationPage[]>([])
const loading = ref(true)
const error = ref('')
const filtre = ref('')
const ouvertes = ref<Set<string>>(new Set())

function bascule(page: string) {
  const s = new Set(ouvertes.value)
  if (s.has(page)) s.delete(page); else s.add(page)
  ouvertes.value = s
}

// Champs les plus courants dans un objet mesuré — le reste (variable selon le connecteur, ex.
// `options` d'un <select>, `contraintes` de validation) reste visible en clair mais sans colonne
// dédiée : la forme du crawl évolue, cet écran ne doit pas la figer.
function libelle(o: Record<string, any>): string {
  return o.label || o.name || o.text || '—'
}

const pagesFiltrees = computed(() => {
  const q = filtre.value.trim().toLowerCase()
  if (!q) return pages.value
  return pages.value.filter(p =>
    p.route.toLowerCase().includes(q) || (p.titre || '').toLowerCase().includes(q))
})

const totalChamps = computed(() => pages.value.reduce((n, p) => n + p.champs.length, 0))
const totalActions = computed(() => pages.value.reduce((n, p) => n + p.actions.length, 0))
const totalLiens = computed(() => pages.value.reduce((n, p) => n + p.liens.length, 0))

onMounted(async () => {
  try {
    const [projets, e, p] = await Promise.all([
      api.listProjects(), api.getExploration(pid), api.getExplorationPages(pid),
    ])
    projet.value = projets.find(x => String(x.id) === pid) || null
    etat.value = e
    pages.value = p
  } catch (e: any) {
    error.value = e?.message || 'Cartographie indisponible'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="space-y-6">
    <RouterLink to="/admin/projects"
                class="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
      <Icon name="chevron" class="h-3.5 w-3.5 rotate-180" /> Projets
    </RouterLink>

    <div v-if="loading" class="flex items-center gap-2 text-muted-foreground text-sm">
      <Spinner class="h-4 w-4" /> Chargement…
    </div>
    <p v-else-if="error" class="text-sm text-destructive">{{ error }}</p>

    <template v-else>
      <div>
        <h1 class="text-2xl font-semibold tracking-tight">
          Cartographie explorée{{ projet ? ' — ' + projet.name : '' }}
        </h1>
        <p v-if="projet?.base_url" class="mt-1 text-sm text-muted-foreground">
          {{ projet.base_url }}
        </p>
        <p v-if="etat?.mesure_le" class="mt-1 text-sm text-subtle-foreground">
          Mesuré le {{ etat.mesure_le }} — crawl déterministe Playwright, aucun LLM. C'est une
          photo qui vieillit : elle ne se met pas à jour toute seule.
        </p>
      </div>

      <p v-if="!pages.length" class="text-sm text-subtle-foreground">
        Aucune page explorée pour ce projet — lancez une exploration depuis l'écran des projets.
      </p>

      <template v-else>
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Routes" :value="pages.length" icon="folder" tone="primary" />
          <StatTile label="Champs" :value="totalChamps" icon="file" tone="muted" />
          <StatTile label="Actions" :value="totalActions" icon="check" tone="success" />
          <StatTile label="Liens" :value="totalLiens" icon="dot" tone="muted" />
        </div>

        <input v-model="filtre" type="text" placeholder="Filtrer par route ou par titre…"
               class="h-9 w-full max-w-sm rounded-md border border-border bg-surface-raised px-3 text-sm
                      placeholder:text-subtle-foreground focus:outline-none focus:ring-1 focus:ring-primary" />

        <div class="space-y-2">
          <Card v-for="p in pagesFiltrees" :key="p.route" :dense="true">
            <button type="button" class="flex w-full items-center justify-between gap-3 text-left"
                    @click="bascule(p.route)">
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <code class="truncate text-sm font-medium text-foreground">{{ p.route }}</code>
                  <span v-if="p.titre" class="truncate text-xs text-muted-foreground">{{ p.titre }}</span>
                </div>
                <div class="mt-1 text-xs text-subtle-foreground">
                  {{ p.champs.length }} champ{{ p.champs.length > 1 ? 's' : '' }}
                  · {{ p.actions.length }} action{{ p.actions.length > 1 ? 's' : '' }}
                  · {{ p.liens.length }} lien{{ p.liens.length > 1 ? 's' : '' }}
                  <template v-if="p.formulaires.length">
                    · {{ p.formulaires.length }} formulaire{{ p.formulaires.length > 1 ? 's' : '' }}
                  </template>
                </div>
              </div>
              <Icon name="chevron" class="h-4 w-4 shrink-0 text-muted-foreground/50 transition-transform"
                    :class="ouvertes.has(p.route) ? 'rotate-90' : ''" />
            </button>

            <div v-if="ouvertes.has(p.route)" class="mt-4 space-y-4 border-t border-border/60 pt-4">
              <div v-if="p.champs.length">
                <div class="text-[11px] font-medium uppercase tracking-wide text-subtle-foreground">Champs</div>
                <div class="mt-1.5 flex flex-wrap gap-1.5">
                  <Chip v-for="(c, i) in p.champs" :key="i"
                        :icon="c.required ? 'check' : 'circle'"
                        :label="libelle(c) + (c.tag ? ` (${c.tag}${c.type ? ':' + c.type : ''})` : '')"
                        :cls="c.required
                          ? 'border-warning/40 bg-warning/10 text-warning'
                          : 'border-border bg-surface-raised text-muted-foreground'" />
                </div>
              </div>

              <div v-if="p.actions.length">
                <div class="text-[11px] font-medium uppercase tracking-wide text-subtle-foreground">Actions</div>
                <div class="mt-1.5 flex flex-wrap gap-1.5">
                  <Chip v-for="(a, i) in p.actions" :key="i"
                        :icon="a.soumet ? 'check' : 'dot'"
                        :label="libelle(a)"
                        :cls="a.soumet
                          ? 'border-primary/40 bg-primary/10 text-primary'
                          : 'border-border bg-surface-raised text-muted-foreground'" />
                </div>
              </div>

              <div v-if="p.liens.length">
                <div class="text-[11px] font-medium uppercase tracking-wide text-subtle-foreground">Liens</div>
                <ul class="mt-1.5 space-y-1">
                  <li v-for="(l, i) in p.liens" :key="i" class="truncate text-xs text-muted-foreground">
                    <span class="text-foreground">{{ l.text || '—' }}</span>
                    <span class="text-subtle-foreground"> → {{ l.href }}</span>
                  </li>
                </ul>
              </div>

              <div v-if="p.formulaires.length">
                <div class="text-[11px] font-medium uppercase tracking-wide text-subtle-foreground">Formulaires</div>
                <ul class="mt-1.5 space-y-1">
                  <li v-for="(f, i) in p.formulaires" :key="i" class="text-xs text-muted-foreground">
                    <span class="uppercase text-foreground">{{ f.method || 'get' }}</span>
                    {{ f.action || '(même page)' }} — {{ f.champs }} champ{{ f.champs > 1 ? 's' : '' }}
                  </li>
                </ul>
              </div>
            </div>
          </Card>
        </div>

        <p v-if="!pagesFiltrees.length" class="text-sm text-subtle-foreground">
          Aucune route ne correspond à « {{ filtre }} ».
        </p>
      </template>
    </template>
  </div>
</template>
