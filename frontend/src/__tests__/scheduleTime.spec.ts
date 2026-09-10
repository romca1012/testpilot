/**
 * Conversion locale <-> UTC pour la planification récurrente (2026-09-10).
 *
 * ⚠️ Le bug corrigé : le formulaire demandait une heure sans dire UTC, alors que
 * `scheduler_service.tick()` compare en UTC côté serveur — une planification à 14h37 tapée en
 * France l'été (UTC+2) se déclenchait réellement à 16h37. Fixe `TZ` explicitement (plutôt que de
 * dépendre du fuseau de la machine qui exécute la suite) pour que ce test reste déterministe.
 */
process.env.TZ = 'Europe/Paris'

import { describe, it, expect } from 'vitest'
import { localVersUtc, utcVersLocal } from '../lib/scheduleTime'

describe('scheduleTime — quotidien (pas de jour de semaine)', () => {
  it('14h37 locale (été, UTC+2) devient 12h37 UTC', () => {
    expect(localVersUtc({ hour: 14, minute: 37, weekday: null }))
      .toEqual({ hour: 12, minute: 37, weekday: null })
  })

  it('l\'aller-retour restitue exactement l\'heure locale de départ', () => {
    const local = { hour: 2, minute: 15, weekday: null }
    expect(utcVersLocal(localVersUtc(local))).toEqual(local)
  })

  it('un passage de minuit (UTC) ne casse rien pour le quotidien : 23h50 locale -> 21h50 UTC', () => {
    expect(localVersUtc({ hour: 23, minute: 50, weekday: null }))
      .toEqual({ hour: 21, minute: 50, weekday: null })
  })
})

describe('scheduleTime — hebdomadaire (le jour peut basculer avec l\'heure)', () => {
  it('lundi 14h37 locale reste lundi en UTC (pas de bascule de jour)', () => {
    // weekday 0 = lundi (convention Python, `datetime.weekday()`).
    expect(localVersUtc({ hour: 14, minute: 37, weekday: 0 }))
      .toEqual({ hour: 12, minute: 37, weekday: 0 })
  })

  it('lundi 1h00 locale bascule dimanche 23h00 UTC — le jour change AVEC l\'heure', () => {
    // 1h locale (UTC+2) - 2h = 23h la veille : le jour de la semaine doit suivre, sous peine
    // de comparer un « lundi 23h UTC » à un déclenchement réel un dimanche soir.
    expect(localVersUtc({ hour: 1, minute: 0, weekday: 0 }))
      .toEqual({ hour: 23, minute: 0, weekday: 6 }) // 6 = dimanche
  })

  it('l\'aller-retour restitue exactement heure ET jour de départ, y compris au passage de minuit', () => {
    for (const weekday of [0, 1, 2, 3, 4, 5, 6]) {
      const local = { hour: 1, minute: 0, weekday }
      expect(utcVersLocal(localVersUtc(local))).toEqual(local)
    }
  })

  it('dimanche 23h30 locale bascule lundi 21h30 UTC (bascule dans l\'autre sens)', () => {
    expect(localVersUtc({ hour: 23, minute: 30, weekday: 6 }))
      .toEqual({ hour: 21, minute: 30, weekday: 6 })
  })
})

describe('scheduleTime — affichage (UTC stocké -> local affiché)', () => {
  it('12h37 UTC (stocké) s\'affiche 14h37 locale', () => {
    expect(utcVersLocal({ hour: 12, minute: 37, weekday: null }))
      .toEqual({ hour: 14, minute: 37, weekday: null })
  })

  it('dimanche 23h00 UTC (stocké) s\'affiche lundi 01h00 locale', () => {
    expect(utcVersLocal({ hour: 23, minute: 0, weekday: 6 }))
      .toEqual({ hour: 1, minute: 0, weekday: 0 })
  })
})
