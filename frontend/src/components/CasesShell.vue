<script setup lang="ts">
// Shell « Cas de test » — disposition inspirée de TestRail, palette sombre du projet.
// Adopté comme SHELL des routes de gestion des cas (option (a) validée le 2026-07-20). La
// Spécification (case_group) apparaît ICI dans l'arbre (Module → Spécification), sans être un
// concept qu'on impose ailleurs. Les boutons/onglets non couverts par ce lot mènent à « à venir ».
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, LIBELLE_ROLE } from '../lib/api'
import { useProjects } from '../lib/useProjects'
import { useModuleCreate } from '../lib/useModuleCreate'
import { useSectionCreate } from '../lib/useSectionCreate'
import { useSession } from '../lib/useSession'
// Couche de données (lot A, 2026-07-24) : plus de `load()` maison ici. Le shell et la page
// affichée demandaient les MÊMES modules, cas et spécifications à chaque navigation ; ils
// partagent désormais un seul cache, et une mutation invalide ce qu'il faut.
import {
  useCreerGroupe, useCreerModule, useGroupes, useModules, useNbCas, useSupprimerModule, useUnCas,
} from '../lib/donnees'
import Modal from './ui/Modal.vue'
import Button from './ui/Button.vue'
import IconButton from './ui/IconButton.vue'

const route = useRoute()
const router = useRouter()
const { projects, ensureLoaded, projectById } = useProjects()
const { session } = useSession()

// Modale UNIQUE de création de module (déclenchée d'ici « + Ajouter une section », et depuis la
// liste des cas). Le shell est toujours présent sur les routes de gestion : c'est son bon hôte.
const mc = useModuleCreate()
const nm = ref({ name: '', description: '' })
const creatingModule = ref(false)
const moduleError = ref('')

watch(() => mc.open.value, (o) => { if (o) { nm.value = { name: '', description: '' }; moduleError.value = '' } })

const creerModule = useCreerModule(computed(() => mc.pid.value || (pid.value as string)))

async function submitModule() {
  const name = nm.value.name.trim()
  if (!name) return
  creatingModule.value = true
  moduleError.value = ''
  try {
    // La mutation invalide le projet : l'arbre ET les pages qui listent les modules se
    // rafraîchissent seuls. Plus de `load()` manuel à ne pas oublier.
    await creerModule.mutateAsync({ name, description: nm.value.description.trim() })
    mc.close()
    mc.markCreated()
  } catch (e: any) {
    moduleError.value = e?.message || 'Création impossible'
  } finally {
    creatingModule.value = false
  }
}

const pid = computed(() => route.params.pid as string | undefined)
const currentProject = computed(() => projectById(pid.value))
const menuOpen = ref(false)

// Les trois listes de l'arbre viennent du cache partagé. `?? []` parce qu'une requête en vol n'a
// pas encore de données : l'arbre se dessine vide plutôt que de faire tomber le rendu.
const { data: modulesData } = useModules(pid)
const { data: groupsData } = useGroupes(pid)
const modules = computed(() => modulesData.value ?? [])
const groups = computed(() => groupsData.value ?? [])
// ⚠️ L'arbre ne charge PLUS tous les cas du projet (2026-07-24). Il n'en avait besoin que pour
// deux choses : un compteur et le fil d'Ariane d'un cas ouvert. À 2 000 cas, il payait une
// réponse de plusieurs mégaoctets pour afficher un nombre.
const caseCount = useNbCas(pid)
const expanded = ref<number[]>([])

// Tout déplié au premier chargement d'un projet — un arbre entièrement replié ne montre rien
// de ce qu'on vient d'ouvrir.
watch(modules, (m) => { if (m.length && !expanded.value.length) expanded.value = m.map((x) => x.id) })
watch(pid, () => { expanded.value = [] })   // changer de projet ne conserve pas un dépliage étranger

onMounted(() => { ensureLoaded() })
watch(pid, () => { ensureLoaded() })
// ⚠️ **Le rechargement à chaque navigation a été SUPPRIMÉ** (`watch(route.fullPath, load)`).
// Il rechargeait modules + spécifications + cas à chaque clic, en double avec la page affichée.
// Ce qui le remplace : les mutations invalident explicitement ce qu'elles périment
// (`lib/donnees.ts`). Une donnée fraîche de moins de 30 s n'est plus redemandée.

const specCount = computed(() => groups.value.length)
const initial = computed(() => (currentProject.value?.name || '?').trim().charAt(0).toUpperCase())

function groupsOf(moduleId: number) {
  return groups.value.filter((g) => g.module_id === moduleId)
}
function toggle(moduleId: number) {
  expanded.value = expanded.value.includes(moduleId)
    ? expanded.value.filter((id) => id !== moduleId)
    : [...expanded.value, moduleId]
}
const activeGroupId = computed(() =>
  route.name === 'spec-detail' ? Number(route.params.id) || null
  : route.name === 'cases' ? Number(route.query.spec) || null : null)

// ── Créer une SECTION ou une SOUS-SECTION (lot 4, 2026-07-24 ; sous-sections, migration 28) ────
// ⚠️ Créer ici ne génère AUCUN cas et ne dépense RIEN : on nomme un document, on l'écrit sur sa
// fiche, et c'est un geste séparé qui lance la génération (§4bis du brief).
// Modale UNIQUE, comme la création de module : plusieurs endroits la déclenchent (l'arbre latéral,
// et surtout les liens inline sous chaque module/Section de TestCasesList.vue, à l'endroit exact
// où TestRail les place) — `useSectionCreate` est le composable partagé qui les fait converger ici.
const sc = useSectionCreate()
const nouvelleSpec = ref({ title: '' })
const creatingSpec = ref(false)
const specError = ref('')
const specModalTitle = computed(() => sc.parentGroupId.value ? 'Nouvelle sous-section' : 'Nouvelle section')

watch(() => sc.open.value, (o) => { if (o) { nouvelleSpec.value = { title: '' }; specError.value = '' } })

function ouvrirCreationSpec(moduleId: number) {
  sc.openFor(moduleId)
}

const creerGroupe = useCreerGroupe(pid)

async function submitSpec() {
  const titre = nouvelleSpec.value.title.trim()
  if (!titre || sc.moduleId.value == null) return
  creatingSpec.value = true
  specError.value = ''
  try {
    const creee = await creerGroupe.mutateAsync({
      moduleId: sc.moduleId.value, title: titre, parentGroupId: sc.parentGroupId.value,
    })
    sc.close()
    sc.markCreated()
    // On emmène sur sa fiche : une Section vide qu'on ne rédige pas ne sert à rien.
    router.push({ name: 'spec-detail', params: { pid: pid.value, id: String(creee.id) } })
  } catch (e: any) {
    specError.value = e?.message || 'Création impossible'
  } finally {
    creatingSpec.value = false
  }
}

function ouvrirFicheSpec(groupId: number) {
  router.push({ name: 'spec-detail', params: { pid: pid.value, id: String(groupId) } })
}
const activeModuleId = computed(() =>
  route.name === 'cases' ? Number(route.query.module) || null : null)

function openSpec(groupId: number) {
  // ⚠️ On GARDE le reste de la query (notamment `module`) : filtrer sur une Section ne doit pas
  // faire perdre le module qu'on regardait — sinon « retirer le filtre » renvoie à une vue plus
  // large que celle d'où on est parti (mesuré le 2026-08-05).
  router.push({ name: 'cases', params: { pid: pid.value }, query: { ...route.query, spec: String(groupId) } })
}

// ── Sous-navigation d'un cas — NICHÉE sous « Cas de test » (pas une colonne à part) ──
const caseId = computed(() => (route.name === 'case-detail' ? Number(route.params.id) : null))
// Le cas ouvert se demande par son identifiant, plutôt que d'être cherché dans une liste qu'on
// aurait chargée entièrement pour lui.
const { data: caseDetail } = useUnCas(computed(() => caseId.value ?? ''))
const currentCase = computed(() => caseDetail.value?.case ?? null)
const caseTab = computed(() => (route.query.tab as string) || 'details')
const subtabs = [
  { key: 'details', label: 'Détails' },
  { key: 'tests', label: 'Tests & Résultats' },
  { key: 'defauts', label: 'Défauts' },
  { key: 'historique', label: 'Historique' },
  // Consultation du Gherkin/Python généré (2026-08-07) — édition réservée au rôle Dev, mais la
  // LECTURE reste ouverte à tous : c'est l'onglet qui l'affiche, pas le contenu, qui se gate.
  { key: 'script', label: 'Script' },
]
function goSubTab(key: string) {
  if (!caseId.value) return
  router.push({ name: 'case-detail', params: { pid: pid.value, id: String(caseId.value) },
    query: key === 'details' ? {} : { tab: key } })
}

// ── Sous-navigation d'un RUN — NICHÉE sous « Exécutions et résultats de test » (même patron) ──
// ⚠️ Les sous-onglets sont de VRAIES routes depuis le 2026-08-05, plus un `?tab=` sur
// `run-detail` : chacun charge sa propre donnée, et la page d'un TEST (`run-test`) doit garder ce
// contexte de campagne dans la barre latérale — sinon on perd la campagne en ouvrant un test.
const ROUTES_RUN = ['run-detail', 'run-activite', 'run-progression', 'run-test']
const runId = computed(() =>
  ROUTES_RUN.includes(String(route.name)) ? Number(route.params.id) : null)
const runSubtabs = [
  { key: 'tests', label: 'Tests & Résultats', route: 'run-detail', ready: true },
  { key: 'activite', label: 'Activité', route: 'run-activite', ready: true },
  { key: 'progression', label: 'Progression', route: 'run-progression', ready: true },
  // Seul « Défauts » reste à venir : TestPilot ne modélise pas encore de défaut rattaché à un
  // résultat, et un écran de compteurs à zéro laisserait croire que la question est réglée.
  { key: 'defauts', label: 'Défauts', route: '', ready: false },
]
// L'onglet actif se lit sur le NOM DE ROUTE. Un test ouvert (`run-test`) garde « Tests &
// Résultats » allumé : c'est de là qu'on y est arrivé, et c'est là qu'on revient.
const runTab = computed(() =>
  runSubtabs.find((t) => t.route && t.route === String(route.name))?.key || 'tests')
function goRunTab(key: string) {
  const cible = runSubtabs.find((t) => t.key === key)
  if (!runId.value || !cible?.route) return
  router.push({ name: cible.route, params: { pid: pid.value, id: String(runId.value) } })
}

// Les pages « Cas de test » (liste + détail) se paginent elles-mêmes (barres pleine largeur) ;
// les pages héritées (exécutions, rapport…) reçoivent un cadre paddé du shell.
const fullBleed = computed(() => ['cases', 'case-detail'].includes(String(route.name)))

// ── Contexte « Exécutions » : filtres portés par l'URL, lus par RunsOverview (état partagé) ──
const execGroup = computed(() => (route.query.group as string) || 'month')
const execSort = computed(() => (route.query.sort as string) || 'date')
function setExecQuery(key: 'group' | 'sort', value: string) {
  router.replace({ name: 'executions', params: { pid: pid.value }, query: { ...route.query, [key]: value } })
}
function goRoute(name: 'run-new' | 'plan-new') {
  router.push({ name, params: { pid: pid.value } })
}
// « Ajouter un cas de test » = saisie MANUELLE (sans IA). Le module courant (si l'arbre en a un
// d'ouvert) est pré-sélectionné.
function goCaseNew(moduleId?: number) {
  router.push({ name: 'case-manual', params: { pid: pid.value },
                query: moduleId ? { module: String(moduleId) } : {} })
}
// « Générer des cas de test » = l'IA depuis une spec (texte ou fichier).
function goGenerate(moduleId?: number) {
  router.push({ name: 'case-new', params: { pid: pid.value },
                query: moduleId ? { module: String(moduleId) } : {} })
}
// Suppression d'un module — CASCADE (cas, versions, exécutions). Confirmation EXPLICITE avec le
// compte de ce qui partira : §2.10 interdit d'effacer un run en silence, pas sur demande claire.
async function deleteModule(m: { id: number; name: string }) {
  // Le compteur du module vient du SERVEUR : la liste des cas n'est plus chargée ici.
  const n = modules.value.find((x) => x.id === m.id)?.case_count ?? 0
  const detail = n ? ` et ses ${n} cas de test (avec leurs exécutions)` : ''
  if (!window.confirm(`Supprimer le module « ${m.name} »${detail} ? Cette action est irréversible.`)) return
  try {
    await supprimerModule.mutateAsync(m.id)
    // Si on était sur une page filtrée par ce module, revenir à la liste complète.
    router.push({ name: 'cases', params: { pid: pid.value } })
  } catch (e: any) {
    window.alert(e?.message || 'Suppression impossible.')
  }
}
const supprimerModule = useSupprimerModule(pid)
// Filtrer la liste sur un MODULE : c'est ce que faisait l'ancienne page module, désormais
// redirigée ici. Cliquer un module de l'arbre a donc un effet, pas seulement déplier.
function openModule(moduleId: number) {
  router.push({ name: 'cases', params: { pid: pid.value }, query: { module: String(moduleId) } })
}

// Nav principale. Seul « Cas de test » est fonctionnel dans ce lot ; le reste mène à « à venir »
// (placeholder), sauf « Exécutions » qui pointe vers l'écran d'exécution existant.
const nav = computed(() => [
  { key: 'apercu', label: 'Aperçu', to: soon('apercu'),
    icon: 'M4 5h16M4 12h16M4 19h10' },
  { key: 'todo', label: 'Tâche à faire', to: soon('todo'),
    icon: 'M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11' },
  { key: 'cases', label: 'Cas de test', to: { name: 'cases', params: { pid: pid.value } },
    icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2' },
  { key: 'exec', label: 'Exécutions et résultats de test', to: { name: 'executions', params: { pid: pid.value } },
    icon: 'M14.7 11.2l-5.2-3a1 1 0 00-1.5.8v6a1 1 0 001.5.9l5.2-3a1 1 0 000-1.7z' },
  { key: 'qualite', label: 'Qualité de génération', to: { name: 'quality', params: { pid: pid.value } },
    icon: 'M3 3v18h18M7 15l3-4 3 3 4-6' },
  { key: 'jalons', label: 'Jalons', to: soon('jalons'),
    icon: 'M5 3v18M5 4h11l-2 3 2 3H5' },
  { key: 'rapports', label: 'Rapports', to: soon('rapports'),
    icon: 'M9 17v-6M12 17V7M15 17v-3M4 5a2 2 0 012-2h12a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2z' },
])
function soon(tab: string) {
  return { name: 'cases-soon', params: { pid: pid.value }, query: { tab } }
}
function isActive(key: string) {
  const n = String(route.name)
  if (key === 'cases') return ['cases', 'case-detail', 'cases-all', 'module-detail',
                               'spec-detail', 'case-new', 'case-manual', 'corbeille'].includes(n)
  if (key === 'exec') return ['executions', 'report', 'run-new', 'plan-new', ...ROUTES_RUN].includes(n)
  if (key === 'qualite') return n === 'quality'
  return n === 'cases-soon' && route.query.tab === key
}
function comingSoon(what: string) {
  window.alert(`${what} — à venir.`)
}
async function seDeconnecter() {
  menuOpen.value = false
  try { await api.logout() } catch { /* déjà déconnecté : le rechargement suffit */ }
  // Rechargement complet plutôt qu'une navigation : il vide le cache de la couche de données,
  // sinon les cas du projet resteraient lisibles en mémoire après la déconnexion.
  window.location.reload()
}

function switchProject(id: number) {
  menuOpen.value = false
  router.push({ name: 'cases', params: { pid: String(id) } })
}
</script>

<template>
  <!-- ⚠️ Garde `pid` : le shell ne se rend JAMAIS sans projet. Pendant une transition
       shell→hors-shell, `route.params.pid` passe à undefined le temps d'un tick ; sans cette
       garde, les RouterLinks de la nav (`{name:'cases', params:{pid: undefined}}`) lèvent
       « Missing required param "pid" », qui cascade en « emitsOptions null » et corrompt l'écran. -->
  <div v-if="pid" class="app-bg min-h-screen flex">
    <aside class="w-[270px] shrink-0 border-r border-border bg-surface/60 backdrop-blur-sm flex flex-col">
      <!-- En-tête projet -->
      <div class="relative">
        <button class="h-14 w-full flex items-center gap-2.5 px-3.5 border-b border-border hover:bg-accent/40 transition-colors"
                @click="menuOpen = !menuOpen">
          <span class="h-[30px] w-[30px] rounded-lg bg-primary text-primary-foreground grid place-items-center font-bold text-sm">{{ initial }}</span>
          <span class="font-semibold flex-1 text-left truncate tracking-tight">{{ currentProject?.name || '…' }}</span>
          <svg class="w-4 h-4 text-muted-foreground shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>
        </button>
        <div v-if="menuOpen" class="absolute left-3 right-3 z-30 mt-1 rounded-md border border-border bg-surface-overlay py-1 shadow-xl">
          <button v-for="p in projects" :key="p.id"
                  class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm hover:bg-accent/60"
                  :class="p.id === Number(pid) ? 'text-primary' : 'text-foreground'"
                  @click="switchProject(p.id)">
            <span class="truncate">{{ p.name }}</span>
          </button>
          <!-- Sans ce lien, la page projets devenait INATTEIGNABLE : on ne pouvait plus créer,
               renommer ni configurer un projet depuis l'interface. -->
          <div class="my-1 border-t border-border"></div>
          <RouterLink to="/projects" class="block px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                      @click="menuOpen = false">Gérer les projets…</RouterLink>
          <!-- La corbeille doit être ATTEIGNABLE : une suppression douce qu'on ne peut pas
               annuler depuis l'interface ne vaut pas mieux qu'une destruction. -->
          <RouterLink :to="{ name: 'corbeille', params: { pid } }"
                      class="block px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                      @click="menuOpen = false">Corbeille…</RouterLink>
          <!-- Les réglages d'instance doivent être ATTEIGNABLES : un compte de service qu'on ne
               peut régler que par variable d'environnement obligerait à redémarrer le serveur
               pour changer un nom affiché dans les rapports. -->
          <RouterLink :to="{ name: 'settings' }"
                      class="block px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                      @click="menuOpen = false">Réglages…</RouterLink>
          <!-- Gestion des comptes (2026-08-07) — Admin seulement : le lien lui-même reflète déjà
               ce que le serveur imposerait de toute façon (403), pas de raison de le proposer. -->
          <RouterLink v-if="session?.role === 'admin'" :to="{ name: 'utilisateurs' }"
                      class="block px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                      @click="menuOpen = false">Utilisateurs…</RouterLink>
          <div class="my-1 border-t border-border"></div>
          <p v-if="session?.authenticated" class="px-3 py-1 text-xs text-subtle-foreground">
            Connecté en tant que {{ session.name }} · {{ LIBELLE_ROLE[session.role] || session.role }}
          </p>
          <!-- ⚠️ Sans moyen de quitter sa session, un poste commun reste ouvert au suivant qui
               s'y assied. La route existait depuis le lot 2 ; aucun écran ne l'appelait. -->
          <button class="block w-full px-3 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                  @click="seDeconnecter">Se déconnecter</button>
        </div>
      </div>

      <!-- Nav principale (+ sous-navigation d'un cas, nichée sous « Cas de test ») -->
      <nav class="p-2.5 flex flex-col gap-0.5">
        <template v-for="item in nav" :key="item.key">
          <component :is="typeof item.to === 'string' ? 'button' : 'RouterLink'"
                     :to="typeof item.to === 'string' ? undefined : item.to"
                     class="group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-left transition-colors"
                     :class="isActive(item.key) ? 'bg-primary/15 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.3)]' : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'">
            <svg class="w-4 h-4 shrink-0" :class="isActive(item.key) && 'text-primary'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path :d="item.icon"/></svg>
            <span class="flex-1">{{ item.label }}</span>
          </component>

          <!-- Sous-nav du cas ouvert — apparaît SOUS « Cas de test », indentée -->
          <div v-if="item.key === 'cases' && caseId" class="ml-4 pl-3 border-l border-border flex flex-col gap-0.5 py-1">
            <span class="px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Aperçu</span>
            <button v-for="t in subtabs" :key="t.key"
                    class="text-left rounded-md px-2.5 py-1.5 text-sm transition-colors"
                    :class="caseTab === t.key ? 'bg-primary/15 text-primary shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.3)]' : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'"
                    @click="goSubTab(t.key)">{{ t.label }}</button>
            <p v-if="currentCase" class="px-2 pt-1.5 text-xs text-muted-foreground leading-relaxed">
              Dans la section
              <button class="text-primary hover:underline" @click="openSpec(currentCase.group_id!)">{{ currentCase.group_title || currentCase.module }}</button>.
            </p>
          </div>

          <!-- Sous-nav du RUN ouvert — apparaît SOUS « Exécutions et résultats de test », indentée -->
          <div v-if="item.key === 'exec' && runId" class="ml-4 pl-3 border-l border-border flex flex-col gap-0.5 py-1">
            <span class="px-2 py-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">Aperçu</span>
            <button v-for="t in runSubtabs" :key="t.key"
                    class="text-left rounded-md px-2.5 py-1.5 text-sm transition-colors flex items-center justify-between"
                    :class="runTab === t.key ? 'bg-primary/15 text-primary shadow-[inset_0_0_0_1px_hsl(var(--primary)/0.3)]' : 'text-muted-foreground hover:text-foreground hover:bg-accent/50'"
                    @click="goRunTab(t.key)">
              {{ t.label }}<span v-if="!t.ready" class="text-xs uppercase text-muted">à venir</span>
            </button>
            <div class="px-2 pt-1.5 text-xs text-muted-foreground leading-relaxed space-y-1">
              <p>Jalon : <span class="text-muted">à venir</span></p>
              <p>Références : <span class="text-muted">aucune</span></p>
            </div>
          </div>
        </template>
      </nav>

      <!-- ══ SIDEBAR CONTEXTUELLE : le contenu change selon le module actif ══ -->

      <!-- Contexte « Cas de test » : boutons cas + arbre Module → Spécification -->
      <template v-if="isActive('cases')">
      <div class="px-3 pb-3 flex flex-col gap-2">
        <!-- « Ajouter un cas de test » = SAISIE MANUELLE (sans IA). « Générer » = l'IA depuis une
             spec. Les deux étaient confondus : « Ajouter » lançait l'IA, « Générer » ne faisait
             rien. Correction du porteur (2026-07-21). -->
        <Button variant="primary" class="w-full" @click="goCaseNew()">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          Ajouter un cas
        </Button>
        <Button variant="secondary" class="w-full" @click="goGenerate()">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15l-1.9-4.1L5.5 9l4.6-1.4z"/></svg>
          Générer des cas
        </Button>
      </div>

      <!-- Info spécifications / cas -->
      <div class="px-3.5 pb-3 text-xs leading-relaxed">
        <div class="flex items-center gap-1.5 text-muted-foreground">
          Contient {{ specCount }} section{{ specCount > 1 ? 's' : '' }} et {{ caseCount }} cas.
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/></svg>
        </div>
        <button class="text-primary hover:underline" @click="comingSoon('Modifier la description')">Modifier la description</button>
      </div>

      <!-- Bandeau + sous-barre -->
      <div class="flex items-center justify-between px-3.5 py-2.5 border-y border-border text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        Cas de test
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 13l5 5 5-5M7 6l5 5 5-5"/></svg>
      </div>
      <div class="flex items-center gap-2 px-3.5 py-2 text-xs">
        <span class="flex items-center gap-1.5 rounded-md border border-border bg-surface-raised px-2 py-1">Tous
          <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg></span>
      </div>

      <!-- Arbre Module → Spécification -->
      <div class="px-2 pb-4 overflow-y-auto">
        <template v-for="m in modules" :key="m.id">
          <div class="group flex w-full items-center gap-1 rounded-md px-1.5 py-1.5 hover:bg-accent/40"
               :class="activeModuleId === m.id && 'bg-primary/10'">
            <IconButton size="sm" class="shrink-0" :label="expanded.includes(m.id) ? 'Replier' : 'Déplier'" @click.stop="toggle(m.id)">
              <svg class="w-3 h-3 text-muted-foreground transition-transform" :class="expanded.includes(m.id) ? 'rotate-90' : ''" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5l8 7-8 7z"/></svg>
            </IconButton>
            <!-- Le NOM filtre la liste sur ce module (ce que faisait l'ancienne page module). -->
            <button class="flex min-w-0 flex-1 items-center gap-1.5 text-left font-semibold" :title="m.name" @click="openModule(m.id)">
              <svg class="w-4 h-4 text-warning shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
              <span class="truncate">{{ m.name }}</span>
            </button>
            <!-- Créer une SECTION (le document source) : le geste qui manquait à
                 l'interface — le CRUD existait côté serveur sans qu'aucun écran ne l'appelle. -->
            <IconButton size="sm" class="shrink-0" label="Ajouter une section dans ce module" @click.stop="ouvrirCreationSpec(m.id)">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9zM14 3v6h6M12 12v6M9 15h6"/></svg>
            </IconButton>
            <IconButton size="sm" class="shrink-0" label="Ajouter un cas dans ce module" @click.stop="goCaseNew(m.id)">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
            </IconButton>
            <IconButton size="sm" class="shrink-0 opacity-0 group-hover:opacity-100" variant="danger" label="Supprimer ce module" @click.stop="deleteModule(m)">
              <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 7h12M9 7V5a1 1 0 011-1h4a1 1 0 011 1v2m-7 0v11a2 2 0 002 2h4a2 2 0 002-2V7"/></svg>
            </IconButton>
          </div>
          <template v-if="expanded.includes(m.id)">
            <!-- Le NOM filtre la liste sur cette spécification (comportement d'origine) ;
                 l'icône de droite ouvre sa FICHE — le document lui-même. Deux gestes distincts
                 pour deux intentions distinctes : « montre-moi ses cas » et « montre-moi ce
                 qu'elle dit ». -->
            <div v-for="g in groupsOf(m.id)" :key="g.id"
                 class="group/spec flex w-full items-center gap-1.5 rounded-md pl-7 pr-1.5 py-1.5 hover:bg-accent/40 text-sm"
                 :class="activeGroupId === g.id ? 'text-primary bg-primary/10' : 'text-primary/90'">
              <button class="flex min-w-0 flex-1 items-center gap-1.5 text-left" :title="g.title" @click="openSpec(g.id)">
                <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
                <span class="truncate">{{ g.title }}</span>
              </button>
              <IconButton size="sm" class="shrink-0 opacity-0 group-hover/spec:opacity-100"
                          label="Ouvrir la section (le document)" @click.stop="ouvrirFicheSpec(g.id)">
                <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9zM14 3v6h6M8 13h8M8 17h5"/></svg>
              </IconButton>
            </div>
          </template>
        </template>
      </div>
      </template>

      <!-- Contexte « Exécutions et résultats de test » : actions run/plan + filtres -->
      <template v-else-if="isActive('exec')">
      <div class="px-3 pb-3 flex flex-col gap-2">
        <Button variant="primary" class="w-full" @click="goRoute('run-new')">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          Ajouter une exécution
        </Button>
        <Button variant="primary" class="w-full" @click="goRoute('plan-new')">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>
          Ajouter un plan
        </Button>
      </div>
      <div class="px-3.5 pb-4 space-y-3 text-sm">
        <label class="block">
          <span class="text-xs text-muted-foreground">Grouper par</span>
          <select :value="execGroup" @change="setExecQuery('group', ($event.target as HTMLSelectElement).value)"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-2 py-1.5">
            <option value="month">Mois</option>
            <option value="milestone" disabled>Jalon (à venir)</option>
            <option value="assignee" disabled>Assigné à (à venir)</option>
          </select>
        </label>
        <label class="block">
          <span class="text-xs text-muted-foreground">Trier par</span>
          <select :value="execSort" @change="setExecQuery('sort', ($event.target as HTMLSelectElement).value)"
                  class="mt-1 w-full rounded-md bg-surface-raised border border-border px-2 py-1.5">
            <option value="date">Date</option>
            <option value="name">Nom</option>
            <option value="pass">% de réussite</option>
          </select>
        </label>
      </div>
      </template>
    </aside>

    <div class="flex-1 min-w-0 overflow-y-auto">
      <slot v-if="fullBleed" />
      <div v-else class="mx-auto max-w-6xl p-6 md:p-8"><slot /></div>
    </div>

    <!-- ════════ Création d'un module (TestRail « Add Section », thème sombre) — modale UNIQUE ════════ -->
    <Modal :open="mc.open.value" title="Nouveau module"
           subtitle="Un module regroupe des cas de test par domaine fonctionnel de l'application."
           @close="mc.close()">
      <form id="form-create-module" class="space-y-3" @submit.prevent="submitModule">
        <label class="block">
          <span class="text-sm font-medium">Nom <span class="text-destructive">*</span></span>
          <input v-model="nm.name" placeholder="ex. Facturation" autofocus
                 class="mt-1 h-9 w-full rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />
        </label>
        <label class="block">
          <span class="text-sm font-medium">Description <span class="text-muted-foreground">(facultatif)</span></span>
          <textarea v-model="nm.description" rows="3" placeholder="À quoi sert ce module ?"
                    class="mt-1 w-full rounded-md border border-border bg-surface-raised px-3 py-2 text-sm outline-none focus:border-primary/50" />
        </label>
        <p v-if="moduleError" class="text-sm text-destructive">{{ moduleError }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="mc.close()">Annuler</Button>
        <Button type="submit" form="form-create-module" variant="primary" :loading="creatingModule" :disabled="!nm.name.trim()">Créer le module</Button>
      </template>
    </Modal>

    <!-- ════════ Création d'une SECTION ou SOUS-SECTION (décision 0022 ; migration 28) ════════ -->
    <Modal :open="sc.open.value" :title="specModalTitle"
           subtitle="Un document décrivant une fonctionnalité. Il servira à écrire un ou plusieurs cas de test."
           @close="sc.close()">
      <form id="form-create-spec" class="space-y-3" @submit.prevent="submitSpec">
        <label class="block">
          <span class="text-sm font-medium">Titre <span class="text-destructive">*</span></span>
          <input v-model="nouvelleSpec.title" placeholder="ex. Déclaration d'un sinistre client" autofocus
                 class="mt-1 h-9 w-full rounded-md border border-border bg-surface-raised px-3 text-sm outline-none focus:border-primary/50" />
        </label>
        <p class="text-sm text-muted-foreground">
          Rien n'est généré ni dépensé à la création : vous rédigerez le document à l'étape
          suivante, et la génération restera un geste explicite.
        </p>
        <p v-if="specError" class="text-sm text-destructive">{{ specError }}</p>
      </form>
      <template #footer>
        <Button type="button" variant="secondary" @click="sc.close()">Annuler</Button>
        <Button type="submit" form="form-create-spec" variant="primary" :loading="creatingSpec" :disabled="!nouvelleSpec.title.trim()">{{ sc.parentGroupId.value ? 'Créer la sous-section' : 'Créer la section' }}</Button>
      </template>
    </Modal>
  </div>
</template>
