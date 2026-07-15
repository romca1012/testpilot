import { describe, it, expect } from 'vitest'
import { executionView, functionalView, validationView, toneClasses } from '../lib/status'

describe('status mapping — deux axes distincts', () => {
  it('axe exécution : chaque code a libellé + icône + ton', () => {
    expect(executionView('success').label).toBe('Exécuté')
    expect(executionView('technical_error').tone).toBe('destructive')
    expect(executionView('not_executed').label).toBe('Non exécuté')
    expect(executionView(null).label).toBe('Non exécuté') // repli sûr
  })

  it('axe fonctionnel : indéterminé est un ton distinct (jamais conforme/non-conforme)', () => {
    expect(functionalView('conforme').tone).toBe('success')
    expect(functionalView('non_conforme').tone).toBe('destructive')
    expect(functionalView('indetermine').tone).toBe('warning')
    expect(functionalView('indetermine').label).toBe('Indéterminé')
  })

  it('les deux axes ne partagent pas le même mapping', () => {
    // « success » (exéc) et « conforme » (fonc) sont deux codes différents → deux libellés.
    expect(executionView('success').label).not.toBe(functionalView('conforme').label)
  })

  it('validation : cycle de vie du cas', () => {
    expect(validationView('validated').label).toBe('Validé')
    expect(validationView('to_review').tone).toBe('warning')
  })

  it('toneClasses renvoie des classes (jamais vide)', () => {
    expect(toneClasses('success')).toContain('text-success')
    expect(toneClasses('muted')).toContain('text-muted-foreground')
  })
})
