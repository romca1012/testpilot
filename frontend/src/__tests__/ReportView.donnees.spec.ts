/**
 * Lot PT-02c — le rapport d'un test montre les données de test réellement posées (figées au lancement, A29).
 *
 * Ce que ces tests gardent :
 * 1. sans donnée de test, le rapport est celui d'avant (aucune carte) ;
 * 2. chaque variable est écrite telle que le test l'écrit (`{{client}}`), avec la valeur jouée ;
 * 3. une valeur reprise du jeu « Par défaut » le dit, discrètement ; une valeur du jeu joué ne dit rien de plus.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const getReport = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    getReport: (...a: any[]) => getReport(...a),
    listArtifacts: () => Promise.reject(new Error('aucune trace')),
    artifactUrl: () => '',
    rapportImprimable: () => '',
  },
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { pid: '1', id: '7' } }) }))

import ReportView from '../pages/ReportView.vue'

const RAPPORT = {
  module_name: 'commande', title: 'Commande', version_number: 1,
  execution_status: 'success', functional_status: 'conforme', execution_label: 'Succès', functional_label: 'Conforme',
  scenarios_total: 1, scenarios_passed: 1, scenarios_failed: 0, scenarios: [], repairs: [],
  cost_usd: 0, cost_source: 'none', iterations: 0, duration_seconds: 3, needs_human_confirmation: false,
}

beforeEach(() => vi.clearAllMocks())

async function rapport(plus: object) {
  getReport.mockResolvedValue({ ...RAPPORT, ...plus })
  const w = monter(ReportView)
  await flushPromises()
  return w
}

describe('ReportView — données de test jouées (PT-02c)', () => {
  it('falsifiable : sans donnée de test, aucune carte', async () => {
    const w = await rapport({ donnees_de_test: {} })

    expect(w.find('[data-testid="donnees-jouees"]').exists()).toBe(false)
  })

  it('falsifiable : chaque variable, telle que le test l’écrit, avec la valeur jouée et son origine', async () => {
    const w = await rapport({ donnees_de_test: { jeu: 'Grosse commande', valeurs: {
      client: { valeur: 'Durand Industrie', origine: 'Grosse commande' },
      ville: { valeur: 'Lyon', origine: 'Par défaut' },
    } } })

    const carte = w.get('[data-testid="donnees-jouees"]')
    expect(carte.text()).toContain('Données de test — Grosse commande')
    const lignes = carte.findAll('tr').map((l) => [l.get('th').text(), l.get('td').text().replace(/\s+/g, ' ').trim()])
    expect(lignes).toEqual([['{{client}}', 'Durand Industrie'], ['{{ville}}', 'Lyon Par défaut']])
  })

  it('falsifiable (A52) : plusieurs lignes jouées, une ligne par itération, une colonne par variable', async () => {
    const w = await rapport({ donnees_de_test: { jeu: 'Par défaut, Adulte', valeurs: {}, iterations: [
      { jeu: 'Par défaut', valeurs: { age: { valeur: '5', origine: 'Par défaut' }, resultat: { valeur: 'Refusé', origine: 'Par défaut' } } },
      { jeu: 'Adulte', valeurs: { age: { valeur: '18', origine: 'Adulte' }, resultat: { valeur: 'Bienvenue', origine: 'Adulte' } } }] } })

    const carte = w.get('[data-testid="iterations-jouees"]')
    expect(carte.text()).toContain('2 itérations')
    expect(carte.findAll('tbody tr').map((l) => l.findAll('td').map((c) => c.text().trim()))).toEqual([
      ['Par défaut', '5', 'Refusé'], ['Adulte', '18', 'Bienvenue']])
    expect(w.find('[data-testid="donnees-jouees"]').exists()).toBe(false)
    expect(w.find('[data-testid="resultat-iteration"]').exists()).toBe(false)   // rapport d'avant : aucun résultat inventé
  })

  it('falsifiable : chaque itération montre son résultat, calculé par le serveur', async () => {
    const w = await rapport({ donnees_de_test: { jeu: '', valeurs: {}, iterations: [
      { jeu: 'Par défaut', valeurs: { age: { valeur: '5', origine: 'Par défaut' } }, statut: 'passed' },
      { jeu: 'Dix ans', valeurs: { age: { valeur: '10', origine: 'Dix ans' } }, statut: 'failed' }] } })

    expect(w.findAll('[data-testid="resultat-iteration"]').map((b) => b.text())).toEqual(['Passed', 'Failed'])
  })
})
