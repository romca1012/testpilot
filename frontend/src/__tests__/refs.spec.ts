import { describe, it, expect } from 'vitest'
import { parseRefs } from '../lib/refs'

describe('parseRefs', () => {
  it('découpe sur la virgule et enlève les espaces', () => {
    expect(parseRefs('JIRA-123, JIRA-456 ,  JIRA-789')).toEqual(['JIRA-123', 'JIRA-456', 'JIRA-789'])
  })

  it('filtre les entrées vides (virgule en trop, chaîne vide)', () => {
    expect(parseRefs('JIRA-1,, JIRA-2,')).toEqual(['JIRA-1', 'JIRA-2'])
    expect(parseRefs('')).toEqual([])
    expect(parseRefs('   ')).toEqual([])
  })

  it('une seule référence sans virgule reste une liste à un élément', () => {
    expect(parseRefs('JIRA-1')).toEqual(['JIRA-1'])
  })
})
