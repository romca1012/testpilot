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
    await w.findAll('button').find((b) => b.text().includes('Débloquer'))!.trigger('click')   // A68
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

  it.each([
    ['verification_affaiblie_par_correction', 'correction'],  // D30
    ['attente_metier_changee', 'métier'],                     // D31
    ['valeur_vue_a_l_essai', 'donnée'],                       // lot VH-07 (D26)
    ['alors_identique_pour_toutes_les_lignes', 'donnée'],     // A59
    ['verification_changee_apres_defaut', 'défaut ?'],        // revue A62
  ])('étiquette « %s » (%s), jamais l\'enum brute', (kind, famille) => {
    const w = mount(ReviewGate, {
      props: {
        caseId: 1,
        gate: { ...A_RELIRE, lint_warnings: [{ step: '', line: 0, kind, message: 'm' }] },
      },
    })
    expect(w.text()).toContain(famille)
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

  // Étape 2 (A63, A68, porteur 2026-10-20) : « Bloqué », la raison en une ligne, jamais « à relire ».
  it('un test non approuvé est « Bloqué », avec ses raisons et le bouton « Débloquer »', () => {
    const w = mount(ReviewGate, { props: { caseId: 1, gate: {
      ...A_RELIRE, bloque: true, raisons: ['Régénéré après un défaut de l’application : il ne vérifie plus la même chose.'],
      lint_warnings: [{ step: '', line: 0, kind: 'verification_changee_apres_defaut', message: 'm' }] } } })
    expect(w.text()).toContain('Bloqué')
    expect(w.text()).toContain('Ce test ne sera pas lancé.')
    expect(w.text()).toContain('il ne vérifie plus la même chose')
    expect(w.text()).not.toContain('Relecture requise')
    expect(w.findAll('button').some((b) => b.text().includes('Débloquer'))).toBe(true)
    expect(w.find('details').exists()).toBe(true)
  })

  it.each([
    ['champ_ui_non_verifie', 'preuve'], ['champs_requis_manquants', 'formulaire'],
    ['soumission_absente', 'formulaire'], ['menu_non_observe', 'donnée'],
  ])('étape 2 : « %s » a son étiquette (%s), jamais « à vérifier »', (kind, famille) => {
    const w = mount(ReviewGate, { props: { caseId: 1, gate: {
      ...A_RELIRE, lint_warnings: [{ step: 's', line: 1, kind, message: 'm' }] } } })
    expect(w.text()).toContain(famille)
    expect(w.text()).not.toContain('à vérifier')
  })

  // Revue de l'étape 2 (C5) : un écart cas/test (A42) refuse l'approbation — « Débloquer » ne s'affiche pas.
  it('ne propose pas « Débloquer » quand une approbation ne peut pas débloquer', () => {
    const w = mount(ReviewGate, { props: { caseId: 1, gate: {
      ...A_RELIRE, bloque: true, debloquable: false, raisons: ['Écart entre le cas et son test : x.'] } } })
    expect(w.text()).toContain('Bloqué')
    expect(w.findAll('button').some((b) => b.text().includes('Débloquer'))).toBe(false)
  })
})
