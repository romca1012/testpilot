/**
 * Lot PT-04a (A48 à A50) — les environnements à l'écran.
 *
 * Ce que ces tests gardent :
 * 1. l'onglet « Configurations » liste le défaut (le projet) puis les environnements ajoutés ; la nature n'a pas de valeur
 *    par défaut (A48) : sans elle, « Enregistrer » reste grisé ; le défaut ne change que de nom ;
 * 2. au lancement, un projet qui n'a que le défaut voit le formulaire d'avant ; sinon le défaut est coché, « Production »
 *    n'est jamais cochable, et l'envoi porte les environnements choisis ;
 * 3. plusieurs environnements : le plan qui les regroupe s'ouvre ensuite.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { monter } from './_montage'

const listEnvironnements = vi.fn()
const createEnvironnement = vi.fn()
const updateEnvironnement = vi.fn()
const createRun = vi.fn()
const push = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    listEnvironnements: (...a: any[]) => listEnvironnements(...a),
    createEnvironnement: (...a: any[]) => createEnvironnement(...a),
    updateEnvironnement: (...a: any[]) => updateEnvironnement(...a),
    deleteEnvironnement: vi.fn(),
    listCases: () => Promise.resolve({ items: [{ id: 20, automatise: true }], next_cursor: null, total: 1 }),
    listGroups: () => Promise.resolve([]),
    createRun: (...a: any[]) => createRun(...a),
    getTestData: () => Promise.resolve({ variables: [], jeux: [] }),
    casAvecVariables: () => Promise.resolve([]),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' } }),
  useRouter: () => ({ push }),
}))

import Environnements from '../components/parametres/Environnements.vue'
import AddTestRunForm from '../pages/AddTestRunForm.vue'

const DEFAUT = { id: 0, nom: 'Recette', base_url: 'https://recette.test', connector_version: '', database: '', oracle_base_url: '',
  nature: 'test', nature_libelle: 'Test', est_defaut: true }
const PREPROD = { ...DEFAUT, id: 5, nom: 'Préproduction', base_url: 'https://preprod.test', est_defaut: false }
const PROD = { ...DEFAUT, id: 6, nom: 'Prod', base_url: 'https://prod.test', nature: 'production', nature_libelle: 'Production',
  est_defaut: false }
const PROJET = { id: 1, name: 'Boutique', connector_type: 'web', base_url: 'https://recette.test', database: '' } as any
const stubs = { Teleport: true }

beforeEach(() => {
  vi.clearAllMocks()
  listEnvironnements.mockResolvedValue([DEFAUT, PREPROD, PROD])
  createRun.mockResolvedValue({ id: 9, plan_id: 3 })
})

describe('Onglet Configurations — environnements (PT-04a)', () => {
  it('liste le défaut puis les ajoutés, avec leur nature en clair', async () => {
    const w = mount(Environnements, { props: { projet: PROJET, peutRegler: true }, global: { stubs } })
    await flushPromises()

    const lignes = w.findAll('[data-testid="environnement-ligne"]').map((l) => l.text())
    expect(lignes).toHaveLength(3)
    expect(lignes[0]).toContain('Recette')
    expect(lignes[1]).toContain('Préproduction')
    expect(w.get('[data-testid="nature-6"]').text()).toBe('Production')
    expect(w.find('[data-testid="environnement-supprimer-0"]').exists()).toBe(false)
  })

  it('falsifiable (A48) : sans nature choisie, rien ne part', async () => {
    createEnvironnement.mockResolvedValue([DEFAUT, PREPROD])
    const w = mount(Environnements, { props: { projet: PROJET, peutRegler: true }, global: { stubs } })
    await flushPromises()
    await w.get('[data-testid="environnement-ajouter"]').trigger('click')
    await w.get('[data-testid="environnement-nom"]').setValue('Préproduction')
    await w.get('[data-testid="environnement-adresse"]').setValue('https://preprod.test')

    expect(w.get('[data-testid="environnement-enregistrer"]').attributes('disabled')).toBeDefined()
    expect((w.get('[data-testid="environnement-nature"]').element as HTMLSelectElement).value).toBe('')
    await w.get('[data-testid="environnement-nature"]').setValue('test')
    await w.get('[data-testid="environnement-formulaire"]').trigger('submit')
    await flushPromises()

    expect(createEnvironnement).toHaveBeenCalledWith(1, expect.objectContaining({ nom: 'Préproduction', nature: 'test',
      base_url: 'https://preprod.test' }))
  })

  it('le défaut ne change que de nom : son adresse se règle ailleurs', async () => {
    updateEnvironnement.mockResolvedValue([{ ...DEFAUT, nom: 'Recette 2' }])
    const w = mount(Environnements, { props: { projet: PROJET, peutRegler: true }, global: { stubs } })
    await flushPromises()
    await w.get('[data-testid="environnement-modifier-0"]').trigger('click')

    expect(w.find('[data-testid="environnement-adresse"]').exists()).toBe(false)
    await w.get('[data-testid="environnement-nom"]').setValue('Recette 2')
    await w.get('[data-testid="environnement-formulaire"]').trigger('submit')
    await flushPromises()
    expect(updateEnvironnement).toHaveBeenCalledWith(1, 0, { nom: 'Recette 2' })
  })
})

describe('AddTestRunForm — environnements (PT-04a)', () => {
  async function formulaire() {
    const w = monter(AddTestRunForm, { global: { stubs: { RouterLink: { props: ['to'], template: '<a><slot/></a>' } } } })
    await flushPromises()
    await w.get('input[required]').setValue('Nuit')
    return w
  }

  it('un projet qui n’a que le défaut voit le formulaire d’avant', async () => {
    listEnvironnements.mockResolvedValue([DEFAUT])
    createRun.mockResolvedValue({ id: 9, plan_id: null })
    const w = await formulaire()

    expect(w.find('[data-testid="choix-environnements"]').exists()).toBe(false)
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(createRun.mock.calls[0][1].environment_ids).toEqual([])
  })

  it('falsifiable : le défaut est coché, « Production » ne l’est jamais, le choix part au serveur', async () => {
    const w = await formulaire()

    expect((w.get('[data-testid="environnement-0"]').element as HTMLInputElement).checked).toBe(true)
    expect(w.get('[data-testid="environnement-6"]').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="environnement-5"]').setValue(true)
    expect(w.get('[data-testid="nombre-executions-env"]').text()).toBe('2 exécutions, regroupées dans un plan')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(createRun.mock.calls[0][1].environment_ids).toEqual([0, 5])
    expect(push).toHaveBeenCalledWith({ name: 'plan-detail', params: { pid: '1', id: '3' } })
  })

  it('aucun environnement coché : rien ne part', async () => {
    const w = await formulaire()
    await w.get('[data-testid="environnement-0"]').setValue(false)

    expect(w.text()).toContain('Cochez au moins un environnement')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(createRun).not.toHaveBeenCalled()
  })
})
