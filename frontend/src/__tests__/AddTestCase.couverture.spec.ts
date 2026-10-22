/**
 * Étape 5 (F27) — un cas listé par la spécification ne disparaît plus EN SILENCE au découpage : l'écran de validation dit
 * combien la spécification en liste et combien l'IA en propose, et nomme les user stories écartées (citation introuvable).
 * Signal seulement : la validation reste possible, une personne relit.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listGroups = vi.fn()
const addCase = vi.fn()
const getGenerationJob = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    addCase: (...a: any[]) => addCase(...a),
    getGenerationJob: (...a: any[]) => getGenerationJob(...a),
    validateMetier: vi.fn(),
    createModule: vi.fn(),
    createGroup: vi.fn(),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import AddTestCase from '../pages/AddTestCase.vue'

const DRAFT = { title: 'Consulter un équipement', preconditions: '', steps: ['Ouvrir'], expected_result: 'Affiché',
                user_story: 'Consulter' }

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  listModules.mockResolvedValue([{ id: 1, name: 'Parc' }])
  listGroups.mockResolvedValue([{ id: 50, module_id: 1, title: 'Parc', case_count: 0, parent_group_id: null }])
  addCase.mockResolvedValue({ job_id: 'J1', status: 'running', case_ids: [], error: '' })
})

async function jusquAuJob(job: any) {
  const w = monter(AddTestCase)
  await flushPromises()
  await w.find('textarea').setValue('La spécification')
  await w.findAll('select')[1].setValue('50')
  await w.find('form').trigger('submit')
  await flushPromises()
  getGenerationJob.mockResolvedValue(job)
  await vi.advanceTimersByTimeAsync(2100)
  await flushPromises()
  return w
}

describe('AddTestCase — couverture du découpage (F27)', () => {
  it('falsifiable : dit les cas listés, les cas proposés et les user stories écartées', async () => {
    const w = await jusquAuJob({ status: 'awaiting_metier', cases: [DRAFT], case_ids: [], error: '',
                                 couverture: { cas_listes: 3, cas_proposes: 1, stories_ecartees: ['Modifier un statut'] } })
    const bandeau = w.find('[data-testid="couverture-decoupage"]')
    expect(bandeau.exists()).toBe(true)
    expect(bandeau.text()).toContain('La spécification liste 3 cas à couvrir ; l\'IA en propose 1.')
    expect(bandeau.text()).toContain('Modifier un statut')
    expect(w.text()).toContain('Valider 1 cas et générer les tests')
  })

  it('rien à signaler : aucun bandeau', async () => {
    const w = await jusquAuJob({ status: 'awaiting_metier', cases: [DRAFT], case_ids: [], error: '', couverture: {} })
    expect(w.find('[data-testid="couverture-decoupage"]').exists()).toBe(false)
  })
})
