/**
 * `CourbeResultats.vue` — la courbe des résultats par statut sur N jours (Activité d'une
 * campagne, Historique d'un test). Aucun test d'interface ne le couvrait jusqu'ici.
 *
 * Ce que ces tests gardent :
 * - un jour SANS événement reste un point à ZÉRO dans la grille, jamais un trou dans la courbe —
 *   un trou masquerait une période sans activité, qui est elle-même une information ;
 * - la légende affiche un NOMBRE à côté de chaque statut (invariant du dépôt, §4.7 : jamais la
 *   couleur seule) ;
 * - une fenêtre sans AUCUN événement affiche le message qui le dit, plutôt qu'une courbe plate
 *   qu'on prendrait pour un graphique en panne.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { TEST_STATUS_ORDER, testStatusMeta } from '../lib/status'
import { derniersJours } from '../lib/format'
import CourbeResultats from '../components/CourbeResultats.vue'

describe('CourbeResultats — la grille et sa légende', () => {
  it('un jour SANS événement reste dans la grille à zéro, jamais un trou', () => {
    const jours = derniersJours(5)
    const w = mount(CourbeResultats, {
      props: {
        jours: 5,
        events: [{ statut: 'passed', created_at: `${jours[2]}T09:00:00Z` }],
      },
    })

    const polylines = w.findAll('polyline')
    expect(polylines).toHaveLength(TEST_STATUS_ORDER.length)   // une ligne par statut, même à zéro
    for (const p of polylines) {
      const points = (p.attributes('points') || '').split(' ').filter(Boolean)
      // 5 jours dans la fenêtre → 5 points, y compris sur les 4 jours qui n'ont rien reçu.
      expect(points).toHaveLength(5)
    }
  })

  it('la légende affiche un NOMBRE par statut, jamais la couleur seule', () => {
    const jours = derniersJours(3)
    const w = mount(CourbeResultats, {
      props: {
        jours: 3,
        events: [
          { statut: 'passed', created_at: `${jours[0]}T09:00:00Z` },
          { statut: 'passed', created_at: `${jours[1]}T09:00:00Z` },
          { statut: 'failed', created_at: `${jours[0]}T09:00:00Z` },
        ],
      },
    })

    const texte = w.text()
    for (const code of TEST_STATUS_ORDER) {
      expect(texte, `« ${testStatusMeta(code).label} » manque à la légende`).toContain(testStatusMeta(code).label)
    }
    expect(texte).toContain('Passed : 2')
    expect(texte).toContain('Failed : 1')
    expect(texte).toContain('Retest : 0')
    expect(texte).toContain('Blocked : 0')
    expect(texte).toContain('Untested : 0')
  })

  it('AUCUN événement affiche le message qui le dit, pas une courbe plate silencieuse', () => {
    const w = mount(CourbeResultats, { props: { events: [], jours: 14 } })
    expect(w.text()).toContain('Aucun résultat sur les 14 derniers jours.')
  })
})
