import { describe, it, expect } from 'vitest'
import {
  causeLabel, executionView, functionalView, etatView, typeView, priorityView,
  defectOriginView, costSourceLabel, prettyModule, toneClasses,
} from '../lib/status'

describe('status mapping — deux axes distincts + vocabulaire utilisateur', () => {

  it('causeLabel : libellé français, jamais la valeur brute (lot 02, F10)', () => {
    expect(causeLabel('precondition_non_remplie')).toBe('Prérequis non rempli (environnement)')
    expect(causeLabel('erreur_serveur_5xx')).toBe('Erreur interne du serveur (HTTP 5xx)')
    expect(causeLabel('refus_non_explique')).toBe('Refus non expliqué (à instruire)')
    // Une cause inconnue du front reste lisible : jamais un identifiant brut à l'écran.
    expect(causeLabel('une_cause_future')).toBe('Cause à instruire')
    expect(causeLabel(null)).toBe('Cause à instruire')
  })

  it("blocked (lot 02) : libellé français, ton d'avertissement, jamais la valeur brute ni « Erreur technique »", () => {
    const v = executionView('blocked')
    expect(v.label).toBe('Bloqué (prérequis)')
    expect(v.label).not.toBe(executionView('technical_error').label)
    expect(v.tone).toBe('warning')
    // L'infobulle doit dire que ce n'est NI l'application NI un test cassé.
    expect(v.hint).toMatch(/ni un défaut de l'application ni un test cassé/i)
    expect(JSON.stringify(v)).not.toContain('blocked')
  })

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
