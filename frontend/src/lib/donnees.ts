// LA COUCHE DE DONNÉES — un seul endroit qui sait charger, mettre en cache et invalider
// (lot A du plan de conception, 2026-07-24 — `docs/CONCEPTION.md` §1.2).
//
// ── Le problème qu'elle résout ────────────────────────────────────────────────────────────────
// 22 pages et composants appelaient l'API en direct, chacun avec son `ref()` et son `onMounted`.
// Conséquences mesurées à l'audit :
//   • le shell ET la page rechargeaient les MÊMES modules et les MÊMES cas à chaque navigation ;
//   • après une mutation, chacun rappelait `load()` à la main — un oubli et l'écran mentait ;
//   • deux écrans affichant la même donnée pouvaient diverger, sans que rien ne le signale.
//
// ── La règle ─────────────────────────────────────────────────────────────────────────────────
// **L'état SERVEUR ne se recopie jamais dans un état global.** Les données du serveur ne nous
// appartiennent pas : elles périment, d'autres les changent. Les stocker dans un `ref` partagé
// crée une seconde source de vérité, et la dérive entre les deux est le genre de bug qu'on ne
// débogue pas. Ici, la source de vérité reste le serveur ; ce module n'en tient qu'un CACHE, qui
// sait quand il est périmé.
//
// L'état purement CLIENT (le projet sélectionné, le dépliage de l'arbre, un filtre) n'est pas
// concerné : il n'a pas de source distante, il reste dans les composables locaux.
//
// ── Comment on s'en sert ─────────────────────────────────────────────────────────────────────
//   const { data: cas, isLoading } = useCas(pid)          // lecture : cache + revalidation
//   const creer = useCreerModule(pid)                     // écriture : invalide ce qu'il faut
//   await creer.mutateAsync({ name: 'Facturation' })      // les écrans concernés se rafraîchissent
//
// ⚠️ **Toute mutation DOIT déclarer ce qu'elle invalide.** C'est la seule discipline que cette
// couche exige, et c'est elle qui remplace les `load()` éparpillés. Une mutation qui n'invalide
// rien laisse l'écran afficher un état périmé — le défaut qu'on vient de supprimer.

import { computed, type MaybeRefOrGetter, toValue } from 'vue'
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import {
  api,
  type CaseSummary,
  type GroupSummary,
  type ModuleSummary,
  type ProjectSummary,
  type RunSummary,
} from './api'

// ── Les clés de cache ────────────────────────────────────────────────────────────────────────
// Hiérarchiques et dérivées d'un seul endroit : `cles.casDuProjet(3)` = ['projet', 3, 'cas'].
// Invalider `['projet', 3]` invalide donc TOUT ce qui dépend du projet 3, sans avoir à énumérer.
// Des clés écrites à la main dans chaque écran auraient fini par diverger d'une lettre — et une
// invalidation qui rate sa cible est silencieuse.
export const cles = {
  projets: () => ['projets'] as const,
  projet: (pid: Id) => ['projet', Number(toValue(pid))] as const,
  modules: (pid: Id) => ['projet', Number(toValue(pid)), 'modules'] as const,
  cas: (pid: Id) => ['projet', Number(toValue(pid)), 'cas'] as const,
  groupes: (pid: Id) => ['projet', Number(toValue(pid)), 'groupes'] as const,
  runs: (pid: Id) => ['projet', Number(toValue(pid)), 'runs'] as const,
  qualite: (pid: Id) => ['projet', Number(toValue(pid)), 'qualite'] as const,
  unCas: (id: Id) => ['cas', Number(toValue(id))] as const,
  unGroupe: (id: Id) => ['groupe', Number(toValue(id))] as const,
  unRun: (id: Id) => ['run', Number(toValue(id))] as const,
}

type Id = MaybeRefOrGetter<number | string>

/** Une requête n'est lancée que si son identifiant existe : pendant une transition de route,
 *  `pid` passe brièvement à `undefined` et une requête `/api/projects/undefined/...` partirait. */
function pret(id: Id) {
  return computed(() => {
    const v = toValue(id)
    return v !== undefined && v !== null && v !== '' && !Number.isNaN(Number(v))
  })
}

// ── Lectures ─────────────────────────────────────────────────────────────────────────────────

export function useProjets() {
  return useQuery<ProjectSummary[]>({ queryKey: cles.projets(), queryFn: () => api.listProjects() })
}

export function useModules(pid: Id) {
  return useQuery<ModuleSummary[]>({
    queryKey: computed(() => cles.modules(pid)),
    queryFn: () => api.listModules(toValue(pid)),
    enabled: pret(pid),
  })
}

/** Une PAGE de cas. Les options font partie de la CLÉ de cache : deux filtres différents sont
 *  deux jeux de données distincts, et les confondre servirait la liste de l'un pour l'autre. */
export function usePageCas(pid: Id, opts: MaybeRefOrGetter<{
  module_id?: number; group_id?: number; q?: string; statut?: string; limit?: number
}> = {}) {
  return useQuery({
    queryKey: computed(() => [...cles.cas(pid), toValue(opts)]),
    queryFn: () => api.listCases(toValue(pid), toValue(opts)),
    enabled: pret(pid),
  })
}

/** Le NOMBRE de cas, sans les charger — pour un compteur.
 *
 *  ⚠️ C'est ce qui a permis de découpler l'arbre de la liste : la barre latérale affichait un
 *  compteur en chargeant TOUS les cas du projet. À 2 000 cas, elle payait une réponse de
 *  plusieurs mégaoctets pour afficher un nombre. */
export function useNbCas(pid: Id) {
  const q = useQuery({
    queryKey: computed(() => [...cles.cas(pid), 'total']),
    queryFn: () => api.listCases(toValue(pid), { limit: 1 }),
    enabled: pret(pid),
  })
  return computed(() => q.data.value?.total ?? 0)
}

export function useGroupes(pid: Id) {
  return useQuery<GroupSummary[]>({
    queryKey: computed(() => cles.groupes(pid)),
    queryFn: () => api.listGroups(toValue(pid)),
    enabled: pret(pid),
  })
}

export function useRuns(pid: Id) {
  return useQuery<RunSummary[]>({
    queryKey: computed(() => cles.runs(pid)),
    queryFn: () => api.listRuns(toValue(pid)),
    enabled: pret(pid),
  })
}

export function useUnGroupe(gid: Id) {
  return useQuery({
    queryKey: computed(() => cles.unGroupe(gid)),
    queryFn: () => api.getGroup(toValue(gid)),
    enabled: pret(gid),
  })
}

export function useUnCas(cid: Id) {
  return useQuery({
    queryKey: computed(() => cles.unCas(cid)),
    queryFn: () => api.getCase(toValue(cid)),
    enabled: pret(cid),
  })
}

// ── Écritures ────────────────────────────────────────────────────────────────────────────────
// Chacune déclare ce qu'elle périme. C'est ce qui remplace les rechargements manuels.

export function useCreerModule(pid: Id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { name: string; description?: string }) =>
      api.createModule(toValue(pid), v.name, v.description || ''),
    // Un module neuf change l'arbre ET les listes groupées par module.
    onSuccess: () => { qc.invalidateQueries({ queryKey: cles.projet(pid) }) },
  })
}

export function useSupprimerModule(pid: Id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (moduleId: number) => api.deleteModule(moduleId),
    // Supprimer un module emporte ses cas et ses spécifications : on périme tout le projet
    // plutôt que d'énumérer — une énumération incomplète laisserait un fantôme à l'écran.
    onSuccess: () => { qc.invalidateQueries({ queryKey: cles.projet(pid) }) },
  })
}

export function useCreerGroupe(pid: Id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { moduleId: number; title: string }) =>
      api.createGroup(v.moduleId, { title: v.title }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: cles.groupes(pid) }) },
  })
}

export function useEnregistrerGroupe(pid: Id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: number; title?: string; spec_content?: string }) =>
      api.updateGroup(v.id, { title: v.title, spec_content: v.spec_content }),
    onSuccess: (maj) => {
      // La fiche elle-même ET la liste (le titre a pu changer, il s'affiche dans l'arbre).
      qc.setQueryData(cles.unGroupe(maj.id), maj)
      qc.invalidateQueries({ queryKey: cles.groupes(pid) })
    },
  })
}

export function useSupprimerGroupe(pid: Id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (gid: number) => api.deleteGroup(gid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: cles.groupes(pid) }) },
  })
}

export function useSupprimerCas(pid: Id) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (cid: number) => api.deleteCase(cid),
    // Le compteur de cas d'une spécification bouge aussi : on périme le projet entier.
    onSuccess: () => { qc.invalidateQueries({ queryKey: cles.projet(pid) }) },
  })
}
