/**
 * L'onglet « Qualité de génération » — le suivi de l'évolution de l'outil.
 *
 * LA règle à ne pas casser : « aucune mesure » ne doit JAMAIS s'afficher comme « 0 % ». Un 0 %
 * accuserait l'outil d'un échec total là où il n'y a simplement pas encore de donnée — le repli
 * silencieux que ce projet refuse partout (§4.6). Et le taux compte l'axe EXÉCUTION (le test a
 * tourné), pas la conformité fonctionnelle.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const getQuality = vi.fn()
vi.mock('../lib/api', () => ({ api: { getQuality: (...a: any[]) => getQuality(...a) } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { pid: '1' } }) }))

import QualityDashboard from '../pages/QualityDashboard.vue'

const stubs = { StatTile: { props: ['label', 'value'], template: '<div class="tile">{{ label }}: {{ value }}</div>' } }

beforeEach(() => vi.clearAllMocks())

async function page(q: any) {
  getQuality.mockResolvedValue(q)
  const w = mount(QualityDashboard, { global: { stubs } })
  await flushPromises()
  return w
}

describe('QualityDashboard', () => {
  it('distingue une première tentative échouée du succès après rejeu', async () => {
    const w = await page({ total: 1, ran: 1, technical_error: 0, not_executed: 0,
      ran_rate: 1, by_day: [], first_attempt: { measured: 1, ran: 0,
        usable_verdicts: 0, technical_error: 1, retried: 1, unmeasured: 0,
        pending: 0, ran_rate: 0, usable_verdict_rate: 0 } })
    expect(w.get('[aria-labelledby="first-attempt-title"]').text()).toContain('0 %')
    expect(w.get('[aria-labelledby="first-attempt-title"]').text()).toContain('1 avec rejeu')
    expect(w.text()).toContain('Résultat final historique: 100 %')
  })
  it('affiche les tests bloqués (prérequis) à part, sans les confondre avec les erreurs techniques', async () => {
    const w = await page({ total: 3, ran: 1, technical_error: 1, blocked: 1, not_executed: 0,
      ran_rate: 1 / 3, by_day: [
        { jour: '2026-09-24', success: 1, technical_error: 1, blocked: 1, not_executed: 0 }] })

    expect(w.text()).toContain('Bloqués (prérequis)')
    expect(w.text()).toContain('compté dans le taux comme une erreur technique')
    expect(w.text()).not.toContain('blocked')
  })

  it("reste lisible face à une ancienne réponse d'API sans `blocked`", async () => {
    const w = await page({ total: 2, ran: 2, technical_error: 0, not_executed: 0,
      ran_rate: 1, by_day: [{ jour: '2026-07-21', success: 2, technical_error: 0, not_executed: 0 }] })

    expect(w.text()).toContain('Bloqués (prérequis)')
    expect(w.text()).not.toContain('NaN')
  })

  it("DIT qu'il n'y a aucune mesure au lieu d'afficher 0 %", async () => {
    const w = await page({ total: 0, ran: 0, technical_error: 0, not_executed: 0,
                           ran_rate: null, by_day: [] })

    expect(w.text()).toContain('Aucune exécution mesurée')
    expect(w.text()).not.toContain('0 %')
  })

  it('affiche le taux de réussite technique quand il existe', async () => {
    const w = await page({ total: 4, ran: 3, technical_error: 1, not_executed: 0,
                           ran_rate: 0.75, by_day: [
                             { jour: '2026-07-21', success: 3, technical_error: 1, not_executed: 0 }] })

    expect(w.text()).toContain('75 %')
    expect(w.text()).toContain('3') // tests qui ont tourné
  })

  it("compte l'axe exécution : 3 runs sur 4 ont tourné", async () => {
    const w = await page({ total: 4, ran: 3, technical_error: 1, not_executed: 0,
                           ran_rate: 0.75, by_day: [] })

    expect(w.text()).toContain('3 runs sur 4 ont pu s')
  })

  it('trace une barre par jour (évolution)', async () => {
    const w = await page({ total: 3, ran: 2, technical_error: 1, not_executed: 0, ran_rate: 0.66,
                           by_day: [
                             { jour: '2026-07-19', success: 1, technical_error: 1, not_executed: 0 },
                             { jour: '2026-07-21', success: 1, technical_error: 0, not_executed: 0 }] })

    expect(w.text()).toContain('07-19')
    expect(w.text()).toContain('07-21')
    expect(w.find('[role="img"]').attributes('aria-label')).toContain('Évolution quotidienne')
  })

  it('rend une erreur explicite et permet de relancer le chargement', async () => {
    getQuality.mockRejectedValueOnce(new Error('Droits insuffisants'))
      .mockResolvedValueOnce({ total: 0, ran: 0, technical_error: 0, not_executed: 0,
                               ran_rate: null, by_day: [] })
    const w = mount(QualityDashboard, { global: { stubs } })
    await flushPromises()

    expect(w.find('[role="alert"]').text()).toContain('Droits insuffisants')
    await w.get('button').trigger('click')
    await flushPromises()
    expect(getQuality).toHaveBeenCalledTimes(2)
  })
})
