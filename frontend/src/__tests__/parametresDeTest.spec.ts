/**
 * Lot PT-00 — l'interrupteur « Paramètres de test », lu à un seul endroit.
 * Éteint tant que personne ne l'allume : toute valeur qui n'est pas explicitement un « oui » laisse l'écran d'avant.
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { estAllume, useParametresDeTest } from '../lib/parametresDeTest'
import { projetEnregistre } from '../components/parametres/fusion'

describe('interrupteur « Paramètres de test »', () => {
  it('falsifiable : seul un « oui » explicite allume', () => {
    for (const valeur of ['1', 'true', 'oui', 'on', 'yes', ' 1 ', 'OUI']) expect(estAllume(valeur)).toBe(true)
    for (const valeur of ['', '0', 'false', 'non', 'off', undefined, null, 'peut-être']) expect(estAllume(valeur as any)).toBe(false)
  })
})

// Porteur, 2026-10-23 : la case est retirée, l'organisation est toujours active — même si une ancienne valeur « 0 » reste en
// base ou dans l'environnement du serveur.
vi.mock('../lib/useSettings', () => ({ useSettings: () => ({ get: () => '0', loaded: ref(true) }) }))

describe('organisation « Paramètres de test »', () => {
  it('falsifiable : toujours active, même avec un ancien réglage « 0 »', () => {
    expect(useParametresDeTest().actifs.value).toBe(true)
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
