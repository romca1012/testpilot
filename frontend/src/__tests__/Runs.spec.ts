/**
 * Écrans RUN (campagne) — décision 0022 n°8.
 *
 * Ce que ces tests gardent :
 * - créer un run n'envoie PAS de sélection figée en mode « tous les cas » (sélection vivante) ;
 * - le mode figé exige au moins un cas coché (bouton désactivé sinon) ;
 * - le détail d'un run affiche ses cas, et un cas SANS exécution reste « Untested »
 *   (aucun résultat fabriqué).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listCases = vi.fn()
const createRun = vi.fn()
const listRuns = vi.fn()
const getRun = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listCases: (...a: any[]) => listCases(...a),
    createRun: (...a: any[]) => createRun(...a),
    listRuns: (...a: any[]) => listRuns(...a),
    getRun: (...a: any[]) => getRun(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '7' }, query: {} }),
  useRouter: () => ({ push }),
}))

import AddTestRunForm from '../pages/AddTestRunForm.vue'
import RunsOverview from '../pages/RunsOverview.vue'
import RunDetail from '../pages/RunDetail.vue'

const CAS = [
  { id: 1, title: 'Cas A', module_id: 1 },
  { id: 2, title: 'Cas B', module_id: 1 },
]

beforeEach(() => {
  vi.clearAllMocks()
  listCases.mockResolvedValue(CAS)
  createRun.mockResolvedValue({ id: 7, name: 'R', status: 'draft', case_count: 2 })
  listRuns.mockResolvedValue([])
  getRun.mockResolvedValue({
    run: { id: 7, project_id: 1, name: 'Campagne', status: 'draft', selection_mode: 'frozen',
           case_count: 2, tested_count: 1, created_at: '2026-07-21T10:00:00' },
    description: '', refs: '',
    cases: [
      { id: 1, title: 'Cas A', execution_status: 'success', functional_status: 'conforme', execution_id: 30 },
      { id: 2, title: 'Cas B', execution_status: null, functional_status: null, execution_id: null },
    ],
  })
})

describe('AddTestRunForm — création d\'une campagne', () => {
  it('mode « tous les cas » : n\'envoie AUCUNE sélection figée', async () => {
    const w = mount(AddTestRunForm)
    await flushPromises()

    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createRun).toHaveBeenCalledWith('1', expect.objectContaining({
      selection_mode: 'all', case_ids: [],
    }))
  })

  it('mode figé : exige au moins un cas coché', async () => {
    const w = mount(AddTestRunForm)
    await flushPromises()
    await w.findAll('input[type="radio"]')[1].setValue()
    await flushPromises()

    const submit = w.findAll('button').find((b) => b.text().includes('Ajouter une exécution'))!
    expect(submit.attributes('disabled')).toBeDefined()

    await w.find('input[type="checkbox"]').setValue(true)
    await flushPromises()
    expect(submit.attributes('disabled')).toBeUndefined()
  })

  it('dit que le filtrage dynamique n\'est pas disponible (jamais simulé)', async () => {
    const w = mount(AddTestRunForm)
    await flushPromises()
    expect(w.text()).toContain('pas encore disponible')
  })
})

describe('RunsOverview — liste des campagnes', () => {
  it('invite à créer quand il n\'y a aucune campagne', async () => {
    const w = mount(RunsOverview)
    await flushPromises()
    expect(w.text()).toContain('Aucune exécution pour ce projet')
  })

  it('affiche le % de complétion (note fonctionnelle)', async () => {
    listRuns.mockResolvedValue([{ id: 7, project_id: 1, name: 'Campagne', status: 'running',
                                  selection_mode: 'all', case_count: 4, tested_count: 1,
                                  created_at: '2026-07-21T10:00:00' }])
    const w = mount(RunsOverview)
    await flushPromises()

    expect(w.text()).toContain('1/4 cas testés')
    expect(w.text()).toContain('25 %')
  })
})

describe('RunDetail — les cas du run et leur résultat', () => {
  it('liste les cas avec leur statut, « Untested » si non exécuté', async () => {
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('Cas A')
    expect(w.text()).toContain('Cas B')
    expect(w.text()).toContain('Passed')     // Cas A : success/conforme
    expect(w.text()).toContain('Untested')   // Cas B : aucune exécution dans ce run
  })

  it('affiche l\'avancement réel du run', async () => {
    const w = mount(RunDetail)
    await flushPromises()
    expect(w.text()).toContain('1 / 2 cas testés')
  })
})
