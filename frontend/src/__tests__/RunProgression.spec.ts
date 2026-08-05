/**
 * Sous-onglet PROGRESSION d'une campagne (`RunProgression.vue`) — où elle en est, sans test
 * d'interface jusqu'ici.
 *
 * Ce que ces tests gardent :
 * - le pourcentage compte les cas TESTÉS, où « testé » veut dire « a reçu son PREMIER résultat » —
 *   un cas rejoué plusieurs fois ne compte qu'une fois. C'est la règle documentée en tête du
 *   fichier source : sans elle, une campagne pourrait laisser croire à une avance qu'elle n'a pas
 *   (un cas rejoué trois fois ferait alors trois points de progression pour une seule couverture) ;
 * - une campagne à zéro cas (`case_count = 0`) ne casse pas le rendu : la division est protégée.
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

import RunProgression from '../pages/RunProgression.vue'

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

beforeEach(() => {
  vi.clearAllMocks()
})

describe('RunProgression — un cas compte une fois, jamais un rejeu', () => {
  it('rejouer deux fois le même cas ne double pas le compte de « testés »', async () => {
    getRunActivite.mockResolvedValue({
      run_id: 7, run_name: 'Recette de juillet', case_count: 3,
      // Du plus RÉCENT au plus ANCIEN, comme le fil d'activité les renvoie réellement.
      events: [
        { case_id: 1, case_title: 'Cas A', statut: 'passed', mode: 'manuelle',
          created_by: 'Romaric', created_at: '2026-08-05T10:00:00+00:00' },   // rejeu de A
        { case_id: 2, case_title: 'Cas B', statut: 'failed', mode: 'manuelle',
          created_by: 'Romaric', created_at: '2026-08-04T09:00:00+00:00' },   // premier de B
        { case_id: 1, case_title: 'Cas A', statut: 'failed', mode: 'manuelle',
          created_by: 'Romaric', created_at: '2026-08-03T09:00:00+00:00' },   // premier de A
      ],
    })
    const w = mount(RunProgression, { global: { stubs } })
    await flushPromises()

    // 2 cas TESTÉS (A et B) sur 3 — pas 3, malgré les trois résultats posés dans la campagne.
    expect(w.text()).toContain('2 / 3 cas testés')
    expect(w.text()).toContain(`${Math.round((2 / 3) * 100)} %`)
  })

  it('aucun total à zéro ne casse le rendu (division protégée)', async () => {
    getRunActivite.mockResolvedValue({ run_id: 7, run_name: 'Recette', case_count: 0, events: [] })
    const w = mount(RunProgression, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('0 %')
    expect(w.text()).toContain('0 / 0 cas testés')
    expect(w.text()).toContain('Aucun cas n\'a encore été testé dans cette campagne.')
  })
})
