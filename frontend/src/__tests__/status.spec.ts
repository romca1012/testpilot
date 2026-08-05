import { describe, it, expect } from 'vitest'
import {
  executionView, functionalView, etatView, typeView, priorityView,
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

  it('État : un cycle de vie de DOCUMENT, qui ne parle jamais des exécutions', () => {
    expect(etatView('new').label).toBe('Nouveau')
    expect(etatView('ready').label).toBe('Prêt')
    expect(etatView('obsolete').label).toBe('Obsolète')
    // Repli sur « Nouveau » : c'est ce qu'est un cas dont l'État est inconnu ou vide, et non un
    // « Inconnu » qui laisserait croire à une donnée abîmée.
    expect(etatView(null).label).toBe('Nouveau')
    // ⚠️ L'infobulle doit DIRE que ce champ ne dit rien des exécutions — c'est exactement la
    // confusion que l'ancien « statut de validation » entretenait.
    expect(etatView('new').hint).toMatch(/rien de ses exécutions/i)
  })

  it('Type : un axe de vérification, jamais une méthode de test', () => {
    expect(typeView('fonctionnel').label).toBe('Fonctionnel')
    expect(typeView('non_fonctionnel').label).toBe('Non fonctionnel')
    expect(typeView('non_fonctionnel').hint).toMatch(/performance|sécurité/i)
  })

  it('toneClasses renvoie des classes (jamais vide)', () => {
    expect(toneClasses('success')).toContain('text-success')
    expect(toneClasses('muted')).toContain('text-muted-foreground')
  })
})
