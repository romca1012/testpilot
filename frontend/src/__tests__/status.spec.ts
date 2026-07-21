import { describe, it, expect } from 'vitest'
import {
  executionView, functionalView, validationView, priorityView,
  defectOriginView, costSourceLabel, prettyModule, toneClasses,
} from '../lib/status'

describe('status mapping — deux axes distincts + vocabulaire utilisateur', () => {

  it('provenance du coût et slug de module en clair', () => {
    expect(costSourceLabel('estimated')).toBe('estimé')
    expect(costSourceLabel('anthropic_api')).toBe('mesuré via l\'API')
    expect(prettyModule('demande_materiel')).toBe('Demande materiel')
  })

  it('priorité : étiquette de lecture, et l\'aide dit qu\'elle n\'ordonne PAS l\'exécution', () => {
    expect(priorityView('high').label).toBe('Haute')
    expect(priorityView('low').label).toBe('Basse')
    expect(priorityView(null).label).toBe('Moyenne')       // repli sûr
    // L'infobulle doit désamorcer la confusion « priorité = ordre d'exécution ».
    expect(priorityView('high').hint).toMatch(/aucun ordre d'exécution/i)
    expect(priorityView('high').hint).toMatch(/\.feature/)
  })

  it('toneClasses renvoie des classes (jamais vide)', () => {
    expect(toneClasses('success')).toContain('text-success')
    expect(toneClasses('muted')).toContain('text-muted-foreground')
  })
})
