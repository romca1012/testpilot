/**
 * Lot PT-02b (A28, A32) — le formulaire de création d'une exécution propose les jeux de données du projet.
 *
 * Ce que ces tests gardent :
 * 1. un projet sans variable voit le formulaire d'avant, et n'envoie aucun jeu ;
 * 2. le jeu « Par défaut » est coché d'emblée ; l'écran annonce combien d'exécutions seront créées ;
 * 3. plusieurs jeux : la page ouverte ensuite est le PLAN qui les regroupe ; 50 au plus ; aucun coché : « Par défaut » (A56) ;
 *    « de la ligne X à Y » coche une plage dans l'ordre du tableau ;
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

  // A52 (2026-10-16, changement délibéré des attendus) : chaque ligne cochée est une ITÉRATION de la même exécution — plus
  // une exécution par jeu regroupées dans un plan.
  it('le jeu « Par défaut » est coché d’emblée : une exécution, une itération', async () => {
    const w = await formulaire()

    expect((w.get('[data-testid="jeu-10"]').element as HTMLInputElement).checked).toBe(true)
    expect((w.get('[data-testid="jeu-11"]').element as HTMLInputElement).checked).toBe(false)
    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('1 exécution, 1 itération')
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [10] })
  })

  it('falsifiable : deux lignes cochées, une seule exécution de deux itérations, ouverte directement', async () => {
    const w = await formulaire()
    await w.get('[data-testid="jeu-11"]').setValue(true)

    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('1 exécution, 2 itérations')
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [10, 11] })
    expect(push).toHaveBeenCalledWith({ name: 'run-detail', params: { pid: '1', id: '9' } })
  })

  it('« Toutes les lignes » les coche toutes, puis revient à « Par défaut » seul', async () => {
    const w = await formulaire()
    await w.get('[data-testid="toutes-les-lignes"]').trigger('click')

    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('1 exécution, 2 itérations')
    await w.get('[data-testid="toutes-les-lignes"]').trigger('click')
    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('1 exécution, 1 itération')
  })

  // A56 (porteur, 2026-10-18 — changement délibéré de l'attendu « aucune ligne : on ne peut pas créer ») : les données de
  // test sont facultatives ; aucune ligne cochée, le test est joué avec les valeurs « Par défaut » (le serveur, recevant une
  // liste vide, fige le jeu « Par défaut » — `test_lancement_par_jeux.py`).
  it('falsifiable : aucune ligne cochée, l’exécution est créée avec les valeurs par défaut', async () => {
    const w = await formulaire()
    await w.get('[data-testid="jeu-10"]').setValue(false)

    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('1 exécution, valeurs par défaut')
    await envoyer(w)
    expect(createRun).toHaveBeenCalledTimes(1)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [] })
  })

  it('falsifiable : « de la ligne 2 à 3 » coche ces lignes-là, dans l’ordre du tableau', async () => {
    getTestData.mockResolvedValue({ ...TABLEAU, jeux: [...TABLEAU.jeux,
      { id: 12, nom: 'Mineur', est_defaut: false, valeurs: {} }, { id: 13, nom: 'Majeur', est_defaut: false, valeurs: {} }] })
    const w = await formulaire()

    expect(w.get('[data-testid="plage-a"]').element).toHaveProperty('value', '4')
    await w.get('[data-testid="plage-de"]').setValue('3')
    await w.get('[data-testid="plage-a"]').setValue('2')   // à l'envers : la plage est remise dans l'ordre
    await w.get('[data-testid="plage-cocher"]').trigger('click')

    expect(w.get('[data-testid="nombre-executions"]').text()).toBe('1 exécution, 2 itérations')
    await envoyer(w)
    expect(createRun.mock.calls[0][1]).toMatchObject({ dataset_ids: [11, 12] })
  })

  it('deux lignes seulement : pas de plage à choisir', async () => {
    const w = await formulaire()
    expect(w.find('[data-testid="plage"]').exists()).toBe(false)
  })

  it('falsifiable : au-delà de 50 jeux cochés, on ne peut pas créer', async () => {
    getTestData.mockResolvedValue({ variables: TABLEAU.variables,
      jeux: Array.from({ length: 51 }, (_, i) => ({ id: 100 + i, nom: `Jeu ${i}`, est_defaut: i === 0, valeurs: {} })) })
    const w = await formulaire()
    for (let i = 1; i < 51; i++) await w.get(`[data-testid="jeu-${100 + i}"]`).setValue(true)
    await envoyer(w)

    expect(w.get('[data-testid="trop-de-jeux"]').text()).toBe('50 lignes au plus')
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
