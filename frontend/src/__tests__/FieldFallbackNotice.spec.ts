import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FieldFallbackNotice from '../components/FieldFallbackNotice.vue'

describe('FieldFallbackNotice — le repli de champ ne passe jamais inaperçu (0007 B+)', () => {
  it('reste muet quand il n\'y a rien à signaler', () => {
    // Anti-bruit : pas de bandeau par défaut, sinon le signal perdrait tout son sens.
    const wrapper = mount(FieldFallbackNotice, { props: { fallbacks: [] } })
    expect(wrapper.text()).toBe('')
  })

  it('affiche le repli ET ses DEUX lectures possibles', () => {
    const wrapper = mount(FieldFallbackNotice, {
      props: { fallbacks: ["champ 'Raison de la demande' résolu via son libellé -> name='name'"] },
    })
    const text = wrapper.text()
    expect(text).toContain('Raison de la demande')
    // Les deux lectures : n'en donner qu'une orienterait le diagnostic à tort — c'est
    // précisément ce que le verdict 0007 n°2 refuse (une vraie régression Odoo ne doit
    // jamais être absorbée en silence).
    expect(text).toContain('à corriger dans le test')
    expect(text).toContain('renommé côté')
  })

  it('accorde le libellé au nombre de replis', () => {
    const un = mount(FieldFallbackNotice, { props: { fallbacks: ['a'] } })
    expect(un.text()).toContain('Un champ a été résolu')
    const deux = mount(FieldFallbackNotice, { props: { fallbacks: ['a', 'b'] } })
    expect(deux.text()).toContain('2 champs ont été résolus')
  })
})
