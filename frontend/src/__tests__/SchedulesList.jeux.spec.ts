/**
 * Lot PT-02b (A28, A35) — une planification choisit ses jeux de données, comme un lancement à la main.
 *
 * Ce que ces tests gardent :
 * 1. un projet sans variable voit la fenêtre d'avant et n'envoie aucun jeu ;
 * 2. le jeu « Par défaut » est coché d'emblée ; les jeux cochés sont envoyés ; aucun coché : « Par défaut » (A56) ;
 * 3. la liste nomme les jeux d'une planification ; l'un d'eux à la corbeille : elle dit qu'elle ne se déclenche pas (A36).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const createSchedule = vi.fn()
const listSchedules = vi.fn()
const getTestData = vi.fn()
vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      listSchedules: (...a: any[]) => listSchedules(...a),
      createSchedule: (...a: any[]) => createSchedule(...a),
      listCases: () => Promise.resolve({ items: [{ id: 20, automatise: true }, { id: 21, automatise: true }], next_cursor: null, total: 2 }),
      getTestData: (...a: any[]) => getTestData(...a),
      casAvecVariables: () => Promise.resolve([21]),
    },
  }
})
vi.mock('../lib/useProjects', () => ({ useProjects: () => ({ projectById: () => ({ effective_role: 'dev' }) }) }))
vi.mock('../lib/useSession', async () => {
  const { ref } = await import('vue')
  return { useSession: () => ({ session: ref({ role: 'dev' }) }) }
})
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { pid: '1' } }), useRouter: () => ({ push: vi.fn() }) }))

import SchedulesList from '../pages/SchedulesList.vue'

const TABLEAU = {
  variables: [{ id: 1, nom: 'client', description: '' }],
  jeux: [{ id: 10, nom: 'Par défaut', est_defaut: true, valeurs: {} }, { id: 11, nom: 'Grosse commande', est_defaut: false, valeurs: {} }],
}
const PLANIF = { id: 5, project_id: 1, name: 'Nocturne', selection_mode: 'all', frequency: 'daily', hour: 0, minute: 0,
  weekday: null, is_active: true, created_by: '', created_at: '', last_run_id: null, last_triggered_at: null }

beforeEach(() => {
  vi.clearAllMocks()
  listSchedules.mockResolvedValue([])
  createSchedule.mockResolvedValue({ ...PLANIF })
  getTestData.mockResolvedValue(TABLEAU)
})

async function fenetre() {
  const w = monter(SchedulesList)
  await flushPromises()
  await w.find('button').trigger('click')   // + Nouvelle planification
  await flushPromises()
  return w
}
async function creer(w: any) {
  await w.find('#form-create-schedule').trigger('submit.prevent')
  await flushPromises()
}

describe('SchedulesList — jeux de données (PT-02b)', () => {
  it('falsifiable : un projet sans variable voit la fenêtre d’avant et n’envoie aucun jeu', async () => {
    getTestData.mockResolvedValue({ variables: [], jeux: [] })
    const w = await fenetre()

    expect(w.find('[data-testid="choix-jeux"]').exists()).toBe(false)
    await creer(w)
    expect(createSchedule.mock.calls[0][1]).toMatchObject({ dataset_ids: [] })
  })

  it('falsifiable : les jeux cochés sont envoyés, « Par défaut » d’emblée', async () => {
    const w = await fenetre()
    expect((w.get('[data-testid="jeu-10"]').element as HTMLInputElement).checked).toBe(true)
    await w.get('[data-testid="jeu-11"]').setValue(true)

    // A52 : une exécution, une itération par ligne (changement délibéré : avant, une exécution par jeu).
    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('1 exécution, 2 itérations')
    await creer(w)
    expect(createSchedule.mock.calls[0][1]).toMatchObject({ dataset_ids: [10, 11] })
  })

  // A56 (porteur, 2026-10-18 — changement délibéré de l'attendu « aucun coché : on ne peut pas créer ») : la planification
  // se crée et jouera les valeurs « Par défaut » du moment de chaque déclenchement.
  it('falsifiable : aucun jeu coché, la planification se crée avec les valeurs par défaut', async () => {
    const w = await fenetre()
    await w.get('[data-testid="jeu-10"]').setValue(false)

    expect(w.get('button[form="form-create-schedule"]').attributes('disabled')).toBeUndefined()
    await creer(w)
    expect(createSchedule.mock.calls[0][1]).toMatchObject({ dataset_ids: [] })
  })

  it('la liste nomme les jeux, et signale un jeu à la corbeille', async () => {
    listSchedules.mockResolvedValue([{ ...PLANIF, dataset_ids: [10, 99] }])
    const w = monter(SchedulesList)
    await flushPromises()

    expect(w.text()).toContain('Par défaut, jeu à la corbeille')
    expect(w.get('[data-testid="planif-bloquee"]').text()).toBe('Ne se déclenche pas : un jeu de données est à la corbeille')
  })

  it('tous ses jeux vivants : aucun avertissement', async () => {
    listSchedules.mockResolvedValue([{ ...PLANIF, dataset_ids: [10, 11] }])
    const w = monter(SchedulesList)
    await flushPromises()

    expect(w.text()).toContain('Par défaut, Grosse commande')
    expect(w.find('[data-testid="planif-bloquee"]').exists()).toBe(false)
  })

  it('falsifiable : noms des jeux illisibles, un décompte neutre — jamais « à la corbeille » à tort', async () => {
    listSchedules.mockResolvedValue([{ ...PLANIF, dataset_ids: [10, 11] }])
    getTestData.mockRejectedValue(new Error('indisponible'))
    const w = monter(SchedulesList)
    await flushPromises()

    expect(w.text()).toContain('2 jeux de données')
    expect(w.text()).not.toContain('corbeille')
  })
})
