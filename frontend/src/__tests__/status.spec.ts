import { describe, it, expect } from 'vitest'
import {
  executionView, functionalView, validationView,
  defectOriginView, confirmationView, costSourceLabel, prettyModule, toneClasses,
} from '../lib/status'

describe('status mapping — deux axes distincts + vocabulaire utilisateur', () => {
  it('axe exécution : libellés humains + ton', () => {
    expect(executionView('success').label).toBe('A tourné')
    expect(executionView('technical_error').tone).toBe('destructive')
    expect(executionView('not_executed').label).toBe('Pas lancé')
    expect(executionView(null).label).toBe('Pas lancé') // repli sûr
  })

  it('axe fonctionnel : indéterminable a un ton distinct + une aide', () => {
    expect(functionalView('conforme').tone).toBe('success')
    expect(functionalView('indetermine').label).toBe('Indéterminable')
    expect(functionalView('indetermine').hint).toBeTruthy()
  })

  it('les deux axes ne partagent pas le même mapping', () => {
    expect(executionView('success').label).not.toBe(functionalView('conforme').label)
  })

  it('validation : cycle de vie du cas', () => {
    expect(validationView('validated').label).toBe('Validé')
    expect(validationView('to_review').tone).toBe('warning')
    expect(validationView('never_executed').label).toBe('Non validé')
    expect(validationView('never_executed').hint).toBeTruthy()
  })

  it('origine de défaut : jamais brut, avec aide pour « test à corriger »', () => {
    expect(defectOriginView('vrai_bug').label).toBe('Bug dans l\'application')
    expect(defectOriginView('test_a_reparer').label).toBe('Test à corriger')
    expect(defectOriginView('test_a_reparer').hint).toBeTruthy()
  })

  it('confirmation : not_required est masqué (null), les autres sont en clair', () => {
    expect(confirmationView('not_required')).toBeNull()
    expect(confirmationView('pending_human')?.label).toContain('validation humaine')
    expect(confirmationView('confirmed')?.label).toBe('Validé par un humain')
  })

  it('provenance du coût et slug de module en clair', () => {
    expect(costSourceLabel('estimated')).toBe('estimé')
    expect(costSourceLabel('anthropic_api')).toBe('mesuré via l\'API')
    expect(prettyModule('demande_materiel')).toBe('Demande materiel')
  })

  it('toneClasses renvoie des classes (jamais vide)', () => {
    expect(toneClasses('success')).toContain('text-success')
    expect(toneClasses('muted')).toContain('text-muted-foreground')
  })
})
