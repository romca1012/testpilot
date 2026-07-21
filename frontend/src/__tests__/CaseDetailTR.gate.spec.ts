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
      id: 1, title: 'Demande de matériel', angle: 'nominal', validation_status: 'never_executed',
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

describe('CaseDetailTR — la relecture reste sur le cas, le lancement part vers Run/Plan', () => {
  it('affiche le gate de relecture (invariant §4.3)', async () => {
    const w = await page(A_RELIRE)
    // Le gate est le garde-fou annoncé par le produit : s'il n'est pas à l'écran, la promesse
    // « relecture humaine obligatoire » n'est plus tenable par l'utilisateur.
    expect(w.text()).toContain('Relecture')
    expect(w.findComponent({ name: 'ReviewGate' }).exists()).toBe(true)
  })

  it('ne propose PLUS de « Lancer une exécution » sur le cas (2026-07-21)', async () => {
    // Un cas ne s'exécute pas seul : l'exécution vit dans un Run. Un bouton « Lancer » par cas
    // contredisait le modèle cible (`0022`) — il a été retiré.
    const w = await page(APPROUVE)
    const btn = w.findAll('button').find((b) => b.text().includes('Lancer une exécution'))
    expect(btn).toBeUndefined()
  })

  it('quand le gate REFUSE, dit qu\'un cas non relu bloque le run', async () => {
    const w = await page(A_RELIRE)
    expect(w.text()).toContain('Approuvez la version en relecture')
  })

  it('quand le gate AUTORISE, renvoie vers « Exécutions et résultats de test »', async () => {
    // On indique OÙ se lance l'exécution (dans un run), plutôt que de la proposer ici.
    const w = await page(APPROUVE)
    expect(w.text()).toContain('Exécutions et résultats de test')
    expect(runCase).not.toHaveBeenCalled()
  })
})
