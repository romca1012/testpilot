import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusPair from '../components/StatusPair.vue'

describe('StatusPair — les deux axes ne sont JAMAIS fusionnés', () => {
  it('affiche deux étiquettes d\'axe explicites et deux verdicts distincts', () => {
    const wrapper = mount(StatusPair, {
      props: { executionStatus: 'technical_error', functionalStatus: 'indetermine' },
    })
    const text = wrapper.text()
    // Étiquettes d'axe compréhensibles sans le brief.
    expect(text).toContain('Déroulement du test')
    expect(text).toContain('Résultat fonctionnel')
    // Chaque axe porte son propre verdict — pas un unique badge « OK/KO ».
    expect(text).toContain('Erreur technique')
    expect(text).toContain('Indéterminable')
  })

  it("un cas bloqué (prérequis manquant) reste sur l'axe exécution, l'axe fonctionnel dit indéterminable", () => {
    const wrapper = mount(StatusPair, {
      props: { executionStatus: 'blocked', functionalStatus: 'indetermine' },
    })
    const text = wrapper.text()
    expect(text).toContain('Bloqué (prérequis)')
    expect(text).toContain('Indéterminable')
    expect(text).not.toContain('Erreur technique')
    expect(text).not.toContain('blocked')
  })

  it('un cas conforme montre bien deux pastilles positives séparées', () => {
    const wrapper = mount(StatusPair, {
      props: { executionStatus: 'success', functionalStatus: 'conforme' },
    })
    expect(wrapper.text()).toContain('A tourné')
    expect(wrapper.text()).toContain('Conforme')
  })
})
