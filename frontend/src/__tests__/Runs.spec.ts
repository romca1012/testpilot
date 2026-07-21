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
const launchRun = vi.fn()
const archiveRun = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listCases: (...a: any[]) => listCases(...a),
    createRun: (...a: any[]) => createRun(...a),
    listRuns: (...a: any[]) => listRuns(...a),
    getRun: (...a: any[]) => getRun(...a),
    launchRun: (...a: any[]) => launchRun(...a),
    archiveRun: (...a: any[]) => archiveRun(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '7' }, query: {} }),
  useRouter: () => ({ push }),
}))

import AddTestRunForm from '../pages/AddTestRunForm.vue'
import RunsOverview from '../pages/RunsOverview.vue'
import RunDetail from '../pages/RunDetail.vue'

// Deux modules DIFFÉRENTS : une campagne doit pouvoir être TRANSVERSE (§7).
const CAS = [
  { id: 1, title: 'Cas A', module_id: 1, module: 'Facturation' },
  { id: 2, title: 'Cas B', module_id: 2, module: 'Livraison' },
]

beforeEach(() => {
  vi.clearAllMocks()
  listCases.mockResolvedValue(CAS)
  createRun.mockResolvedValue({ id: 7, name: 'R', status: 'draft', case_count: 2 })
  listRuns.mockResolvedValue([])
  launchRun.mockResolvedValue({ id: 7, status: 'running' })
  archiveRun.mockResolvedValue({ id: 7, is_archived: true })
  getRun.mockResolvedValue({
    run: { id: 7, project_id: 1, name: 'Campagne', status: 'draft', selection_mode: 'frozen',
           case_count: 2, tested_count: 1, is_archived: false, created_at: '2026-07-21T10:00:00' },
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

  it('permet une sélection TRANSVERSE : cas de plusieurs modules (§7)', async () => {
    // Le JTBD « régression transverse » : une campagne pioche dans plusieurs modules. Le backend
    // le permet ; l'écran doit le rendre VISIBLE (groupes par module + mention « Transverse »).
    const w = mount(AddTestRunForm)
    await flushPromises()
    await w.findAll('input[type="radio"]')[1].setValue()
    await flushPromises()

    expect(w.text()).toContain('Facturation')
    expect(w.text()).toContain('Livraison')

    const boxes = w.findAll('input[type="checkbox"]')
    await boxes[0].setValue(true)   // Cas A — Facturation
    await boxes[1].setValue(true)   // Cas B — Livraison
    await flushPromises()

    expect(w.text()).toContain('Transverse — 2 modules')

    await w.find('form').trigger('submit')
    await flushPromises()
    expect(createRun).toHaveBeenCalledWith('1', expect.objectContaining({
      selection_mode: 'frozen', case_ids: [1, 2],
    }))
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
                                  is_archived: false, created_at: '2026-07-21T10:00:00' }])
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

describe('RunDetail — lancement de la campagne', () => {
  it('propose « Lancer » sur un brouillon et appelle le backend', async () => {
    const w = mount(RunDetail)
    await flushPromises()

    const btn = w.findAll('button').find((b) => b.text().includes("Lancer l'exécution"))!
    expect(btn).toBeDefined()
    await btn.trigger('click')
    await flushPromises()

    expect(launchRun).toHaveBeenCalledWith(7)
  })

  it("pendant l'exécution : pas de bouton, avancement affiché", async () => {
    getRun.mockResolvedValue({
      run: { id: 7, project_id: 1, name: 'C', status: 'running', selection_mode: 'frozen',
             case_count: 2, tested_count: 1, is_archived: false, created_at: '2026-07-21T10:00:00' },
      description: '', refs: '',
      cases: [
        { id: 1, title: 'A', execution_status: 'success', functional_status: 'conforme', execution_id: 30 },
        { id: 2, title: 'B', execution_status: null, functional_status: null, execution_id: null },
      ],
    })
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('Exécution en cours')
    expect(w.findAll('button').find((b) => b.text().includes("Lancer l'exécution"))).toBeUndefined()
  })

  it('propose « Relancer » quand la campagne est terminée', async () => {
    getRun.mockResolvedValue({
      run: { id: 7, project_id: 1, name: 'C', status: 'completed', selection_mode: 'frozen',
             case_count: 1, tested_count: 1, is_archived: false, created_at: '2026-07-21T10:00:00' },
      description: '', refs: '',
      cases: [{ id: 1, title: 'A', execution_status: 'success', functional_status: 'conforme', execution_id: 30 }],
    })
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.findAll('button').find((b) => b.text().includes('Relancer'))).toBeDefined()
  })
})

describe('RunDetail — archivage (lecture seule, reversible)', () => {
  it('cloture la campagne', async () => {
    const w = mount(RunDetail)
    await flushPromises()

    await w.findAll('button').find((b) => b.text() === 'Clôturer')!.trigger('click')
    await flushPromises()

    expect(archiveRun).toHaveBeenCalledWith(7, true)
  })

  it('archivee : bandeau affiche, plus de bouton Lancer, « Rouvrir » propose', async () => {
    getRun.mockResolvedValue({
      run: { id: 7, project_id: 1, name: 'C', status: 'completed', selection_mode: 'frozen',
             case_count: 1, tested_count: 1, is_archived: true, created_at: '2026-07-21T10:00:00' },
      description: '', refs: '',
      cases: [{ id: 1, title: 'A', execution_status: 'success', functional_status: 'conforme', execution_id: 30 }],
    })
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('archivée')
    expect(w.findAll('button').find((b) => b.text().includes('Relancer'))).toBeUndefined()
    expect(w.findAll('button').find((b) => b.text() === 'Rouvrir')).toBeDefined()
  })
})

describe('RunsOverview — les archivees ne polluent pas la vue de travail', () => {
  it('separe les archivees, repliees par defaut', async () => {
    listRuns.mockResolvedValue([
      { id: 7, project_id: 1, name: 'Active', status: 'draft', selection_mode: 'all',
        case_count: 2, tested_count: 0, is_archived: false, created_at: '2026-07-21T10:00:00' },
      { id: 8, project_id: 1, name: 'Ancienne', status: 'completed', selection_mode: 'all',
        case_count: 2, tested_count: 2, is_archived: true, created_at: '2026-07-20T10:00:00' },
    ])
    const w = mount(RunsOverview)
    await flushPromises()

    expect(w.text()).toContain('Active')
    expect(w.text()).toContain('Archivées (1)')
    expect(w.text()).not.toContain('Ancienne')   // repliee

    await w.findAll('button').find((b) => b.text().includes('Archivées'))!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Ancienne')
  })
})
