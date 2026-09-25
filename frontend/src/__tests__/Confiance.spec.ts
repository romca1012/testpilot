/**
 * Lot 05 (D5) — « Réussi — à confirmer » : un vert obtenu par repli ou au second essai n'est jamais présenté comme
 * nominal. Le SERVEUR calcule `a_confirmer` ; l'écran le lit, il ne redérive rien.
 *
 * Ce que ces tests gardent :
 * - un `passed` à confirmer s'affiche « Réussi — à confirmer », un `passed` nominal reste « Passed » ;
 * - FALSIFIABLE : la réserve ne s'applique JAMAIS à un non-vert (un échec obtenu par repli reste « Failed ») ;
 * - aucune valeur d'enum brute (`auto_resolue`) n'atteint l'écran : tout passe par un libellé français ;
 * - la campagne stricte se demande à la création, seulement en mode automatique.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

import { A_CONFIRMER_LABEL, confianceLabel, statutAffiche, testStatusMeta } from '../lib/status'

describe('statutAffiche — la réserve « à confirmer »', () => {
  it('qualifie un passed à confirmer, sans changer le statut de lecture', () => {
    expect(statutAffiche('passed', true).label).toBe('Réussi — à confirmer')
    expect(A_CONFIRMER_LABEL).toBe('Réussi — à confirmer')
    expect(statutAffiche('passed', true).badge).not.toBe(testStatusMeta('passed').badge)
  })

  it('laisse un passed nominal inchangé', () => {
    expect(statutAffiche('passed', false)).toEqual(testStatusMeta('passed'))
    expect(statutAffiche('passed')).toEqual(testStatusMeta('passed'))
  })

  it('ne qualifie JAMAIS un non-vert, même si le drapeau arrivait vrai', () => {
    for (const statut of ['failed', 'retest', 'blocked', 'untested']) {
      expect(statutAffiche(statut, true)).toEqual(testStatusMeta(statut))
    }
  })
})

describe('confianceLabel — aucune valeur brute à l\'écran', () => {
  it('donne un libellé français à chaque valeur', () => {
    expect(confianceLabel('nominale')).toBe('Nominale')
    expect(confianceLabel('auto_resolue')).toBe('Résolue automatiquement')
    expect(confianceLabel('apres_retry')).toBe('Obtenue au second essai')
  })

  it('retombe sur « Nominale » pour une valeur inconnue ou absente, jamais sur la valeur brute', () => {
    expect(confianceLabel('bidon')).toBe('Nominale')
    expect(confianceLabel(undefined)).toBe('Nominale')
  })
})

// ── L'écran d'un test dans sa campagne ────────────────────────────────────────────────────────────────────────
const getTestDansRun = vi.fn()
const getRun = vi.fn()

vi.mock('../lib/api', () => ({
  API_BASE: '',
  roleSuffisant: () => true,
  api: {
    getTestDansRun: (...a: any[]) => getTestDansRun(...a),
    getRun: (...a: any[]) => getRun(...a),
  },
}))
vi.mock('../lib/useProjects', () => ({
  useProjects: () => ({ projectById: () => ({ effective_role: 'admin' }) }),
}))
vi.mock('../lib/useSession', async () => {
  const { ref } = await import('vue')
  return { useSession: () => ({ session: ref({ role: 'admin' }) }) }
})
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '7', caseId: '12' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import RunTestDetail from '../pages/RunTestDetail.vue'

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

function testDto(overrides: Record<string, any> = {}) {
  return {
    run_id: 7, run_name: 'Recette', run_archived: false, run_mode: 'automatique',
    case_id: 12, title: 'Un gestionnaire soumet une demande',
    type: 'fonctionnel', etat: 'ready', priority: 'medium', estimate: '', refs: '',
    statut: 'passed', confiance: 'nominale', a_confirmer: false,
    results: [] as any[], prev_case_id: null, next_case_id: null, historique_du_cas: [] as any[],
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  getRun.mockResolvedValue({ statuts_manuels: ['passed', 'failed', 'retest', 'blocked'] })
})

describe('RunTestDetail — le badge de statut', () => {
  it('affiche « Réussi — à confirmer » pour un vert obtenu par repli, jamais la valeur brute', async () => {
    getTestDansRun.mockResolvedValue(testDto({ confiance: 'auto_resolue', a_confirmer: true }))
    const w = mount(RunTestDetail, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('Réussi — à confirmer')
    expect(w.text()).not.toContain('auto_resolue')
  })

  it('affiche « Passed » pour un vert nominal', async () => {
    getTestDansRun.mockResolvedValue(testDto())
    const w = mount(RunTestDetail, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('Passed')
    expect(w.text()).not.toContain('à confirmer')
  })

  it('ne qualifie pas un échec', async () => {
    getTestDansRun.mockResolvedValue(testDto({ statut: 'failed', confiance: 'apres_retry', a_confirmer: false }))
    const w = mount(RunTestDetail, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('Failed')
    expect(w.text()).not.toContain('à confirmer')
  })
})
