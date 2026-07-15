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

  it('un cas conforme montre bien deux pastilles positives séparées', () => {
    const wrapper = mount(StatusPair, {
      props: { executionStatus: 'success', functionalStatus: 'conforme' },
    })
    expect(wrapper.text()).toContain('A tourné')
    expect(wrapper.text()).toContain('Conforme')
  })
})
