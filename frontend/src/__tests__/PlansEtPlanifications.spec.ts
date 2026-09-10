/**
 * Plans de test + Planifications récurrentes (migration 43, 2026-09-10).
 *
 * Ce que ces tests gardent :
 * - un Plan REGROUPE des campagnes existantes sans jamais fusionner manuel et automatique dans
 *   un seul chiffre — `PlanDetail` les groupe en DEUX sections, chacune gardant son propre run ;
 * - créer une planification n'envoie et n'affiche JAMAIS de choix de mode : le formulaire ne
 *   propose même pas la question (`scheduled_run` n'a pas de colonne `mode`) ;
 * - la lecture des Plans/Planifications reste ouverte au rôle Testeur+, la création/l'activation
 *   d'une planification exige Dev+ (même plancher que le serveur, `require_project_role(ROLE_DEV)`).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listPlans = vi.fn()
const getPlan = vi.fn()
const createPlan = vi.fn()
const assignRunToPlan = vi.fn()
const unassignRunFromPlan = vi.fn()
const listSchedules = vi.fn()
const createSchedule = vi.fn()
const patchSchedule = vi.fn()
const deleteSchedule = vi.fn()
const listRuns = vi.fn()
const listCases = vi.fn()
const listGroups = vi.fn()
const push = vi.fn()

// Le vrai `roleSuffisant` (pas un bouchon `() => true`) : ces écrans distinguent explicitement
// Testeur+ (lecture, Plans) de Dev+ (création/activation d'une planification), et un bouchon
// permissif masquerait un écart de plancher entre l'écran et le serveur.
vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      listPlans: (...a: any[]) => listPlans(...a),
      getPlan: (...a: any[]) => getPlan(...a),
      createPlan: (...a: any[]) => createPlan(...a),
      assignRunToPlan: (...a: any[]) => assignRunToPlan(...a),
      unassignRunFromPlan: (...a: any[]) => unassignRunFromPlan(...a),
      listSchedules: (...a: any[]) => listSchedules(...a),
      createSchedule: (...a: any[]) => createSchedule(...a),
      patchSchedule: (...a: any[]) => patchSchedule(...a),
      deleteSchedule: (...a: any[]) => deleteSchedule(...a),
      listRuns: (...a: any[]) => listRuns(...a),
      listCases: (...a: any[]) => listCases(...a),
      listGroups: (...a: any[]) => listGroups(...a),
    },
  }
})

let currentRole = 'testeur'
vi.mock('../lib/useProjects', () => ({
  useProjects: () => ({ projectById: () => ({ effective_role: currentRole }) }),
}))
vi.mock('../lib/useSession', async () => {
  const { ref } = await import('vue')
  return { useSession: () => ({ session: ref({ role: currentRole }) }) }
})

let currentRouteName = 'plans'
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '9' }, get name() { return currentRouteName } }),
  useRouter: () => ({ push }),
}))

import PlansList from '../pages/PlansList.vue'
import PlanDetail from '../pages/PlanDetail.vue'
import SchedulesList from '../pages/SchedulesList.vue'

const RUN_AUTO = { id: 10, project_id: 1, name: 'Régression', status: 'completed',
  selection_mode: 'all', mode: 'automatique', case_count: 4, tested_count: 4, manuel_count: 0,
  is_archived: false, created_at: '2026-09-01T08:00:00', plan_id: 9 }
const RUN_MANUEL = { id: 11, project_id: 1, name: 'Recette manuelle', status: 'draft',
  selection_mode: 'frozen', mode: 'manuelle', case_count: 2, tested_count: 0, manuel_count: 0,
  is_archived: false, created_at: '2026-09-02T08:00:00', plan_id: 9 }
const RUN_LIBRE = { id: 12, project_id: 1, name: 'Sprint 41', status: 'draft',
  selection_mode: 'all', mode: 'automatique', case_count: 1, tested_count: 0, manuel_count: 0,
  is_archived: false, created_at: '2026-08-20T08:00:00', plan_id: null }

beforeEach(() => {
  vi.clearAllMocks()
  currentRole = 'testeur'
  currentRouteName = 'plans'
  listPlans.mockResolvedValue([{ id: 9, project_id: 1, name: 'Recette V3', description: '',
    refs: '', created_by: 'alice', created_at: '2026-09-01T08:00:00' }])
  getPlan.mockResolvedValue({
    plan: { id: 9, project_id: 1, name: 'Recette V3', description: 'Toutes les campagnes de la V3',
             refs: 'JIRA-42', created_by: 'alice', created_at: '2026-09-01T08:00:00' },
    runs: [RUN_AUTO, RUN_MANUEL],
  })
  createPlan.mockResolvedValue({ id: 9, project_id: 1, name: 'Recette V3', description: '',
    refs: '', created_by: 'alice', created_at: '2026-09-01T08:00:00' })
  listRuns.mockResolvedValue([RUN_AUTO, RUN_MANUEL, RUN_LIBRE])
  listCases.mockResolvedValue({ items: [], next_cursor: null, total: 0 })
  listGroups.mockResolvedValue([])
  listSchedules.mockResolvedValue([
    { id: 5, project_id: 1, name: 'Régression nocturne', selection_mode: 'all',
      frequency: 'daily', hour: 2, minute: 0, weekday: null, is_active: true,
      created_by: 'bob', created_at: '2026-09-05T08:00:00', last_run_id: null, last_triggered_at: null },
  ])
})

describe('PlansList — la liste des plans', () => {
  it('affiche les plans existants et ouvre la fiche au clic', async () => {
    const w = monter(PlansList)
    await flushPromises()
    expect(w.text()).toContain('Recette V3')
    const ligne = w.findAll('button').find((b) => b.text().includes('Recette V3'))
    await ligne!.trigger('click')
    expect(push).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'plan-detail', params: { pid: '1', id: '9' } }))
  })

  it('« + Nouveau plan » est proposé à un Testeur (même plancher que la création de campagne)', async () => {
    currentRole = 'testeur'
    const w = monter(PlansList)
    await flushPromises()
    expect(w.text()).toContain('Nouveau plan')
  })

  it('la création n\'envoie pas de champ mode : un Plan n\'exécute rien', async () => {
    currentRouteName = 'plan-new'
    const w = monter(PlansList)
    await flushPromises()
    await w.find('input').setValue('Recette V4')
    await w.find('form').trigger('submit.prevent')
    await flushPromises()
    expect(createPlan).toHaveBeenCalledWith('1', expect.objectContaining({ name: 'Recette V4' }))
    const [, body] = createPlan.mock.calls[0]
    expect(body).not.toHaveProperty('mode')
  })
})

describe('PlanDetail — jamais un chiffre qui fusionne manuel et automatique', () => {
  it('groupe les runs en DEUX sections distinctes, chacune avec son propre run', async () => {
    const w = monter(PlanDetail)
    await flushPromises()
    expect(w.text()).toContain('Recette V3')
    expect(w.text()).toContain('Régression') // le run automatique
    expect(w.text()).toContain('Recette manuelle') // le run manuel
    expect(w.text()).toContain('Automatique')
    expect(w.text()).toContain('Manuelle')
  })

  it('retirer un run appelle unassignRunFromPlan sans toucher aux autres', async () => {
    unassignRunFromPlan.mockResolvedValue({
      plan: { id: 9, project_id: 1, name: 'Recette V3', description: '', refs: '',
              created_by: '', created_at: '' },
      runs: [RUN_MANUEL],
    })
    window.confirm = vi.fn(() => true)
    const w = monter(PlanDetail)
    await flushPromises()
    const retirer = w.findAll('button').find((b) => b.text() === 'Retirer')
    await retirer!.trigger('click')
    await flushPromises()
    expect(unassignRunFromPlan).toHaveBeenCalledWith(9, 10)
  })

  it('le picker d\'assignation exclut les runs déjà dans CE plan', async () => {
    const w = monter(PlanDetail)
    await flushPromises()
    await w.find('button.shrink-0').trigger('click') // « + Ajouter une exécution »
    await flushPromises()
    const boutons = w.findAll('button').map((b) => b.text())
    // Sprint 41 (hors de tout plan) devient un candidat proposé dans la modale.
    expect(boutons.some((t) => t.includes('Sprint 41'))).toBe(true)
    // R10 (« Régression ») est DÉJÀ dans ce plan : un seul bouton porte son nom (la ligne de la
    // section Automatique) — il ne doit PAS être re-proposé comme candidat dans la modale.
    expect(boutons.filter((t) => t.includes('R10 —')).length).toBe(1)
  })
})

describe('SchedulesList — toujours automatique, jamais de choix de mode', () => {
  it('affiche les planifications avec leur fréquence en clair', async () => {
    const w = monter(SchedulesList)
    await flushPromises()
    expect(w.text()).toContain('Régression nocturne')
    expect(w.text()).toContain('Chaque jour à 02h00')
    expect(w.text()).toContain('Automatique')
  })

  it('le formulaire de création NE PROPOSE AUCUN choix manuel/automatique', async () => {
    currentRole = 'dev'
    const w = monter(SchedulesList)
    await flushPromises()
    await w.find('button').trigger('click') // + Nouvelle planification
    await flushPromises()
    const form = w.find('#form-create-schedule')
    expect(form.exists()).toBe(true)
    // Le formulaire a bien des radios (sélection des CAS, all/frozen) — mais AUCUNE pour le
    // MODE : ni « manuelle » ni « automatique » n'apparaît comme valeur d'un input radio.
    const valeursRadio = form.findAll('input[type=radio]').map((i) => i.attributes('value'))
    expect(valeursRadio).not.toContain('manuelle')
    expect(valeursRadio).not.toContain('automatique')
    expect(form.text()).toContain('toujours en mode')
  })

  it('crée une planification quotidienne sans champ mode et avec weekday=null', async () => {
    currentRole = 'dev'
    const w = monter(SchedulesList)
    await flushPromises()
    await w.find('button').trigger('click')
    await flushPromises()
    await w.find('#form-create-schedule input[required]').setValue('Ma planif')
    await w.find('#form-create-schedule').trigger('submit.prevent')
    await flushPromises()
    expect(createSchedule).toHaveBeenCalledTimes(1)
    const [, body] = createSchedule.mock.calls[0]
    expect(body).not.toHaveProperty('mode')
    expect(body.frequency).toBe('daily')
    expect(body.weekday).toBeNull()
  })

  it('un Testeur voit la liste mais pas les actions de création/activation (Dev+ seulement)', async () => {
    currentRole = 'testeur'
    const w = monter(SchedulesList)
    await flushPromises()
    expect(w.text()).toContain('Régression nocturne')
    expect(w.text()).not.toContain('Nouvelle planification')
    expect(w.text()).not.toContain('Mettre en pause')
  })

  it('mettre en pause appelle patchSchedule avec is_active=false', async () => {
    currentRole = 'dev'
    patchSchedule.mockResolvedValue({})
    const w = monter(SchedulesList)
    await flushPromises()
    const pause = w.findAll('button').find((b) => b.text() === 'Mettre en pause')
    await pause!.trigger('click')
    await flushPromises()
    expect(patchSchedule).toHaveBeenCalledWith(5, { is_active: false })
  })
})
