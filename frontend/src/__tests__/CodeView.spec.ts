import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import CodeView from '../components/CodeView.vue'

describe('CodeView — coloration maison + sécurité', () => {
  it('échappe le HTML du contenu (pas d\'injection via v-html)', () => {
    const wrapper = mount(CodeView, { props: { content: 'x = "<script>alert(1)</script>"', lang: 'python' } })
    // La balise brute ne doit jamais apparaître telle quelle dans le DOM.
    expect(wrapper.html()).not.toContain('<script>alert(1)</script>')
    expect(wrapper.text()).toContain('<script>')  // rendu comme texte, échappé
  })

  it('colore un mot-clé Gherkin en début de ligne', () => {
    const wrapper = mount(CodeView, { props: { content: 'Quand je clique', lang: 'gherkin' } })
    expect(wrapper.html()).toContain('text-primary')
    expect(wrapper.text()).toContain('Quand je clique')
  })

  it('colore un mot-clé Python et les chaînes', () => {
    const wrapper = mount(CodeView, { props: { content: "from behave import given", lang: 'python' } })
    expect(wrapper.html()).toContain('text-primary') // from / import surlignés
  })

  it('ne casse pas sur un contenu vide', () => {
    const wrapper = mount(CodeView, { props: { content: '', lang: 'python' } })
    expect(wrapper.find('pre').exists()).toBe(true)
  })
})
