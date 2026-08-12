import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'

const get = vi.fn()
const ensureLoaded = vi.fn()
vi.mock('../lib/useSettings', () => ({ useSettings: () => ({ get, ensureLoaded }) }))

import RefsList from '../components/RefsList.vue'

beforeEach(() => { get.mockReset(); ensureLoaded.mockReset() })

describe('RefsList', () => {
  it('sans gabarit réglé : texte brut, jamais un lien', () => {
    get.mockReturnValue('')
    const w = mount(RefsList, { props: { refs: 'JIRA-1, JIRA-2' } })
    // Espacées par un `gap` CSS (flex), pas un espace texte — d'où l'absence d'espace ici.
    expect(w.text()).toBe('JIRA-1JIRA-2')
    expect(w.find('a').exists()).toBe(false)
  })

  it('avec un gabarit réglé : chaque référence devient un lien avec {ref} remplacé', () => {
    get.mockReturnValue('https://exemple.atlassian.net/browse/{ref}')
    const w = mount(RefsList, { props: { refs: 'JIRA-1, JIRA-2' } })
    const liens = w.findAll('a')
    expect(liens).toHaveLength(2)
    expect(liens[0].attributes('href')).toBe('https://exemple.atlassian.net/browse/JIRA-1')
    expect(liens[1].attributes('href')).toBe('https://exemple.atlassian.net/browse/JIRA-2')
    expect(liens[0].attributes('target')).toBe('_blank')
    expect(liens[0].attributes('rel')).toBe('noopener noreferrer')
  })

  it('un gabarit qui ne produit pas une URL http(s) retombe sur du texte brut', () => {
    get.mockReturnValue('javascript:alert(1)//{ref}')
    const w = mount(RefsList, { props: { refs: 'JIRA-1' } })
    expect(w.find('a').exists()).toBe(false)
    expect(w.text()).toBe('JIRA-1')
  })

  it('encode la référence dans l\'URL', () => {
    get.mockReturnValue('https://exemple.atlassian.net/browse/{ref}')
    const w = mount(RefsList, { props: { refs: 'PROJ/1' } })
    expect(w.find('a').attributes('href')).toBe('https://exemple.atlassian.net/browse/PROJ%2F1')
  })
})
