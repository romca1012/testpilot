/**
 * Mise à jour en direct (SSE, audit 2026-09-07) — « plusieurs comptes en simultané sur des
 * projets ». Un cas édité par un collègue doit se refléter sur cet écran sans rechargement
 * manuel, SAUF si un formulaire d'édition est ouvert ICI : dans ce cas on se contente de
 * prévenir, jamais de recharger sous les pieds d'une saisie en cours (elle serait perdue).
 * Le vrai filet contre une édition concurrente reste le refus 409 côté serveur
 * (`base_version_id`, voir `tests/test_champs_metier.py` côté backend) — ce flux n'est qu'un
 * confort qui invite à recharger plus tôt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const getCase = vi.fn()
let dernierFlux: { onmessage: ((msg: MessageEvent) => void) | null; close: () => void } | null = null
const openProjectEvents = vi.fn((..._args: any[]) => {
  dernierFlux = { onmessage: null, close: vi.fn() }
  return dernierFlux
})

vi.mock('../lib/api', () => ({
  roleSuffisant: () => true,
  openProjectEvents: (...a: any[]) => openProjectEvents(...a),
  api: {
    getCase: (...a: any[]) => getCase(...a),
    getCaseScenarios: vi.fn().mockResolvedValue([]),
    listCases: vi.fn().mockResolvedValue({ items: [] }),
    updateCaseMetier: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import CaseDetailTR from '../pages/CaseDetailTR.vue'

function detail() {
  return {
    case: { id: 1, title: 'Demande de matériel', etat: 'new', type: 'fonctionnel', refs: '', estimate: '' },
    current_version_id: 7,
    versions: [{ id: 7, version_number: 1, feature_content: '', preconditions: '',
                test_steps: '', expected_result: '' }],
    reviews: [], executions: [],
    gate: { allowed: true, needs_review: false, reason: '', repair_budget: 0, repair_budget_default: 2 },
  }
}

const stubs = {
  // Un vrai bouton qui émet `edit`, pour pouvoir entrer en édition comme un utilisateur le
  // ferait — contrairement à un stub `true` muet, qui ne rendrait aucun élément cliquable.
  CaseHeader: { template: '<button @click="$emit(\'edit\')">Modifier</button>' },
  TestsResultsTab: true, DefectsTab: true, HistoryTab: true,
  RouterLink: { template: '<a><slot/></a>' },
}
const mocks = {
  $route: { params: { pid: '1', id: '1' }, query: {} },
  $router: { push: vi.fn() },
}

beforeEach(() => {
  vi.clearAllMocks()
  dernierFlux = null
})

async function page() {
  getCase.mockResolvedValue(detail())
  const w = mount(CaseDetailTR, { global: { stubs, mocks } })
  await flushPromises()
  return w
}

function emettre(evenement: { kind: string; case_id: number }) {
  dernierFlux!.onmessage!({ data: JSON.stringify(evenement) } as MessageEvent)
}

describe('CaseDetailTR — mise à jour en direct (SSE)', () => {
  it('ouvre un flux sur le PROJET du cas au montage', async () => {
    await page()
    expect(openProjectEvents).toHaveBeenCalledWith('1')
  })

  it('un événement sur CE cas, hors édition, recharge automatiquement', async () => {
    await page()
    expect(getCase).toHaveBeenCalledTimes(1)

    emettre({ kind: 'case_metier_changed', case_id: 1 })
    await flushPromises()

    expect(getCase).toHaveBeenCalledTimes(2)
  })

  it('un événement sur un AUTRE cas du même projet est ignoré', async () => {
    await page()
    emettre({ kind: 'case_metier_changed', case_id: 999 })
    await flushPromises()
    expect(getCase).toHaveBeenCalledTimes(1)
  })

  it('un événement pendant l’édition ne recharge PAS et affiche une notification', async () => {
    const w = await page()
    await w.find('button').trigger('click')   // « Modifier » (stub CaseHeader)

    emettre({ kind: 'case_metier_changed', case_id: 1 })
    await flushPromises()

    expect(getCase).toHaveBeenCalledTimes(1)   // pas de rechargement silencieux du brouillon
    expect(w.text()).toContain('vient de modifier')
  })

  it('« Voir la version à jour » referme le formulaire et recharge', async () => {
    const w = await page()
    await w.find('button').trigger('click')   // « Modifier »
    emettre({ kind: 'case_metier_changed', case_id: 1 })
    await flushPromises()

    const bouton = w.findAll('button').find((b) => b.text() === 'Voir la version à jour')
    expect(bouton).toBeTruthy()
    await bouton!.trigger('click')
    await flushPromises()

    expect(getCase).toHaveBeenCalledTimes(2)
    expect(w.text()).not.toContain('vient de modifier')
  })

  it('la connexion SSE se ferme au démontage', async () => {
    const w = await page()
    w.unmount()
    expect(dernierFlux!.close).toHaveBeenCalled()
  })
})
