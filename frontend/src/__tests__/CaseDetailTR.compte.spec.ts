/**
 * Étape 4 (A70, porteur 2026-10-20) : « Joué en tant que » sur la fiche du cas.
 * - n'apparaît que si le projet a d'autres comptes que le principal (écran sobre) ;
 * - le choix part au serveur (`compte_id`), et un compte inchangé ne crée aucune version.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import type { GateOut } from '../lib/api'

const getCase = vi.fn()
const updateCaseMetier = vi.fn()
vi.mock('../lib/api', () => ({
  roleSuffisant: () => true,
  openProjectEvents: () => ({ close: () => {}, onmessage: null }),
  api: {
    getCase: (...a: any[]) => getCase(...a),
    getCaseScenarios: vi.fn().mockResolvedValue([]),
    getExecution: vi.fn().mockResolvedValue({ running: false }),
    reviewCase: vi.fn().mockResolvedValue({}),
    updateCaseMetier: (...a: any[]) => updateCaseMetier(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import CaseDetailTR from '../pages/CaseDetailTR.vue'

const APPROUVE: GateOut = {
  allowed: true, needs_review: false, reason: 'version approuvée en relecture',
  repair_budget: 2, repair_budget_default: 2,
}

function detail(comptes: { id: number | null; libelle: string }[], compteId: number | null = null) {
  return {
    case: { id: 1, title: 'Supprimer un devis', etat: 'new', type: 'fonctionnel', refs: '', estimate: '' },
    current_version_id: 7,
    versions: [{ id: 7, version_number: 1, feature_content: '# language: fr\nScénario: x',
                 preconditions: 'Un devis existe', test_steps: '["Supprimer le devis"]', expected_result: 'Refusé',
                 compte_id: compteId }],
    reviews: [], executions: [], gate: APPROUVE, comptes,
  }
}

const stubs = {
  CaseHeader: { template: '<button @click="$emit(\'edit\')">Modifier</button>' },
  TestsResultsTab: true, DefectsTab: true, HistoryTab: true, LignesDuCas: true,
  RouterLink: { template: '<a><slot/></a>' },
}
const mocks = { $route: { params: { pid: '1', id: '1' }, query: {} }, $router: { push: vi.fn() } }
const DEUX = [{ id: null, libelle: 'principal' }, { id: 4, libelle: 'Lecteur' }]

async function page(d: any) {
  getCase.mockResolvedValue(d)
  const w = mount(CaseDetailTR, { global: { stubs, mocks } })
  await flushPromises()
  return w
}
async function choisir(w: any, index: number) {
  const select = w.get('[data-testid="choix-compte"]')
  ;(select.findAll('option')[index].element as HTMLOptionElement).selected = true
  await select.trigger('change')
}
function bouton(w: any, texte: string) {
  return w.findAll('button').find((b: any) => b.text().includes(texte))
}

beforeEach(() => { getCase.mockReset(); updateCaseMetier.mockReset() })

describe('CaseDetailTR — Joué en tant que (A70)', () => {
  it('ne montre rien quand le projet n’a que le compte principal', async () => {
    const w = await page(detail([{ id: null, libelle: 'principal' }]))
    expect(w.find('[data-testid="joue-en-tant-que"]').exists()).toBe(false)
    await w.get('button').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="choix-compte"]').exists()).toBe(false)
  })

  it('dit avec quel compte le cas est joué, et envoie le compte choisi', async () => {
    updateCaseMetier.mockResolvedValue({})
    const w = await page(detail(DEUX, 4))
    expect(w.get('[data-testid="joue-en-tant-que"]').text()).toContain('Lecteur')

    await w.get('button').trigger('click')
    await flushPromises()
    await choisir(w, 0)   // « principal »
    await bouton(w, 'Enregistrer')!.trigger('click')
    await flushPromises()

    expect(updateCaseMetier).toHaveBeenCalledTimes(1)
    expect(updateCaseMetier.mock.calls[0][1].compte_id).toBe(null)
  })

  it('un compte retiré du projet reste visible et se remplace, même s’il ne reste que le principal', async () => {
    updateCaseMetier.mockResolvedValue({})
    const w = await page(detail([{ id: null, libelle: 'principal' }], 9))
    expect(w.get('[data-testid="joue-en-tant-que"]').text()).toContain('compte supprimé')

    await w.get('button').trigger('click')
    await flushPromises()
    const options = w.get('[data-testid="choix-compte"]').findAll('option')
    expect(options[0].text()).toBe('compte supprimé')
    expect(options[0].attributes('disabled')).toBeDefined()
    await choisir(w, 1)   // « principal »
    await bouton(w, 'Enregistrer')!.trigger('click')
    await flushPromises()
    expect(updateCaseMetier.mock.calls[0][1].compte_id).toBe(null)
  })

  it('une retouche sans changer de compte n’envoie pas le compte (un compte supprimé ne bloque pas l’enregistrement)', async () => {
    updateCaseMetier.mockResolvedValue({})
    const w = await page(detail([{ id: null, libelle: 'principal' }], 9))
    await w.get('button').trigger('click')
    await flushPromises()
    await w.get('input').setValue('Supprimer un devis (retouché)')
    await bouton(w, 'Enregistrer')!.trigger('click')
    await flushPromises()
    expect(updateCaseMetier).toHaveBeenCalledTimes(1)
    expect('compte_id' in updateCaseMetier.mock.calls[0][1]).toBe(false)
  })

  it('dit quand le compte du cas n’a pas encore été exploré, ou n’a pas pu s’y connecter (A80)', async () => {
    const jamais = await page(detail([{ id: null, libelle: 'principal' }, { id: 4, libelle: 'Lecteur', exploration: 'jamais' } as any], 4))
    expect(jamais.get('[data-testid="exploration-du-compte"]').text())
      .toBe('Lecteur pas encore exploré — actualisez l’exploration du projet'.replace('’', "'"))
    const echec = await page(detail([{ id: null, libelle: 'principal' }, { id: 4, libelle: 'Lecteur', exploration: 'echec' } as any], 4))
    expect(echec.get('[data-testid="exploration-du-compte"]').text()).toContain('connexion impossible lors de l')
    const erreur = await page(detail([{ id: null, libelle: 'principal' }, { id: 4, libelle: 'Lecteur', exploration: 'erreur' } as any], 4))
    expect(erreur.get('[data-testid="exploration-du-compte"]').text()).toContain('l\'exploration a échoué pour ce compte')
    const incomplet = await page(detail([{ id: null, libelle: 'principal' }, { id: 4, libelle: 'Lecteur', exploration: 'incomplet' } as any], 4))
    expect(incomplet.get('[data-testid="exploration-du-compte"]').text()).toContain('exploration incomplète')
    const ok = await page(detail([{ id: null, libelle: 'principal' }, { id: 4, libelle: 'Lecteur', exploration: '' } as any], 4))
    expect(ok.find('[data-testid="exploration-du-compte"]').exists()).toBe(false)
    const principal = await page(detail([{ id: null, libelle: 'principal' }, { id: 4, libelle: 'Lecteur', exploration: 'jamais' } as any], null))
    expect(principal.find('[data-testid="exploration-du-compte"]').exists()).toBe(false)
  })

  it('un compte inchangé ne crée aucune version', async () => {
    const w = await page(detail(DEUX, 4))
    await w.get('button').trigger('click')
    await flushPromises()
    await bouton(w, 'Enregistrer')!.trigger('click')
    await flushPromises()
    expect(updateCaseMetier).not.toHaveBeenCalled()
  })
})
