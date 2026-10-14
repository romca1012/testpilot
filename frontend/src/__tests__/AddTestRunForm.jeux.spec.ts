/**
 * Lot PT-02b (A28, A32) — le formulaire de création d'une exécution propose les jeux de données du projet.
 *
 * Ce que ces tests gardent :
 * 1. un projet sans variable voit le formulaire d'avant, et n'envoie aucun jeu ;
 * 2. le jeu « Par défaut » est coché d'emblée ; l'écran annonce combien d'exécutions seront créées ;
 * 3. plusieurs jeux : la page ouverte ensuite est le PLAN qui les regroupe ; 50 au plus ; au moins un ;
 * 4. un lien mène au tableau des données de test ; une campagne manuelle n'envoie aucun jeu.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const createRun = vi.fn()
const getTestData = vi.fn()
const casAvecVariables = vi.fn()
const push = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    // Trois tests automatisés, seuls 21 et 22 écrivent des variables (décision A35) ; 23 est saisi à la main : une
    // exécution automatique ne le joue pas, il ne doit pas être compté.
    listCases: () => Promise.resolve({ items: [{ id: 20, automatise: true }, { id: 21, automatise: true },
      { id: 22, automatise: true }, { id: 23, automatise: false }], next_cursor: null, total: 4 }),
    listGroups: () => Promise.resolve([]),
    createRun: (...a: any[]) => createRun(...a),
    getTestData: (...a: any[]) => getTestData(...a),
    casAvecVariables: (...a: any[]) => casAvecVariables(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' } }),
  useRouter: () => ({ push }),
}))

import AddTestRunForm from '../pages/AddTestRunForm.vue'

const TABLEAU = {
  variables: [{ id: 1, nom: 'client', description: '' }],
  jeux: [{ id: 10, nom: 'Par défaut', est_defaut: true, valeurs: {} }, { id: 11, nom: 'Grosse commande', est_defaut: false, valeurs: {} }],
}

beforeEach(() => {
  vi.clearAllMocks()
  createRun.mockResolvedValue({ id: 9, plan_id: null })
  getTestData.mockResolvedValue(TABLEAU)
  casAvecVariables.mockResolvedValue([21, 22])
})

async function formulaire() {
  const w = monter(AddTestRunForm, { global: { stubs: { RouterLink: { props: ['to'], template: '<a :data-vers="JSON.stringify(to)"><slot/></a>' } } } })
  await flushPromises()
  await w.get('input[required]').setValue('Recette')
  return w
}
async function envoyer(w: any) {
  await w.get('form').trigger('submit')
  await flushPromises()
}

describe('AddTestRunForm — jeux de données (PT-02b)', () => {
  it('falsifiable : un projet sans variable voit le formulaire d’avant et n’envoie aucun jeu', async () => {
    getTestData.mockResolvedValue({ variables: [], jeux: [] })
    const w = await formulaire()

    expect(w.find('[data-testid="choix-jeux"]').exists()).toBe(false)
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [] })
    expect(push).toHaveBeenCalledWith({ name: 'run-detail', params: { pid: '1', id: '9' } })
  })

  it('le jeu « Par défaut » est coché d’emblée : une exécution', async () => {
    const w = await formulaire()

    expect((w.get('[data-testid="jeu-10"]').element as HTMLInputElement).checked).toBe(true)
    expect((w.get('[data-testid="jeu-11"]').element as HTMLInputElement).checked).toBe(false)
    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('1 exécution')
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [10] })
  })

  it('falsifiable : deux jeux cochés, l’écran l’annonce et ouvre le plan qui les regroupe', async () => {
    createRun.mockResolvedValue({ id: 9, plan_id: 4 })
    const w = await formulaire()
    await w.get('[data-testid="jeu-11"]').setValue(true)

    expect(w.get('[data-testid="nombre-executions"]').text().replace(/\s+/g, ' '))
      .toBe('2 exécutions : 3 tests dans la première, 2 avec variables dans les autres')
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [10, 11] })
    expect(push).toHaveBeenCalledWith({ name: 'plan-detail', params: { pid: '1', id: '4' } })
  })

  it('falsifiable (A35) : aucun test choisi n’écrit de variable, l’écran le dit', async () => {
    casAvecVariables.mockResolvedValue([])
    const w = await formulaire()
    await w.get('[data-testid="jeu-11"]').setValue(true)

    expect(w.get('[data-testid="nombre-executions"]').text().replace(/\s+/g, ' '))
      .toBe('2 exécutions : 3 tests dans la première, aucun test avec variables dans les autres')
  })

  it('falsifiable : la liste des tests avec variables illisible ne retire pas le choix des jeux', async () => {
    casAvecVariables.mockRejectedValue(new Error('indisponible'))
    const w = await formulaire()
    await w.get('[data-testid="jeu-11"]').setValue(true)

    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('2 exécutions, regroupées dans un plan')
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [10, 11] })
  })

  it('falsifiable : aucun jeu coché, on ne peut pas créer', async () => {
    const w = await formulaire()
    await w.get('[data-testid="jeu-10"]').setValue(false)
    await envoyer(w)

    expect(createRun).not.toHaveBeenCalled()
    expect(w.get('[data-testid="choix-jeux"]').text()).toContain('Cochez au moins un jeu')
  })

  it('falsifiable : au-delà de 50 jeux cochés, on ne peut pas créer', async () => {
    getTestData.mockResolvedValue({ variables: TABLEAU.variables,
      jeux: Array.from({ length: 51 }, (_, i) => ({ id: 100 + i, nom: `Jeu ${i}`, est_defaut: i === 0, valeurs: {} })) })
    const w = await formulaire()
    for (let i = 1; i < 51; i++) await w.get(`[data-testid="jeu-${100 + i}"]`).setValue(true)
    await envoyer(w)

    expect(w.get('[data-testid="trop-de-jeux"]').text()).toBe('50 jeux au plus')
    expect(createRun).not.toHaveBeenCalled()
  })

  it('un lien mène au tableau des données de test (A32)', async () => {
    const w = await formulaire()

    expect(JSON.parse(w.get('[data-testid="lien-donnees"]').attributes('data-vers')!)).toEqual({ name: 'project-test-data', params: { pid: '1' } })
  })

  it('passer en manuel puis revenir en automatique garde les jeux cochés', async () => {
    const w = await formulaire()
    await w.get('[data-testid="jeu-11"]').setValue(true)
    const radio = (v: string) => w.findAll('input[type="radio"]').find((r: any) => (r.element as HTMLInputElement).value === v)!
    await radio('manuelle').setValue(true)
    await radio('automatique').setValue(true)

    expect((w.get('[data-testid="jeu-11"]').element as HTMLInputElement).checked).toBe(true)
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [10, 11] })
  })

  it('une campagne manuelle ne montre ni n’envoie aucun jeu', async () => {
    const w = await formulaire()
    const manuelle = w.findAll('input[type="radio"]').find((r: any) => (r.element as HTMLInputElement).value === 'manuelle')!
    await manuelle.setValue(true)

    expect(w.find('[data-testid="choix-jeux"]').exists()).toBe(false)
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [] })
  })
})
