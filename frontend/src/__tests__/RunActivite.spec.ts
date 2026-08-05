/**
 * Sous-onglet ACTIVITÉ d'une campagne (`RunActivite.vue`) — le fil de ce qui s'est passé, jour
 * par jour. Aucun test d'interface ne le couvrait alors que le backend l'est déjà (voir
 * `tests/test_test_dans_campagne.py`, section 5 — « le fil d'ACTIVITÉ d'une campagne »).
 *
 * Ce que ces tests gardent :
 * - les événements sont GROUPÉS PAR JOUR — c'est ce qui rend le fil lisible sur une campagne qui
 *   dure des semaines, plutôt qu'une liste plate ;
 * - une campagne sans AUCUNE activité affiche le message qui le dit, jamais un tableau vide
 *   silencieux qu'on pourrait prendre pour un écran en panne ;
 * - chaque ligne montre le MODE (manuelle/automatique) de son résultat — l'invariant du produit :
 *   un « Passed » manuel ne doit jamais pouvoir se confondre avec un « Passed » automatique,
 *   y compris sur ce fil chronologique.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const getRunActivite = vi.fn()

vi.mock('../lib/api', () => ({
  api: { getRunActivite: (...a: any[]) => getRunActivite(...a) },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '7' }, query: {} }),
}))

import RunActivite from '../pages/RunActivite.vue'

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RunActivite — le fil chronologique d\'une campagne', () => {
  it('groupe les événements par JOUR', async () => {
    getRunActivite.mockResolvedValue({
      run_id: 7, run_name: 'Recette de juillet', case_count: 2,
      events: [
        { case_id: 1, case_title: 'Cas A', statut: 'passed', mode: 'manuelle',
          created_by: 'Romaric', created_at: '2026-08-05T10:00:00+00:00' },
        { case_id: 2, case_title: 'Cas B', statut: 'failed', mode: 'manuelle',
          created_by: 'Romaric', created_at: '2026-08-05T15:00:00+00:00' },
        { case_id: 1, case_title: 'Cas A', statut: 'blocked', mode: 'automatique',
          created_by: 'TestPilot', created_at: '2026-08-04T09:00:00+00:00' },
      ],
    })
    const w = mount(RunActivite, { global: { stubs } })
    await flushPromises()

    const jours = w.findAll('section')
    expect(jours).toHaveLength(2)   // deux jours distincts, pas trois lignes plates
    expect(jours[0].text()).toContain('Cas A')
    expect(jours[0].text()).toContain('Cas B')
    expect(jours[1].text()).toContain('Cas A')
  })

  it('une campagne sans AUCUNE activité affiche le message qui le dit', async () => {
    // ⚠️ « rien à afficher » et un tableau vide se ressemblent trop : sans ce message, un écran en
    // panne et une campagne qu'on n'a pas encore jouée seraient indiscernables.
    getRunActivite.mockResolvedValue({ run_id: 7, run_name: 'Recette', case_count: 2, events: [] })
    const w = mount(RunActivite, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('Aucun résultat n\'a encore été posé dans cette campagne.')
    expect(w.findAll('section')).toHaveLength(0)
  })

  it('chaque ligne montre le MODE de son résultat', async () => {
    getRunActivite.mockResolvedValue({
      run_id: 7, run_name: 'Recette', case_count: 2,
      events: [
        { case_id: 1, case_title: 'Cas A', statut: 'passed', mode: 'manuelle',
          created_by: 'Romaric', created_at: '2026-08-05T10:00:00+00:00' },
        { case_id: 2, case_title: 'Cas B', statut: 'passed', mode: 'automatique',
          created_by: 'TestPilot', created_at: '2026-08-05T11:00:00+00:00' },
      ],
    })
    const w = mount(RunActivite, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('Manuelle')
    expect(w.text()).toContain('Automatique')
  })
})
