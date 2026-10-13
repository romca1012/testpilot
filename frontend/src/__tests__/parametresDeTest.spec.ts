/**
 * Lot PT-00 — l'interrupteur « Paramètres de test », lu à un seul endroit.
 * Éteint tant que personne ne l'allume : toute valeur qui n'est pas explicitement un « oui » laisse l'écran d'avant.
 */
import { describe, it, expect } from 'vitest'
import { estAllume } from '../lib/parametresDeTest'
import { projetEnregistre } from '../components/parametres/fusion'

describe('interrupteur « Paramètres de test »', () => {
  it('falsifiable : seul un « oui » explicite allume', () => {
    for (const valeur of ['1', 'true', 'oui', 'on', 'yes', ' 1 ', 'OUI']) expect(estAllume(valeur)).toBe(true)
    for (const valeur of ['', '0', 'false', 'non', 'off', undefined, null, 'peut-être']) expect(estAllume(valeur as any)).toBe(false)
  })
})

describe('projet enregistré', () => {
  it('falsifiable : garde le rôle sur le projet, que le serveur rend vide', () => {
    const avant = { id: 4, name: 'Portail', effective_role: 'admin' } as any

    expect(projetEnregistre(avant, { name: 'Portail 2', effective_role: '' } as any))
      .toMatchObject({ id: 4, name: 'Portail 2', effective_role: 'admin' })
    expect(projetEnregistre(avant, null)).toMatchObject({ id: 4, name: 'Portail', effective_role: 'admin' })
  })
})
