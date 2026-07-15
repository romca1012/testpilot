import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import StatusPair from '../components/StatusPair.vue'

describe('StatusPair — les deux axes ne sont JAMAIS fusionnés', () => {
  it('affiche deux étiquettes d\'axe et deux verdicts distincts', () => {
    const wrapper = mount(StatusPair, {
      props: { executionStatus: 'technical_error', functionalStatus: 'indetermine' },
    })
    const text = wrapper.text()
    // Les deux axes sont étiquetés séparément.
    expect(text).toContain('Exécution')
    expect(text).toContain('Fonctionnel')
    // Chaque axe porte son propre verdict — pas un unique badge « OK/KO ».
    expect(text).toContain('Erreur technique')
    expect(text).toContain('Indéterminé')
  })

  it('un cas conforme montre bien deux pastilles positives séparées', () => {
    const wrapper = mount(StatusPair, {
      props: { executionStatus: 'success', functionalStatus: 'conforme' },
    })
    expect(wrapper.text()).toContain('Exécuté')
    expect(wrapper.text()).toContain('Conforme')
  })
})
