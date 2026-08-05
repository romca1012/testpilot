/**
 * Garde de NON-RÉGRESSION : la page d'un cas doit exposer la RELECTURE et le LANCEMENT.
 *
 * ⚠️ Pourquoi ce fichier existe. Quand `CaseDetailTR.vue` a remplacé `CaseDetail.vue`, ces deux
 * fonctions n'ont pas été reportées. Les backends marchaient (`POST /api/cases/{id}/review` et
 * `/runs`), l'ancienne page qui les appelait est devenue orpheline — et **plus aucun bouton ne
 * les atteignait**. On ne pouvait plus ni approuver une version, ni lancer un test depuis
 * l'interface. Les 36 tests du front étaient verts : aucun ne regardait la PAGE, seulement ses
 * composants pris isolément. Un composant qui marche mais que personne ne monte est du code mort.
 *
 * Ces tests montent la VRAIE page. Ils échouent si le gate ou le bouton d'exécution disparaît
 * à nouveau — y compris par simple oubli lors d'une refonte d'écran.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import type { GateOut } from '../lib/api'

const getCase = vi.fn()
const runCase = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    getCase: (...a: any[]) => getCase(...a),
    getCaseScenarios: vi.fn().mockResolvedValue([]),
    runCase: (...a: any[]) => runCase(...a),
    getExecution: vi.fn().mockResolvedValue({ running: false }),
    reviewCase: vi.fn().mockResolvedValue({}),
    updateCaseMetier: vi.fn().mockResolvedValue({}),
  },
}))

import CaseDetailTR from '../pages/CaseDetailTR.vue'

const A_RELIRE: GateOut = {
  allowed: false, needs_review: true, reason: 'relecture humaine obligatoire',
  repair_budget: 0, repair_budget_default: 2,
}
const APPROUVE: GateOut = {
  allowed: true, needs_review: false, reason: 'version approuvée en relecture',
  repair_budget: 2, repair_budget_default: 2,
}

function detail(gate: GateOut) {
  return {
    case: {
      id: 1, title: 'Demande de matériel', etat: 'new', type: 'fonctionnel',
      refs: '', estimate: '',
    },
    current_version_id: 7,
    // Cas GÉNÉRÉ par IA : il a du Gherkin — donc gate + exécution s'affichent (un cas MANUEL,
    // sans feature_content, montrerait « test technique non généré » à la place).
    versions: [{ id: 7, version_number: 1, feature_content: '# language: fr\nScénario: x',
                 preconditions: '', test_steps: '', expected_result: '' }],
    reviews: [], executions: [], gate,
  }
}

const stubs = {
  CaseHeader: true, TestsResultsTab: true, DefectsTab: true, HistoryTab: true,
  RouterLink: { template: '<a><slot/></a>' },  // rend le slot pour vérifier le texte du lien
}
const mocks = {
  $route: { params: { pid: '1', id: '1' }, query: {} },
  $router: { push: vi.fn() },
}

// `useRoute`/`useRouter` de vue-router, sans installer le routeur complet.
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

async function page(gate: GateOut) {
  getCase.mockResolvedValue(detail(gate))
  const w = mount(CaseDetailTR, { global: { stubs, mocks } })
  await flushPromises()
  return w
}

beforeEach(() => { getCase.mockReset(); runCase.mockReset() })

// Amendement §4.3 (2026-07-21) : la validation métier à la création vaut relecture. Plus de gate
// humain ni de budget de réparation sur la page du cas — le smoke-check reste, en INFORMATION.
describe('CaseDetailTR — plus de gate ; vigilance en info + renvoi vers Run/Plan', () => {
  it('ne propose PLUS d\'étape de relecture à approuver', async () => {
    const w = await page(APPROUVE)
    expect(w.findComponent({ name: 'ReviewGate' }).exists()).toBe(false)
    // Aucun bouton d'approbation ni de budget de réparation sur le cas.
    expect(w.text()).not.toContain('tentatives de réparation')
  })

  it('ne propose PLUS de « Lancer une exécution » sur le cas', async () => {
    const w = await page(APPROUVE)
    const btn = w.findAll('button').find((b) => b.text().includes('Lancer une exécution'))
    expect(btn).toBeUndefined()
  })

  it('affiche les points de vigilance du smoke-check EN INFORMATION', async () => {
    // Les alertes restent visibles (« ce test pourrait ne rien créer »), mais sans décision.
    const w = await page({ ...APPROUVE, lint_warnings: [
      { step: '[NOMINAL] X', line: 14, kind: 'soumission_absente', message: 'aucun step ne SOUMET le formulaire' }] })
    expect(w.text()).toContain('Points de vigilance')
    expect(w.text()).toContain('aucun step ne SOUMET le formulaire')
  })

  it('renvoie vers « Exécutions et résultats de test »', async () => {
    const w = await page(APPROUVE)
    expect(w.text()).toContain('Exécutions et résultats de test')
    expect(runCase).not.toHaveBeenCalled()
  })
})
