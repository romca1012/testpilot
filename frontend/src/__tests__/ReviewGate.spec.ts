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

  it.each([
    'assertion_code_modifiee', 'scenario_supprime', 'assertion_modifiee', 'exemple_modifie',
  ])('étiquette le kind lot 09 « %s » comme réparation, jamais l\'enum brute', (kind) => {
    // Revue verdict-reviewer (lot 09) : ces 4 kinds de repair_diff.py n'avaient pas d'entrée dans
    // FAMILLES — repli « à vérifier » plutôt que l'enum brute (pas une violation de §4.7), mais
    // perdait le lien avec les avertissements 0017 déjà connus (step_modifie/step_supprime).
    const w = mount(ReviewGate, {
      props: {
        caseId: 1,
        gate: { ...A_RELIRE, lint_warnings: [{ step: 's', line: 1, kind, message: 'm' }] },
      },
    })
    expect(w.text()).toContain('réparation')
    expect(w.text()).not.toContain(kind)
  })

  it('étiquette F26 « enregistrement_non_cree_par_le_scenario » comme « donnée réelle », visuellement distinct', () => {
    // F26, point 1 (2026-10-01) : signal « impossible à manquer, différent du générique » —
    // famille dédiée (ni « réparation », ni « donnée » générique) ET couleur distincte (rouge,
    // pas l'ambre partagé par tous les autres avis).
    const w = mount(ReviewGate, {
      props: {
        caseId: 1,
        gate: {
          ...A_RELIRE,
          lint_warnings: [{ step: 'j\'ouvre l\'enregistrement "X"', line: 1,
                           kind: 'enregistrement_non_cree_par_le_scenario', message: 'm' }],
        },
      },
    })
    expect(w.text()).toContain('donnée réelle')
    const badge = w.findAll('span').find((s) => s.text() === 'donnée réelle')
    expect(badge?.classes()).toContain('text-destructive')
    expect(badge?.classes()).not.toContain('text-warning')
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
