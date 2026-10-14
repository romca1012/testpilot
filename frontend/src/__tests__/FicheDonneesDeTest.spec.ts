/**
 * Lot PT-02c (A32) — la fiche d'un test et ses données de test.
 *
 * Ce que ces tests gardent :
 * 1. l'aperçu par colonne n'est proposé que si le projet a des variables ET que le test en écrit ; sinon, le test tel qu'écrit ;
 * 2. le texte remplacé est celui du SERVEUR (même calcul qu'au lancement), jamais recalculé à l'écran ; un manque y est dit ;
 * 3. « Variable » propose les variables du projet, écrites `{{nom}}`, et rien à un projet sans variable.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const getTestData = vi.fn()
const apercuDonnees = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    getTestData: (...a: any[]) => getTestData(...a),
    apercuDonnees: (...a: any[]) => apercuDonnees(...a),
  },
}))

import ApercuParJeu from '../components/case/ApercuParJeu.vue'
import InsererVariable from '../components/case/InsererVariable.vue'

const TABLEAU = {
  variables: [{ id: 1, nom: 'client', description: '' }],
  jeux: [{ id: 10, nom: 'Par défaut', est_defaut: true, valeurs: {} }, { id: 11, nom: 'Grosse commande', est_defaut: false, valeurs: {} }],
}
const AVEC = 'Fonctionnalité: X\n  Scénario: Y\n    Alors le client {{client}} est servi\n'

beforeEach(() => {
  vi.clearAllMocks()
  getTestData.mockResolvedValue(TABLEAU)
})

const stubs = { RouterLink: { props: ['to'], template: '<a :data-vers="JSON.stringify(to)"><slot/></a>' } }
async function apercu(feature = AVEC) {
  const w = monter(ApercuParJeu, { props: { pid: '1', caseId: 7, versionId: 70, feature }, global: { stubs } })
  await flushPromises()
  return w
}

describe('Fiche d’un test — aperçu par colonne (PT-02c)', () => {
  it('falsifiable : un test sans variable ne propose rien et reste tel qu’écrit', async () => {
    const w = await apercu('Fonctionnalité: X\n  Scénario: Y\n    Alors ok\n')

    expect(w.find('[data-testid="apercu-jeu"]').exists()).toBe(false)
    expect(w.text()).toContain('Alors ok')
  })

  it('un projet sans variable ne propose rien', async () => {
    getTestData.mockResolvedValue({ variables: [], jeux: [] })
    const w = await apercu()

    expect(w.find('[data-testid="apercu-jeu"]').exists()).toBe(false)
  })

  it('falsifiable : toutes les variables à la corbeille, l’aperçu reste proposé pour annoncer le blocage', async () => {
    getTestData.mockResolvedValue({ variables: [], jeux: TABLEAU.jeux })
    const w = await apercu()

    expect(w.find('[data-testid="apercu-jeu"]').exists()).toBe(true)
  })

  it('falsifiable : une colonne choisie, le texte vient du serveur', async () => {
    apercuDonnees.mockResolvedValue({ jeu: 'Grosse commande', texte: 'Alors le client Durand est servi', manques: [], valeurs: {} })
    const w = await apercu()
    expect(w.text()).toContain('{{client}}')

    await w.get('[data-testid="apercu-jeu"]').setValue('11')
    await flushPromises()

    expect(apercuDonnees).toHaveBeenCalledWith(7, 70, 11)
    expect(w.text()).toContain('Alors le client Durand est servi')
    expect(w.text()).not.toContain('{{client}}')
    expect(JSON.parse(w.get('[data-testid="lien-donnees"]').attributes('data-vers')!)).toEqual({ name: 'project-test-data', params: { pid: '1' } })
  })

  it('falsifiable : une valeur qui manque est dite', async () => {
    apercuDonnees.mockResolvedValue({ jeu: 'Par défaut', texte: AVEC, manques: ['variable sans valeur « client »'], valeurs: {} })
    const w = await apercu()
    await w.get('[data-testid="apercu-jeu"]').setValue('10')
    await flushPromises()

    expect(w.get('[data-testid="apercu-manques"]').text()).toBe('Serait bloqué : variable sans valeur « client »')
  })
})

describe('Fiche d’un test — bouton « Variable » (PT-02c)', () => {
  it('falsifiable : choisir une variable l’écrit entre doubles accolades', async () => {
    const w = monter(InsererVariable, { props: { pid: '1' } })
    await flushPromises()

    await w.get('[data-testid="inserer-variable"]').setValue('client')

    expect(w.emitted('inserer')).toEqual([['{{client}}']])
    expect((w.get('[data-testid="inserer-variable"]').element as HTMLSelectElement).value).toBe('')
  })

  it('un projet sans variable ne voit pas le bouton', async () => {
    getTestData.mockResolvedValue({ variables: [], jeux: [] })
    const w = monter(InsererVariable, { props: { pid: '1' } })
    await flushPromises()

    expect(w.find('[data-testid="inserer-variable"]').exists()).toBe(false)
  })
})
