<script setup lang="ts">
// Liste des cas de test — disposition TestRail (palette sombre). Groupée par SECTION = MODULE.
// ⚠️ **Aucun statut ici** (consigne du porteur, 2026-08-06) : un cas de test n'EST pas
// passed/failed — seule une EXÉCUTION (un run précis) l'est. Le raccourci `c.statut` (dernier
// résultat, tous modes/campagnes confondus) restait affiché ici et laissait croire qu'un cas
// « a » un statut propre, alors que la vérité par campagne vit dans `test_result` et peut
// diverger d'une campagne à l'autre. Le statut ne s'affiche donc plus que dans les écrans
// d'EXÉCUTION (RunDetail, RunTestDetail, l'onglet Tests & Résultats d'un cas). Titre sans
// préfixe de classement.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, roleSuffisant, type CaseSummary, type GroupSummary, type ModuleSummary } from '../lib/api'
import { useSession } from '../lib/useSession'
import { useProjects } from '../lib/useProjects'
import { typeView } from '../lib/status'
import { useModuleCreate } from '../lib/useModuleCreate'
import { useSectionCreate } from '../lib/useSectionCreate'
import { cles, usePageCas, useModules, useGroupes } from '../lib/donnees'
import { useQueryClient } from '@tanstack/vue-query'
import {
  COLONNES_MASQUABLES, HAUTEUR_LIGNE, usePreferencesListe, type Colonne,
} from '../lib/preferencesListe'
import Button from '../components/ui/Button.vue'
import IconButton from '../components/ui/IconButton.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

const route = useRoute()
const router = useRouter()
const pid = computed(() => route.params.pid as string)
const { session } = useSession()
const { projectById } = useProjects()
const roleProjet = computed(() => projectById(pid.value)?.effective_role || session.value?.role || '')
const peutModifier = computed(() => roleSuffisant(roleProjet.value, 'testeur'))
const peutGenerer = computed(() => roleSuffisant(roleProjet.value, 'dev'))
const estAdmin = computed(() => roleProjet.value === 'admin')
const specFilter = computed(() => Number(route.query.spec) || null)

// Couche de données partagée (lot A, 2026-07-24) : cette page et le shell demandaient les mêmes
// modules et les mêmes cas, chacun de son côté, à chaque navigation. Un seul cache désormais.
const { data: modulesData, isLoading: chargeModules } = useModules(pid)
const modules = computed(() => modulesData.value ?? [])
// Sections/Sous-sections (migration 28) : chargées à PART des cas, pour que celles encore VIDES
// (qu'on vient de créer inline, "Ajouter une section"/"Ajouter une sous-section") apparaissent
// quand même — dériver uniquement des cas présents (ancien comportement) les aurait rendues
// invisibles tant qu'aucun cas n'y est encore rangé.
const { data: groupsData } = useGroupes(pid)
const groups = computed(() => groupsData.value ?? [])
// Chargement seulement au PREMIER affichage : une revalidation de fond ne doit pas remplacer la
// liste par un squelette — l'écran doit rester stable sous les yeux de celui qui le lit.
const loading = computed(() => (chargeModules.value || chargeCas.value)
                               && !modulesData.value && !casesData.value)
const collapsed = ref<number[]>([])
const qc = useQueryClient()

// ── Création d'un module (modale partagée, rendue par CasesShell) ──────────────
// On ne fait que DÉCLENCHER l'ouverture : la modale unique vit dans le shell. ⚠️ Le watcher sur
// `createdAt` a disparu — la création invalide désormais le cache du projet, donc cette liste se
// rafraîchit d'elle-même. C'est exactement la plomberie que la couche de données remplace.
const { openFor: openCreateModule } = useModuleCreate()
// ── Création d'une Section/Sous-section (modale partagée, rendue par CasesShell) ──────────────
// Même patron que les modules : la modale unique vit dans le shell, ici on ne fait que déclencher
// son ouverture. Placé INLINE sous chaque module/Section dans la liste — à l'endroit exact où
// TestRail les affiche (consigne du porteur, 2026-08-06), plus dans la barre latérale ambiguë.
const sc = useSectionCreate()
function ajouterSection(moduleId: number) { sc.openFor(moduleId) }
function ajouterSousSection(moduleId: number, parentGroupId: number) { sc.openFor(moduleId, parentGroupId) }

// ── Glisser-déposer : déplacer/copier un cas, réorganiser les Sections (étape 2bis) ────────────
// ⚠️ Scope volontairement DANS LE MODULE COURANT (décision du plan) — pas de choix de module,
// une Section/sous-section n'existe que sous un module précis. Remplace le menu ⋮ livré à l'étape
// 2 (le porteur l'a comparé à de vraies captures TestRail : chez eux c'est un vrai glisser-
// déposer natif, poignée par ligne + petit menu AU POINT DE DÉPÔT). Le backend ne change pas —
// `api.deplacerCas`/`copierCas`/`deplacerGroupe` sont les mêmes qu'avant, seul le déclenchement
// change. Le réordonnancement (position au sein d'une même Section) reste HORS scope : non
// demandé, et `case_group` n'a aujourd'hui aucun moyen de le piloter par glisser-déposer.
const TYPE_CAS = 'application/x-tp-case'
const TYPE_SECTION = 'application/x-tp-section'

// Menu flottant qui apparaît AU POINT DE DÉPÔT (comme TestRail) quand on lâche sans modificateur
// clavier — Ctrl/Cmd ou Maj agissent directement SANS jamais faire apparaître ce menu.
const menuDepot = ref<{
  x: number; y: number; kind: 'cas' | 'section'; id: number; cibleGroupId: number | null
} | null>(null)
function fermerMenuDepot() { menuDepot.value = null }

const survolSection = ref<number | null>(null)
const survolModule = ref<number | null>(null)

function onDragStartCas(event: DragEvent, caseId: number) {
  event.dataTransfer?.setData(TYPE_CAS, String(caseId))
}
function onDragStartSection(event: DragEvent, groupId: number | null) {
  if (groupId == null) return
  event.dataTransfer?.setData(TYPE_SECTION, String(groupId))
}

// Une Section/sous-section accepte les DEUX types (un cas à ranger, une autre Section à imbriquer
// dessous) — d'où `.prevent` inconditionnel côté template. Un en-tête de MODULE, lui, n'accepte
// qu'une Section (pour la repromouvoir au premier niveau) : un cas ne peut pas atterrir
// directement sur un module, il lui faut toujours une Section.
function onDragOverModule(event: DragEvent) {
  if (event.dataTransfer?.types.includes(TYPE_SECTION)) event.preventDefault()
}

// Surbrillance de la cible survolée — « Sans section » (group_id null, cas orphelins) n'est pas
// une vraie Section : elle n'accepte jamais de dépôt.
function onDragEnterSection(event: DragEvent, groupId: number | null) {
  if (groupId == null) return
  if (event.dataTransfer?.types.includes(TYPE_CAS) || event.dataTransfer?.types.includes(TYPE_SECTION)) {
    survolSection.value = groupId
  }
}
function onDragLeaveSection(groupId: number | null) {
  if (groupId != null && survolSection.value === groupId) survolSection.value = null
}
function onDragEnterModule(event: DragEvent, moduleId: number) {
  if (event.dataTransfer?.types.includes(TYPE_SECTION)) survolModule.value = moduleId
}
function onDragLeaveModule(moduleId: number) {
  if (survolModule.value === moduleId) survolModule.value = null
}

function ouvrirMenuDepot(event: DragEvent, kind: 'cas' | 'section', id: number, cibleGroupId: number | null) {
  const LARGEUR = 230
  const HAUTEUR = 150
  menuDepot.value = {
    x: Math.min(event.clientX, window.innerWidth - LARGEUR - 8),
    y: Math.min(event.clientY, window.innerHeight - HAUTEUR - 8),
    kind, id, cibleGroupId,
  }
}

function onDropSection(event: DragEvent, cibleGroupId: number | null) {
  event.preventDefault()
  survolSection.value = null
  if (cibleGroupId == null) return
  const dt = event.dataTransfer
  if (!dt) return
  if (dt.types.includes(TYPE_CAS)) {
    const caseId = Number(dt.getData(TYPE_CAS))
    if (!caseId) return
    if (event.ctrlKey || event.metaKey) { deplacerCasVers(caseId, cibleGroupId); return }
    if (event.shiftKey) { copierCasVers(caseId, cibleGroupId); return }
    ouvrirMenuDepot(event, 'cas', caseId, cibleGroupId)
  } else if (dt.types.includes(TYPE_SECTION)) {
    const groupId = Number(dt.getData(TYPE_SECTION))
    if (!groupId || groupId === cibleGroupId) return
    if (event.ctrlKey || event.metaKey) { deplacerGroupeVers(groupId, cibleGroupId); return }
    ouvrirMenuDepot(event, 'section', groupId, cibleGroupId)
  }
}

function onDropModule(event: DragEvent) {
  event.preventDefault()
  survolModule.value = null
  const dt = event.dataTransfer
  if (!dt?.types.includes(TYPE_SECTION)) return
  const groupId = Number(dt.getData(TYPE_SECTION))
  if (!groupId) return
  // Promotion au premier niveau : `cibleGroupId: null` = « aucun parent ».
  if (event.ctrlKey || event.metaKey) { deplacerGroupeVers(groupId, null); return }
  ouvrirMenuDepot(event, 'section', groupId, null)
}

async function deplacerCasVers(caseId: number, groupId: number) {
  try {
    await api.deplacerCas(caseId, groupId)
    await qc.invalidateQueries({ queryKey: cles.projet(pid.value) })
  } catch (e: any) {
    messageLot.value = e?.message || 'Déplacement impossible.'
  }
}
async function copierCasVers(caseId: number, groupId: number) {
  try {
    await api.copierCas(caseId, groupId)
    await qc.invalidateQueries({ queryKey: cles.projet(pid.value) })
  } catch (e: any) {
    messageLot.value = e?.message || 'Copie impossible.'
  }
}
async function deplacerGroupeVers(groupId: number, parentGroupId: number | null) {
  try {
    await api.deplacerGroupe(groupId, parentGroupId)
    await qc.invalidateQueries({ queryKey: cles.projet(pid.value) })
  } catch (e: any) {
    messageLot.value = e?.message || 'Déplacement impossible.'
  }
}

// Boutons du menu flottant — lisent `menuDepot` avant de le fermer, sinon la cible a disparu.
async function menuDepotDeplacer() {
  const m = menuDepot.value
  if (!m) return
  fermerMenuDepot()
  if (m.kind === 'cas') await deplacerCasVers(m.id, m.cibleGroupId!)
  else await deplacerGroupeVers(m.id, m.cibleGroupId)
}
async function menuDepotCopier() {
  const m = menuDepot.value
  if (!m || m.kind !== 'cas') return
  fermerMenuDepot()
  await copierCasVers(m.id, m.cibleGroupId!)
}

// Tri et filtre CÔTÉ CLIENT (préférences de lecture, pas de rechargement).
const filterStatus = ref('')  // '' = tous

// ── Préférences d'affichage, conservées PAR PROJET (lot C) ───────────────────
// Densité, colonnes et tri sont des préférences de LECTURE : elles n'ont rien à faire dans la
// couche de données (personne d'autre n'est concerné par la densité que je choisis).
const { prefs, reinitialiser, estModifie } = usePreferencesListe(() => pid.value)
const sortKey = computed({
  get: () => prefs.value.tri,
  set: (v: 'id' | 'title' | 'status') => { prefs.value.tri = v },
})
function colonneVisible(c: Colonne) { return prefs.value.colonnes.includes(c) }
function basculerColonne(c: Colonne) {
  prefs.value.colonnes = colonneVisible(c)
    ? prefs.value.colonnes.filter((x) => x !== c)
    : [...prefs.value.colonnes, c]
}
const menuColonnes = ref(false)

// Libellés MÉTIER de la priorité : `high` ne s'affiche jamais tel quel (§8 du brief).
const PRIORITE: Record<string, string> = { high: 'Haute', medium: 'Moyenne', low: 'Basse' }

// ── RECHERCHE ────────────────────────────────────────────────────────────────
// Instantanée et côté client : les cas du projet sont déjà en cache, un aller-retour serveur
// n'apporterait qu'une latence. Elle porte sur ce qu'on lit à l'écran — titre, identifiant,
// module, spécification : chercher « C12 » ou « sinistre » doit marcher pareil.
const recherche = ref('')

// ⚠️ La recherche et le filtre partent au SERVEUR, avec la pagination (2026-07-24). Appliqués
// côté navigateur, ils ne porteraient que sur la page chargée : chercher un cas de la page 3
// répondrait « aucun résultat », et l'utilisateur conclurait qu'il n'existe pas.
const PAR_PAGE = 100
const pageDemandee = ref(PAR_PAGE)
const requeteServeur = computed(() => ({
  q: recherche.value.trim(), statut: filterStatus.value, limit: pageDemandee.value,
}))
const { data: casesData, isLoading: chargeCas } = usePageCas(pid, requeteServeur)
const cases = computed(() => casesData.value?.items ?? [])
const totalCas = computed(() => casesData.value?.total ?? 0)
const resteACharger = computed(() => Math.max(0, totalCas.value - cases.value.length))
function chargerPlus() { pageDemandee.value += PAR_PAGE }
// Revenir au premier lot dès que le filtre change : garder 400 lignes chargées en changeant de
// recherche ferait payer un temps de réponse sans rapport avec ce qu'on demande.
watch([recherche, filterStatus, pid], () => { pageDemandee.value = PAR_PAGE })

// ── SÉLECTION MULTIPLE ───────────────────────────────────────────────────────
const selection = ref<number[]>([])
function estSelectionne(id: number) { return selection.value.includes(id) }
function basculer(id: number) {
  selection.value = estSelectionne(id)
    ? selection.value.filter((x) => x !== id) : [...selection.value, id]
}
function toutSelectionner(ids: number[], coche: boolean) {
  selection.value = coche
    ? [...new Set([...selection.value, ...ids])]
    : selection.value.filter((x) => !ids.includes(x))
}
// ⚠️ La sélection est vidée quand la liste change de contenu (filtre, recherche, projet) :
// garder des cases cochées invisibles ferait agir sur ce qu'on ne voit plus.
watch([recherche, filterStatus, pid, specFilter], () => { selection.value = [] })

// Le statut vient du SERVEUR (2026-07-24) : c'est la même valeur qui sert à filtrer et à
// afficher, donc elles ne peuvent pas se contredire.
function statusOf(c: CaseSummary) { return c.statut }

// Cases visibles : filtrées par spécification (arbre) PUIS par statut (barre d'outils).
// Seul le filtre par SPÉCIFICATION reste local : il vient de l'arbre et ne change pas la
// requête. Recherche et statut, eux, sont déjà appliqués par le serveur.
const visibleCases = computed(() =>
  specFilter.value ? cases.value.filter((c) => c.group_id === specFilter.value) : cases.value)

function sortRows(rows: CaseSummary[]): CaseSummary[] {
  const copy = [...rows]
  if (sortKey.value === 'title') copy.sort((a, b) => a.title.localeCompare(b.title))
  else if (sortKey.value === 'status') copy.sort((a, b) => statusOf(a).localeCompare(statusOf(b)))
  else copy.sort((a, b) => a.id - b.id)
  return copy
}

// Sections = modules avec leurs cas visibles. On MONTRE les modules vides quand aucun filtre n'est
// actif — sinon un module qu'on vient de créer resterait invisible (et l'écran mentirait sur la
// structure). Sous un filtre (spec/statut), on masque au contraire ce qui n'a rien à montrer.
const sections = computed(() => {
  const filtering = !!specFilter.value || !!filterStatus.value
  return modules.value
    .map((m) => {
      const rows = sortRows(visibleCases.value.filter((c) => c.module_id === m.id))
      return { module: m, rows, groupes: groupesDeModule(m.id, rows) }
    })
    .filter((s) => !filtering || s.rows.length > 0)
})

// Sous-groupe les cas d'un module par SECTION → SOUS-SECTION (migration 28, une seule profondeur,
// parité TestRail) — chacune vue comme un dossier qui contient des cas et, pour une Section, des
// sous-dossiers. ⚠️ Construit depuis `groups` (TOUTES les Sections du module, cas ou pas), pas
// depuis les seuls cas présents : une Section/Sous-section fraîchement créée, encore vide, doit
// apparaître tout de suite pour qu'on puisse y ranger un cas — la dériver des cas la rendrait
// invisible jusqu'à ce qu'elle en porte un.
interface GroupeSection {
  group_id: number | null; group_title: string; rows: CaseSummary[]; sousSections: GroupeSection[]
}
function groupesDeModule(moduleId: number, rows: CaseSummary[]): GroupeSection[] {
  const groupesDuModule = groups.value.filter((g) => g.module_id === moduleId)
  const parGroupe = new Map<number, CaseSummary[]>()
  const orphelins: CaseSummary[] = []
  for (const c of rows) {
    if (c.group_id != null && groupesDuModule.some((g) => g.id === c.group_id)) {
      const arr = parGroupe.get(c.group_id) ?? []
      arr.push(c)
      parGroupe.set(c.group_id, arr)
    } else {
      orphelins.push(c)
    }
  }
  const versGroupeSection = (g: GroupSummary): GroupeSection => ({
    group_id: g.id, group_title: g.title, rows: parGroupe.get(g.id) ?? [], sousSections: [],
  })
  const noeuds = groupesDuModule
    .filter((g) => g.parent_group_id == null)
    .map((g) => {
      const noeud = versGroupeSection(g)
      noeud.sousSections = groupesDuModule
        .filter((sg) => sg.parent_group_id === g.id)
        .map(versGroupeSection)
      return noeud
    })
  // Cas orphelins (import, résidu — `CaseRepo.create` auto-enveloppe normalement TOUJOURS un cas
  // dans sa propre Section) : un groupe « Sans section » plutôt que de disparaître en silence.
  if (orphelins.length) {
    noeuds.push({ group_id: null, group_title: 'Sans section', rows: orphelins, sousSections: [] })
  }
  return noeuds
}

// Pliage PAR SECTION, distinct du pliage par module (`collapsed`) : une clé composite évite toute
// collision entre un id de module et un id de case_group, qui viennent de séquences différentes.
const collapsedGroups = ref<string[]>([])
const groupeASupprimer = ref<GroupeSection | null>(null)
const suppressionGroupe = ref(false)
function toggleGroup(moduleId: number, groupId: number | null) {
  const cle = `${moduleId}:${groupId}`
  collapsedGroups.value = collapsedGroups.value.includes(cle)
    ? collapsedGroups.value.filter((x) => x !== cle) : [...collapsedGroups.value, cle]
}
function groupCollapsed(moduleId: number, groupId: number | null) {
  return collapsedGroups.value.includes(`${moduleId}:${groupId}`)
}

function demanderSuppressionGroupe(groupe: GroupeSection) {
  if (groupe.group_id == null) return
  groupeASupprimer.value = groupe
}

async function supprimerGroupe() {
  const groupe = groupeASupprimer.value
  if (!groupe?.group_id) return
  suppressionGroupe.value = true
  messageLot.value = ''
  try {
    await api.deleteGroup(groupe.group_id)
    groupeASupprimer.value = null
    messageLot.value = `La section « ${groupe.group_title} » a été supprimée.`
    await qc.invalidateQueries({ queryKey: cles.projet(pid.value) })
  } catch (e: any) {
    groupeASupprimer.value = null
    messageLot.value = e?.message || 'Suppression de la section impossible.'
  } finally {
    suppressionGroupe.value = false
  }
}

// « Ajouter un cas » INLINE sous une Section/sous-section — le module ET la Section d'où on
// clique sont pré-sélectionnés (2026-09-11, parité TestRail : « Add Test Case » se lance depuis
// une Section déjà ouverte, le cas y atterrit directement). Une fonction LOCALE — la vérification
// de types réelle, mise en place le 2026-08-06, a attrapé l'appel à une fonction du même nom qui
// n'existait QUE dans CasesShell.vue, jamais ici.
function goCaseNew(moduleId: number, groupId?: number | null) {
  router.push({ name: 'case-manual', params: { pid: pid.value },
                query: { module: String(moduleId), ...(groupId ? { section: String(groupId) } : {}) } })
}

// Nombre de colonnes RÉELLEMENT affichées (checkbox + titre + chevron sont fixes, le reste
// dépend des préférences) — la ligne d'en-tête de Section doit couvrir exactement ce nombre,
// ni plus (bord qui dépasse) ni moins (colonnes désalignées avec le tableau).
const colonnesAffichees = computed(() =>
  3 + (colonneVisible('id') ? 1 : 0)
    + (colonneVisible('type') ? 1 : 0) + (colonneVisible('priorite') ? 1 : 0))

const activeSpecTitle = computed(() => {
  if (!specFilter.value) return null
  return cases.value.find((c) => c.group_id === specFilter.value)?.group_title || null
})

function toggle(mid: number) {
  collapsed.value = collapsed.value.includes(mid)
    ? collapsed.value.filter((x) => x !== mid) : [...collapsed.value, mid]
}
function openCase(id: number) {
  router.push({ name: 'case-detail', params: { pid: pid.value, id: String(id) } })
}
function comingSoon(what: string) { window.alert(`${what} — à venir.`) }

// Renommer un module (« Éditer la section »). Prompt simple : une seule valeur, pas besoin d'une
// modale. Le serveur refuse un nom déjà pris (409) — on remonte le message.
async function renameSection(m: ModuleSummary) {
  const nom = window.prompt('Renommer le module', m.name)
  if (!nom || !nom.trim() || nom.trim() === m.name) return
  try {
    await api.renameModule(m.id, nom.trim())
    // Renommage : ponctuel et sans mutation dédiée — on périme explicitement les modules.
    await qc.invalidateQueries({ queryKey: cles.modules(pid.value) })
  } catch (e: any) {
    window.alert(e?.message || 'Renommage impossible.')
  }
}

// Barre d'icônes du haut. « Importer » retiré (décision porteur) ; « Exporter » branché (CSV).
const topIcons = [
  { d: 'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3', t: 'Exporter (CSV)' },
]
function topAction(t: string) {
  if (t.startsWith('Exporter')) return exportCsv()
  comingSoon(t)
}

// Export CSV des cas visibles — universel (Excel, partage avec la QA non technique). Côté client :
// les données sont déjà chargées, aucun aller-retour serveur. Un champ contenant `;`/`"`/saut de
// ligne est échappé (guillemets doublés) — sinon le CSV se décale silencieusement.
function csvCell(v: unknown): string {
  const s = String(v ?? '')
  return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}
function exportCsv() {
  // ⚠️ Pas de colonne Statut : un cas de test n'a pas de statut propre, seule une exécution en a
  // un (consigne du porteur, 2026-08-06).
  const entetes = ['ID', 'Titre', 'Module', 'Type', 'Priorité']
  const lignes = visibleCases.value.map((c) => [
    `C${c.id}`, c.title, c.module || '', typeView(c.type).label, c.priority || '',
  ].map(csvCell).join(';'))
  // BOM UTF-8 : sans lui, Excel lit « é » de travers.
  const contenu = '﻿' + [entetes.join(';'), ...lignes].join('\r\n')
  const blob = new Blob([contenu], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `cas-de-test-${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
function goRunNew() { router.push({ name: 'run-new', params: { pid: pid.value } }) }

// ── ACTIONS EN LOT ───────────────────────────────────────────────────────────
// Le geste que ce lot vise : 20 cas cochés, une action. Chaque action rend un COMPTE RENDU
// (`traites` / `ignores`) — un cas peut avoir disparu entre l'affichage et le clic, et le taire
// ferait croire à un succès complet.
const actionEnCours = ref(false)
const messageLot = ref('')

function bilan(r: { traites: number; ignores: number }, verbe: string) {
  messageLot.value = r.ignores
    ? `${r.traites} cas ${verbe}, ${r.ignores} ignoré(s) — ils n'existaient plus.`
    : `${r.traites} cas ${verbe}.`
}

async function prioriteEnLot(priority: string) {
  actionEnCours.value = true
  messageLot.value = ''
  try {
    bilan(await api.prioriteEnLot(selection.value, priority), 'mis à jour')
    await qc.invalidateQueries({ queryKey: cles.cas(pid.value) })
    selection.value = []
  } catch (e: any) {
    messageLot.value = e?.message || 'Action impossible.'
  } finally {
    actionEnCours.value = false
  }
}

async function supprimerEnLot() {
  const n = selection.value.length
  if (!window.confirm(
    `Supprimer ${n} cas de test ?\n\nRien n'est détruit : ils partent à la corbeille et `
    + `restent restaurables.`)) return
  actionEnCours.value = true
  messageLot.value = ''
  try {
    bilan(await api.supprimerEnLot(selection.value), 'supprimés')
    await qc.invalidateQueries({ queryKey: cles.projet(pid.value) })
    selection.value = []
  } catch (e: any) {
    messageLot.value = e?.message || 'Suppression impossible.'
  } finally {
    actionEnCours.value = false
  }
}

</script>

<template>
  <div>
    <!-- BARRE D'ACTIONS EN LOT — n'apparaît QUE lorsqu'il y a une sélection.
         L'afficher en permanence encombrerait un écran déjà dense de boutons inutilisables :
         les actions de masse se révèlent au moment où elles ont un sens. -->
    <div v-if="selection.length"
         class="sticky top-0 z-20 flex flex-wrap items-center gap-3 border-b border-primary/30 bg-primary/10 px-6 py-2.5 text-sm backdrop-blur">
      <span class="font-semibold">{{ selection.length }} cas sélectionné{{ selection.length > 1 ? 's' : '' }}</span>
      <span class="text-muted-foreground">Priorité :</span>
      <button v-for="p in ['high', 'medium', 'low']" :key="p"
              class="text-primary hover:underline disabled:opacity-50" :disabled="actionEnCours"
              @click="prioriteEnLot(p)">{{ PRIORITE[p] }}</button>
      <span class="text-muted-foreground/50">·</span>
      <button v-if="estAdmin" class="text-destructive hover:underline disabled:opacity-50" :disabled="actionEnCours"
              @click="supprimerEnLot">Supprimer</button>
      <span class="flex-1"></span>
      <button class="text-muted-foreground hover:text-foreground" @click="selection = []">Tout décocher</button>
    </div>

    <!-- ⚠️ Le compte rendu vit HORS de la barre de sélection : celle-ci disparaît dès que
         l'action aboutit (la sélection est vidée), et le message s'effaçait donc à l'instant
         précis où il fallait le lire. « 18 traités, 2 ignorés » n'était jamais vu. -->
    <div v-if="messageLot"
         class="flex items-center gap-3 border-b border-border bg-surface-raised/70 px-6 py-2 text-sm">
      <span>{{ messageLot }}</span>
      <button class="text-muted-foreground hover:text-foreground" aria-label="Masquer le message"
              @click="messageLot = ''">✕</button>
    </div>

    <!-- En-tête -->
    <div class="flex items-center justify-between px-6 pt-6 pb-2">
      <h1 class="text-2xl font-semibold tracking-tight">Cas de test</h1>
      <div class="flex items-center gap-3.5 text-muted-foreground">
        <IconButton v-if="peutModifier" label="Nouveau module" @click="openCreateModule(pid)">
          <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><path d="M12 10v5M9.5 12.5h5"/></svg>
        </IconButton>
        <IconButton v-for="ic in topIcons" :key="ic.t" :label="ic.t" @click="topAction(ic.t)">
          <svg class="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path :d="ic.d"/></svg>
        </IconButton>
        <button v-if="peutGenerer" title="Générer des cas de test avec l'IA" class="grid place-items-center w-7 h-7 rounded-full bg-success/15 text-success hover:bg-success/25"
                @click="router.push({ name: 'case-new', params: { pid } })" aria-label="Générer des cas de test avec l'IA">
          <svg class="w-[15px] h-[15px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"><path d="M12 3l1.9 4.6L18.5 9l-4.6 1.9L12 15l-1.9-4.1L5.5 9l4.6-1.4z"/></svg>
        </button>
        <button v-if="peutModifier" title="Lancer une exécution (créer un run)" class="grid place-items-center w-[30px] h-[30px] rounded-full bg-success text-success-foreground hover:bg-success/90" @click="goRunNew" aria-label="Lancer une exécution (créer un run)">
          <svg class="w-[15px] h-[15px]" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
        </button>
      </div>
    </div>

    <!-- Barre d'outils secondaire — tri et filtre CÔTÉ CLIENT (les cas sont déjà chargés). -->
    <div class="flex items-center gap-4 px-6 py-2 border-y border-border bg-surface-raised/50 text-xs text-muted-foreground">
      <label class="flex items-center gap-1.5">Trier :
        <select v-model="sortKey" class="bg-transparent text-foreground border-b border-dotted border-muted-foreground outline-none cursor-pointer">
          <option value="id">ID</option>
          <option value="title">Titre</option>
          <option value="status">Statut</option>
        </select>
      </label>
      <label class="flex items-center gap-1.5">Filtre :
        <select v-model="filterStatus" class="bg-transparent text-foreground border-b border-dotted border-muted-foreground outline-none cursor-pointer">
          <option value="">Tous</option>
          <option value="passed">Passed</option>
          <option value="failed">Failed</option>
          <option value="retest">Retest</option>
          <option value="blocked">Blocked</option>
          <option value="untested">Untested</option>
        </select>
      </label>
      <!-- RECHERCHE : le geste le plus fréquent, donc le plus accessible. -->
      <label class="flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
        <input v-model="recherche" type="search" placeholder="Rechercher un cas…"
               aria-label="Rechercher un cas de test"
               class="w-52 bg-transparent text-foreground placeholder:text-muted-foreground/70 outline-none border-b border-dotted border-muted-foreground focus:border-primary" />
      </label>
      <label class="flex items-center gap-1.5">Densité :
        <select v-model="prefs.densite" class="bg-transparent text-foreground border-b border-dotted border-muted-foreground outline-none cursor-pointer">
          <option value="compacte">Compacte</option>
          <option value="normale">Normale</option>
          <option value="aeree">Aérée</option>
        </select>
      </label>
      <!-- COLONNES : on ne peut pas masquer le titre — une liste de cas sans lui ne montrerait
           plus rien. -->
      <div class="relative">
        <button class="hover:text-foreground" @click="menuColonnes = !menuColonnes">Colonnes ▾</button>
        <div v-if="menuColonnes" class="absolute z-30 mt-1 w-40 rounded-md border border-border bg-surface-overlay py-1 shadow-xl">
          <label v-for="col in COLONNES_MASQUABLES" :key="col.cle"
                 class="flex cursor-pointer items-center gap-2 px-3 py-1.5 hover:bg-accent/60">
            <input type="checkbox" :checked="colonneVisible(col.cle)" @change="basculerColonne(col.cle)" />
            <span class="text-foreground">{{ col.label }}</span>
          </label>
        </div>
      </div>
      <button v-if="estModifie()" class="hover:text-foreground underline" @click="reinitialiser">
        Réinitialiser l'affichage
      </button>
      <span class="flex-1"></span>
      <span v-if="activeSpecTitle" class="flex items-center gap-1.5 text-primary">
        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
        {{ activeSpecTitle }}
        <!-- Filtrer sur une spécification et pouvoir LIRE cette spécification sont deux besoins
             distincts : la liste montre ses cas, le lien montre le document dont ils sont nés. -->
        <RouterLink :to="{ name: 'spec-detail', params: { pid, id: String(specFilter) } }"
                    class="hover:underline" title="Ouvrir la spécification">voir le document</RouterLink>
        <RouterLink :to="{ name: 'cases', params: { pid } }" class="hover:text-foreground" title="Retirer le filtre">✕</RouterLink>
      </span>
    </div>

    <div class="px-6 pb-16">
      <div v-if="loading" class="space-y-2 pt-6">
        <div v-for="i in 3" :key="i" class="h-12 rounded-md bg-secondary animate-pulse"></div>
      </div>

      <div v-else-if="!sections.length" class="flex flex-col items-center gap-3 pt-16 text-center">
        <p class="text-sm text-muted-foreground">
          {{ specFilter || filterStatus ? 'Aucun cas de test ne correspond au filtre.' : 'Aucun module dans ce projet.' }}
        </p>
        <Button v-if="peutModifier && !specFilter && !filterStatus" variant="primary" @click="openCreateModule(pid)">Créer le premier module</Button>
      </div>

      <!-- ⚠️ On DIT ce qui est chargé sur le total : sans ce compte, une liste tronquée a l'air
           complète, et l'utilisateur conclut qu'un cas n'existe pas alors qu'il est page 3.
           Sous un filtre par Section, comparer au total du PROJET n'aurait aucun sens (mesuré le
           2026-08-05 : l'en-tête disait « 15 sur 15 » alors qu'un seul cas était affiché). -->
      <p v-if="!loading && specFilter" class="pt-4 text-xs text-muted-foreground">
        {{ visibleCases.length }} cas affiché{{ visibleCases.length > 1 ? 's' : '' }} pour cette section
      </p>
      <p v-else-if="!loading && totalCas" class="pt-4 text-xs text-muted-foreground">
        {{ cases.length }} cas affiché{{ cases.length > 1 ? 's' : '' }} sur {{ totalCas }}
      </p>

      <div v-for="s in sections" :key="s.module.id" class="mt-4">
        <!-- En-tête de section (module) — reçoit le dépôt d'une Section glissée (la repromeut au
             premier niveau, `parent_group_id: null`) ; un cas seul ne peut pas y atterrir
             directement, il lui faut toujours une Section (`onDragOverModule`). -->
        <div class="flex items-center gap-2.5 py-1.5 rounded"
             :class="survolModule === s.module.id ? 'bg-primary/10' : ''"
             @dragover="onDragOverModule" @dragenter="onDragEnterModule($event, s.module.id)"
             @dragleave="onDragLeaveModule(s.module.id)" @drop="onDropModule($event)">
          <button class="text-muted-foreground hover:text-foreground"
                  :aria-label="`${collapsed.includes(s.module.id) ? 'Déplier' : 'Replier'} le module ${s.module.name}`"
                  :aria-expanded="!collapsed.includes(s.module.id)"
                  @click="toggle(s.module.id)">
            <svg class="w-3.5 h-3.5 transition-transform" :class="collapsed.includes(s.module.id) ? '-rotate-90' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"/></svg>
          </button>
          <span class="font-bold italic tracking-tight">{{ s.module.name }}</span>
          <span class="rounded-full bg-primary/15 text-primary text-xs font-semibold px-2.5 py-0.5 tabular-nums">{{ s.rows.length }}</span>
          <button v-if="peutModifier" class="text-muted-foreground hover:text-foreground" title="Renommer le module" @click="renameSection(s.module)" aria-label="Renommer le module">
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 013 3L7 19l-4 1 1-4z"/></svg>
          </button>
          <!-- « Ajouter une section », INLINE sous le module — à l'endroit où TestRail le place,
               plus dans la barre latérale ambiguë (retirée, 2026-08-06). -->
          <button v-if="peutModifier" class="ml-2 text-xs text-primary hover:underline" @click="ajouterSection(s.module.id)">
            + Ajouter une section
          </button>
        </div>

        <p v-if="!collapsed.includes(s.module.id) && !s.rows.length && !s.groupes.length"
           class="pl-8 py-2 text-xs italic text-subtle-foreground">
          Aucun cas dans ce module — générez-en avec l'IA ou ajoutez-en un.
        </p>

        <table v-if="!collapsed.includes(s.module.id) && (s.rows.length || s.groupes.length)" class="w-full border-collapse">
          <thead>
            <tr class="text-xs uppercase tracking-wider text-muted-foreground">
              <th class="w-8 py-2 pl-1">
                <!-- « Tout sélectionner » porte sur CETTE section, pas sur la liste entière :
                     cocher 400 cas invisibles d'un clic est un piège, pas un raccourci. -->
                <input v-if="peutModifier" type="checkbox" :aria-label="`Sélectionner les cas de ${s.module.name}`"
                       :checked="s.rows.length > 0 && s.rows.every((c) => estSelectionne(c.id))"
                       @change="toutSelectionner(s.rows.map((c) => c.id), ($event.target as HTMLInputElement).checked)" />
              </th>
              <th v-if="colonneVisible('id')" class="w-16 text-left font-semibold py-2 pl-3 relative">
                <span class="absolute left-0 top-1.5 bottom-1.5 w-[3px] rounded bg-primary"></span>ID
              </th>
              <th class="text-left font-semibold py-2 px-2.5">Titre</th>
              <th v-if="colonneVisible('type')" class="w-28 text-left font-semibold py-2 px-2.5">Type</th>
              <!-- Priorité à DROITE avec le statut : ce sont les colonnes qu'on balaie
                   verticalement, et un balayage se fait sur un bord aligné. -->
              <th v-if="colonneVisible('priorite')" class="w-24 text-right font-semibold py-2 px-2.5">Priorité</th>
              <th class="w-8"></th>
            </tr>
          </thead>
          <template v-for="g in s.groupes" :key="`${s.module.id}-${g.group_id}`">
            <!-- En-tête de SECTION (case_group = une user story, §9) — pliable indépendamment du
                 module. C'est le regroupement fait à la génération qui devient enfin VISIBLE dans
                 la liste, pas seulement accessible en filtrant (mesuré le 2026-08-05 : cliquer
                 une Section remplaçait toute la vue au lieu de la sous-titrer). -->
            <tbody>
              <!-- Poignée = draggable (glisser CETTE Section vers une autre) ; la ligne entière est
                   aussi une CIBLE de dépôt (un cas ou une autre Section peut y atterrir). « Sans
                   section » (group_id null, cas orphelins) n'est ni l'un ni l'autre — pas une
                   vraie Section à déplacer ou à recevoir. -->
              <tr class="group border-t border-border/60 bg-surface-raised/40"
                  :class="survolSection === g.group_id ? 'ring-1 ring-inset ring-primary/50' : ''"
                  @dragover="g.group_id ? $event.preventDefault() : undefined"
                  @dragenter="onDragEnterSection($event, g.group_id)"
                  @dragleave="onDragLeaveSection(g.group_id)"
                  @drop="onDropSection($event, g.group_id)">
                <td :colspan="colonnesAffichees" class="px-3" :class="HAUTEUR_LIGNE[prefs.densite]">
                  <div class="flex items-center gap-1.5">
                    <!-- Poignée = un <span> HTML, PAS l'<svg> lui-même : le glisser natif sur un
                         <svg> est peu fiable d'un moteur à l'autre (Chrome ignore `draggable`
                         sans `-webkit-user-drag: element`, absent par défaut). Toujours visible
                         (pas seulement au survol) — parité avec la vraie poignée TestRail. -->
                    <span v-if="g.group_id" draggable="true" @dragstart="onDragStartSection($event, g.group_id)"
                          class="shrink-0 cursor-grab text-muted-foreground/70 hover:text-muted-foreground"
                          title="Glisser pour déplacer cette section">
                      <svg class="w-3.5 h-3.5 pointer-events-none" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.3"/><circle cx="15" cy="6" r="1.3"/><circle cx="9" cy="12" r="1.3"/><circle cx="15" cy="12" r="1.3"/><circle cx="9" cy="18" r="1.3"/><circle cx="15" cy="18" r="1.3"/></svg>
                    </span>
                    <button class="flex items-center gap-1.5 text-left text-muted-foreground hover:text-foreground"
                            :aria-label="`${groupCollapsed(s.module.id, g.group_id) ? 'Déplier' : 'Replier'} la section ${g.group_title}`"
                            :aria-expanded="!groupCollapsed(s.module.id, g.group_id)"
                            @click="toggleGroup(s.module.id, g.group_id)">
                      <svg class="w-3 h-3 shrink-0 transition-transform" :class="groupCollapsed(s.module.id, g.group_id) ? '-rotate-90' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"/></svg>
                      <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
                      <span class="text-sm font-semibold text-primary/90">{{ g.group_title }}</span>
                      <span class="rounded-full bg-primary/15 text-primary text-xs font-semibold px-2 py-0.5 tabular-nums">{{ g.rows.length }}</span>
                    </button>
                    <RouterLink v-if="g.group_id" :to="{ name: 'spec-detail', params: { pid, id: String(g.group_id) } }"
                                class="text-xs text-muted-foreground hover:text-primary hover:underline"
                                title="Ouvrir la section (le document)">voir le document</RouterLink>
                    <IconButton v-if="estAdmin && g.group_id" size="sm" variant="danger"
                                class="ml-auto opacity-70 transition-opacity hover:opacity-100 focus:opacity-100"
                                :label="`Supprimer la section ${g.group_title}`"
                                @click.stop="demanderSuppressionGroupe(g)">
                      <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 7h12M9 7V5h6v2m-7 0 1 12h6l1-12"/></svg>
                    </IconButton>
                  </div>
                </td>
              </tr>
            </tbody>
            <tbody v-if="!groupCollapsed(s.module.id, g.group_id)">
              <tr v-for="c in g.rows" :key="c.id"
                  class="group border-t border-border/60 hover:bg-accent/30 cursor-pointer"
                  :class="estSelectionne(c.id) && 'bg-primary/10'"
                  @click="openCase(c.id)">
                <!-- ⚠️ `@click.stop` sur la case : sans lui, cocher ouvrirait aussi le cas — le
                     clic remonterait à la ligne. Sélectionner et ouvrir sont deux intentions. -->
                <td class="pl-1" :class="HAUTEUR_LIGNE[prefs.densite]" @click.stop>
                  <input v-if="peutModifier" type="checkbox" :aria-label="`Sélectionner ${c.title}`"
                         :checked="estSelectionne(c.id)" @change="basculer(c.id)" />
                </td>
                <td v-if="colonneVisible('id')" class="pl-3 font-bold tabular-nums whitespace-nowrap"
                    :class="HAUTEUR_LIGNE[prefs.densite]">C{{ c.id }}</td>
                <td class="px-2.5 text-primary group-hover:underline leading-snug"
                    :class="HAUTEUR_LIGNE[prefs.densite]">{{ c.title }}</td>
                <!-- `typeView` et jamais le code brut : « non_fonctionnel » à l'écran est une
                     valeur d'enum, pas un libellé (point unique de traduction, `status.ts`). -->
                <td v-if="colonneVisible('type')" class="px-2.5 text-muted-foreground"
                    :class="HAUTEUR_LIGNE[prefs.densite]">{{ typeView(c.type).label }}</td>
                <td v-if="colonneVisible('priorite')" class="px-2.5 text-right text-muted-foreground"
                    :class="HAUTEUR_LIGNE[prefs.densite]">{{ PRIORITE[c.priority] || c.priority }}</td>
                <!-- Poignée de glisser-déposer (parité TestRail, 2026-08-06) — remplace le menu ⋮
                     « Déplacer/copier vers… » : on attrape la ligne et on la lâche sur une Section. -->
                <td class="text-muted-foreground" :class="HAUTEUR_LIGNE[prefs.densite]" @click.stop>
                  <span draggable="true" @dragstart="onDragStartCas($event, c.id)"
                        class="inline-block cursor-grab text-muted-foreground/70 hover:text-muted-foreground"
                        title="Glisser vers une autre section" aria-label="Glisser ce cas vers une autre section" role="img">
                    <svg class="w-4 h-4 pointer-events-none" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.3"/><circle cx="15" cy="6" r="1.3"/><circle cx="9" cy="12" r="1.3"/><circle cx="15" cy="12" r="1.3"/><circle cx="9" cy="18" r="1.3"/><circle cx="15" cy="18" r="1.3"/></svg>
                  </span>
                </td>
              </tr>
              <!-- INLINE, sous la liste des cas de la Section — à l'endroit exact où TestRail les
                   place (consigne du porteur, 2026-08-06), plus dans la barre latérale. Pas de
                   « Ajouter une sous-section » sous une Section « Sans section » (g.group_id null,
                   cas orphelins — pas un vrai conteneur à sous-structurer). -->
              <tr v-if="g.group_id" class="border-t border-border/30">
                <td :colspan="colonnesAffichees" class="pl-9 py-1.5 text-xs" :class="HAUTEUR_LIGNE[prefs.densite]">
                  <button v-if="peutModifier" class="text-primary hover:underline" @click="goCaseNew(s.module.id, g.group_id)">Ajouter un cas</button>
                  <span v-if="peutModifier" class="text-muted-foreground/50 mx-1.5">|</span>
                  <button v-if="peutModifier" class="text-primary hover:underline" @click="ajouterSousSection(s.module.id, g.group_id)">Ajouter une sous-section</button>
                </td>
              </tr>
            </tbody>

            <!-- SOUS-SECTIONS (migration 28) — une profondeur, indentées sous leur Section. -->
            <template v-for="sg in g.sousSections" :key="`${s.module.id}-${g.group_id}-${sg.group_id}`">
              <tbody v-if="!groupCollapsed(s.module.id, g.group_id)">
                <tr class="group border-t border-border/60 bg-surface-raised/25"
                    :class="survolSection === sg.group_id ? 'ring-1 ring-inset ring-primary/50' : ''"
                    @dragover.prevent @dragenter="onDragEnterSection($event, sg.group_id)"
                    @dragleave="onDragLeaveSection(sg.group_id)" @drop="onDropSection($event, sg.group_id)">
                  <td :colspan="colonnesAffichees" class="pl-9 px-3" :class="HAUTEUR_LIGNE[prefs.densite]">
                    <div class="flex items-center gap-1.5">
                      <span draggable="true" @dragstart="onDragStartSection($event, sg.group_id)"
                            class="shrink-0 cursor-grab text-muted-foreground/70 hover:text-muted-foreground"
                            title="Glisser pour déplacer cette sous-section">
                        <svg class="w-3.5 h-3.5 pointer-events-none" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.3"/><circle cx="15" cy="6" r="1.3"/><circle cx="9" cy="12" r="1.3"/><circle cx="15" cy="12" r="1.3"/><circle cx="9" cy="18" r="1.3"/><circle cx="15" cy="18" r="1.3"/></svg>
                      </span>
                      <button class="flex items-center gap-1.5 text-left text-muted-foreground hover:text-foreground"
                              :aria-label="`${groupCollapsed(s.module.id, sg.group_id) ? 'Déplier' : 'Replier'} la sous-section ${sg.group_title}`"
                              :aria-expanded="!groupCollapsed(s.module.id, sg.group_id)"
                              @click="toggleGroup(s.module.id, sg.group_id)">
                        <svg class="w-3 h-3 shrink-0 transition-transform" :class="groupCollapsed(s.module.id, sg.group_id) ? '-rotate-90' : ''" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M6 9l6 6 6-6"/></svg>
                        <svg class="w-3.5 h-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/></svg>
                        <span class="text-sm font-semibold text-primary/80">{{ sg.group_title }}</span>
                        <span class="rounded-full bg-primary/15 text-primary text-xs font-semibold px-2 py-0.5 tabular-nums">{{ sg.rows.length }}</span>
                      </button>
                      <RouterLink :to="{ name: 'spec-detail', params: { pid, id: String(sg.group_id) } }"
                                  class="text-xs text-muted-foreground hover:text-primary hover:underline"
                                  title="Ouvrir la sous-section (le document)">voir le document</RouterLink>
                      <IconButton v-if="estAdmin" size="sm" variant="danger"
                                  class="ml-auto opacity-70 transition-opacity hover:opacity-100 focus:opacity-100"
                                  :label="`Supprimer la sous-section ${sg.group_title}`"
                                  @click.stop="demanderSuppressionGroupe(sg)">
                        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 7h12M9 7V5h6v2m-7 0 1 12h6l1-12"/></svg>
                      </IconButton>
                    </div>
                  </td>
                </tr>
              </tbody>
              <tbody v-if="!groupCollapsed(s.module.id, g.group_id) && !groupCollapsed(s.module.id, sg.group_id)">
                <tr v-for="c in sg.rows" :key="c.id"
                    class="group border-t border-border/60 hover:bg-accent/30 cursor-pointer"
                    :class="estSelectionne(c.id) && 'bg-primary/10'"
                    @click="openCase(c.id)">
                  <td class="pl-1" :class="HAUTEUR_LIGNE[prefs.densite]" @click.stop>
                    <input v-if="peutModifier" type="checkbox" :aria-label="`Sélectionner ${c.title}`"
                           :checked="estSelectionne(c.id)" @change="basculer(c.id)" />
                  </td>
                  <td v-if="colonneVisible('id')" class="pl-3 font-bold tabular-nums whitespace-nowrap"
                      :class="HAUTEUR_LIGNE[prefs.densite]">C{{ c.id }}</td>
                  <td class="px-2.5 text-primary group-hover:underline leading-snug"
                      :class="HAUTEUR_LIGNE[prefs.densite]">{{ c.title }}</td>
                  <td v-if="colonneVisible('type')" class="px-2.5 text-muted-foreground"
                      :class="HAUTEUR_LIGNE[prefs.densite]">{{ typeView(c.type).label }}</td>
                  <td v-if="colonneVisible('priorite')" class="px-2.5 text-right text-muted-foreground"
                      :class="HAUTEUR_LIGNE[prefs.densite]">{{ PRIORITE[c.priority] || c.priority }}</td>
                  <td class="text-muted-foreground" :class="HAUTEUR_LIGNE[prefs.densite]" @click.stop>
                    <span draggable="true" @dragstart="onDragStartCas($event, c.id)"
                          class="inline-block cursor-grab text-muted-foreground/70 hover:text-muted-foreground"
                          title="Glisser vers une autre section" aria-label="Glisser ce cas vers une autre section" role="img">
                      <svg class="w-4 h-4 pointer-events-none" viewBox="0 0 24 24" fill="currentColor"><circle cx="9" cy="6" r="1.3"/><circle cx="15" cy="6" r="1.3"/><circle cx="9" cy="12" r="1.3"/><circle cx="15" cy="12" r="1.3"/><circle cx="9" cy="18" r="1.3"/><circle cx="15" cy="18" r="1.3"/></svg>
                    </span>
                  </td>
                </tr>
                <!-- Pas de « Ajouter une sous-section » ici : une seule profondeur d'imbrication. -->
                <tr class="border-t border-border/30">
                  <td :colspan="colonnesAffichees" class="pl-14 py-1.5 text-xs" :class="HAUTEUR_LIGNE[prefs.densite]">
                    <button v-if="peutModifier" class="text-primary hover:underline" @click="goCaseNew(s.module.id, sg.group_id)">Ajouter un cas</button>
                  </td>
                </tr>
              </tbody>
            </template>
          </template>
        </table>
      </div>
      <div v-if="resteACharger" class="py-6 text-center">
        <Button variant="secondary" @click="chargerPlus">
          Charger {{ Math.min(resteACharger, 100) }} cas de plus
          <span class="text-muted-foreground">({{ resteACharger }} restants)</span>
        </Button>
      </div>
    </div>

    <ConfirmDialog
      :open="Boolean(groupeASupprimer)"
      title="Supprimer cette section ?"
      :message="groupeASupprimer?.rows.length || groupeASupprimer?.sousSections.length
        ? `La section « ${groupeASupprimer?.group_title || ''} » contient encore des cas ou des sous-sections. Déplacez ou supprimez d’abord son contenu.`
        : `La section vide « ${groupeASupprimer?.group_title || ''} » sera placée dans la corbeille.`"
      confirm-label="Supprimer la section"
      :busy="suppressionGroupe"
      :confirm-disabled="Boolean(groupeASupprimer?.rows.length || groupeASupprimer?.sousSections.length)"
      @confirm="supprimerGroupe"
      @cancel="groupeASupprimer = null"
    />

    <!-- ════════ Menu flottant AU POINT DE DÉPÔT (parité TestRail, étape 2bis) ════════
         N'apparaît que si le dépôt s'est fait SANS Ctrl/Cmd/Maj (ces touches agissent tout de
         suite, voir onDropSection/onDropModule) — un fond plein écran ferme le menu au clic
         extérieur, même patron que Modal.vue. -->
    <div v-if="menuDepot" class="fixed inset-0 z-40" @click="fermerMenuDepot" @contextmenu.prevent="fermerMenuDepot">
      <div class="absolute rounded-md border border-border bg-surface-overlay py-1 text-sm shadow-xl"
           :style="{ left: menuDepot.x + 'px', top: menuDepot.y + 'px' }" @click.stop>
        <template v-if="menuDepot.kind === 'cas'">
          <button class="block w-full whitespace-nowrap px-3 py-1.5 text-left hover:bg-accent/60" @click="menuDepotDeplacer">
            Déplacer ici (ctrl/cmd)
          </button>
          <button class="block w-full whitespace-nowrap px-3 py-1.5 text-left hover:bg-accent/60" @click="menuDepotCopier">
            Copier ici (maj)
          </button>
        </template>
        <!-- Une Section n'est jamais copiée ici : ça dupliquerait en cascade tous ses cas. -->
        <button v-else class="block w-full whitespace-nowrap px-3 py-1.5 text-left hover:bg-accent/60" @click="menuDepotDeplacer">
          Déplacer ici
        </button>
        <button class="block w-full whitespace-nowrap px-3 py-1.5 text-left text-muted-foreground hover:bg-accent/60" @click="fermerMenuDepot">
          Annuler
        </button>
      </div>
    </div>
  </div>
</template>
