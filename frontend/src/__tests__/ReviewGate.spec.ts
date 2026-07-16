import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ReviewGate from '../components/ReviewGate.vue'
import type { GateOut } from '../lib/api'

vi.mock('../lib/api', () => ({ api: { reviewCase: vi.fn().mockResolvedValue({}) } }))
import { api } from '../lib/api'

const A_RELIRE: GateOut = {
  allowed: false, needs_review: true, reason: 'relecture humaine obligatoire',
  repair_budget: 0, repair_budget_default: 2,
}
const APPROUVE: GateOut = {
  allowed: true, needs_review: false, reason: 'version approuvée en relecture',
  repair_budget: 2, repair_budget_default: 2,
}

describe('ReviewGate — le gate autorise le budget de réparation (0014, option C)', () => {
  it('montre ce qu\'on autorise AVANT d\'approuver', () => {
    // Réparer exige d'exécuter, et seul le gate autorise une exécution (§4.3) : le relecteur
    // doit voir l'autorisation qu'il donne, pas la découvrir après coup.
    const w = mount(ReviewGate, { props: { caseId: 1, gate: A_RELIRE } })
    expect(w.text()).toContain('tentatives de réparation automatique')
    expect((w.find('input[type="number"]').element as HTMLInputElement).value).toBe('2')
  })

  it('pré-remplit avec le défaut proposé par le serveur, jamais un chiffre en dur', () => {
    const w = mount(ReviewGate, {
      props: { caseId: 1, gate: { ...A_RELIRE, repair_budget_default: 5 } },
    })
    expect((w.find('input[type="number"]').element as HTMLInputElement).value).toBe('5')
  })

  it('dit clairement quand la réparation est interdite', async () => {
    const w = mount(ReviewGate, { props: { caseId: 1, gate: A_RELIRE } })
    await w.find('input[type="number"]').setValue(0)
    expect(w.text()).toContain('réparation interdite')
  })

  it('transmet le budget à l\'approbation', async () => {
    const w = mount(ReviewGate, { props: { caseId: 1, gate: A_RELIRE } })
    await w.find('input[type="number"]').setValue(3)
    await w.findAll('button').find((b) => b.text().includes('Approuver'))!.trigger('click')
    expect(api.reviewCase).toHaveBeenCalledWith(1, true, '', 3)
  })

  it('ne transmet aucun budget sur un REJET', async () => {
    // Un rejet n'exécute rien, donc ne répare rien : le budget n'a pas de sens.
    vi.mocked(api.reviewCase).mockClear()
    const w = mount(ReviewGate, { props: { caseId: 1, gate: A_RELIRE } })
    await w.findAll('button').find((b) => b.text() === 'Rejeter')!.trigger('click')
    expect(api.reviewCase).toHaveBeenCalledWith(1, false, '', undefined)
  })

  it('une fois approuvé, affiche ce qui EST autorisé (plus le formulaire)', () => {
    const w = mount(ReviewGate, { props: { caseId: 1, gate: APPROUVE } })
    expect(w.text()).toContain('2 tentatives autorisées')
    expect(w.find('input[type="number"]').exists()).toBe(false)
  })

  it('une version approuvée SANS réparation le dit', () => {
    const w = mount(ReviewGate, { props: { caseId: 1, gate: { ...APPROUVE, repair_budget: 0 } } })
    expect(w.text()).toContain('interdite pour cette version')
  })
})
