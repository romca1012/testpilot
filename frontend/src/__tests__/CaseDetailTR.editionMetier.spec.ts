/**
 * « Modifier » puis « Enregistrer » SANS RIEN CHANGER ne doit créer AUCUNE version (2026-09-16).
 *
 * ⚠️ Bug réel corrigé ici : à l'ouverture, un champ jamais rédigé se pré-remplit avec l'aperçu
 * DÉRIVÉ du Gherkin (pour ne pas partir d'une page blanche) — comparer au SERVEUR (vide vs.
 * dérivé) voyait donc un « changement » là où l'utilisateur n'avait rien touché, et « Enregistrer »
 * créait une version fantôme à chaque ouverture/fermeture du formulaire. La comparaison se fait
 * désormais formulaire-contre-formulaire (avant/après édition), jamais contre ce que la version
 * stockait.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import type { GateOut } from '../lib/api'

const getCase = vi.fn()
const updateCaseMetier = vi.fn()
vi.mock('../lib/api', () => ({
  roleSuffisant: () => true,
  openProjectEvents: () => ({ close: () => {}, onmessage: null }),
  api: {
    getCase: (...a: any[]) => getCase(...a),
    getCaseScenarios: vi.fn().mockResolvedValue([]),
    getExecution: vi.fn().mockResolvedValue({ running: false }),
    reviewCase: vi.fn().mockResolvedValue({}),
    updateCaseMetier: (...a: any[]) => updateCaseMetier(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import CaseDetailTR from '../pages/CaseDetailTR.vue'

const APPROUVE: GateOut = {
  allowed: true, needs_review: false, reason: 'version approuvée en relecture',
  repair_budget: 2, repair_budget_default: 2,
}

// Cas GÉNÉRÉ dont AUCUN champ métier n'a jamais été rédigé à la main (le scénario du bug réel :
// `preconditions`/`test_steps`/`expected_result` vides sur la version, seul le Gherkin existe).
function detailSansMetierRedige() {
  return {
    case: { id: 1, title: 'Connexion', etat: 'new', type: 'fonctionnel', refs: '', estimate: '' },
    current_version_id: 7,
    versions: [{
      id: 7, version_number: 1,
      feature_content: '# language: fr\nScénario: Connexion\n  Quand je me connecte\n'
        + '  Alors je vois le tableau de bord\n',
      preconditions: '', test_steps: '', expected_result: '',
    }],
    reviews: [], executions: [], gate: APPROUVE,
  }
}

const stubs = {
  CaseHeader: { template: '<button @click="$emit(\'edit\')">Modifier</button>' },
  TestsResultsTab: true, DefectsTab: true, HistoryTab: true,
  RouterLink: { template: '<a><slot/></a>' },
}
const mocks = { $route: { params: { pid: '1', id: '1' }, query: {} }, $router: { push: vi.fn() } }

async function page() {
  getCase.mockResolvedValue(detailSansMetierRedige())
  const w = mount(CaseDetailTR, { global: { stubs, mocks } })
  await flushPromises()
  return w
}

beforeEach(() => { getCase.mockReset(); updateCaseMetier.mockReset() })

async function ouvrirEdition(w: any) {
  await w.get('button').trigger('click')   // « Modifier » (stub CaseHeader, seul bouton présent)
  await flushPromises()
}
function bouton(w: any, texte: string) {
  return w.findAll('button').find((b: any) => b.text().includes(texte))
}

describe('CaseDetailTR — Modifier puis Enregistrer sans rien changer', () => {
  it("n'appelle PAS le serveur et ne crée aucune version quand rien n'a été touché", async () => {
    const w = await page()
    await ouvrirEdition(w)
    expect(bouton(w, 'Enregistrer')).toBeDefined()

    await bouton(w, 'Enregistrer')!.trigger('click')
    await flushPromises()

    expect(updateCaseMetier).not.toHaveBeenCalled()
    // Le formulaire se ferme quand même — comme si « Enregistrer » n'avait rien eu à faire.
    expect(bouton(w, 'Enregistrer')).toBeUndefined()
  })

  it('appelle bien le serveur dès que quelque chose a réellement changé', async () => {
    updateCaseMetier.mockResolvedValue({})
    const w = await page()
    await ouvrirEdition(w)

    const champ = w.find('textarea')
    await champ.setValue('Un employé est déjà connecté.')
    await bouton(w, 'Enregistrer')!.trigger('click')
    await flushPromises()

    expect(updateCaseMetier).toHaveBeenCalledTimes(1)
    const [, corps] = updateCaseMetier.mock.calls[0]
    expect(corps.preconditions).toBe('Un employé est déjà connecté.')
  })

  it("ajouter puis retirer une étape vide n'est pas un changement (repli sur l'aperçu dérivé)", async () => {
    const w = await page()
    await ouvrirEdition(w)

    await bouton(w, 'Ajouter une étape')!.trigger('click')
    const inputs = w.findAll('input').filter((i: any) => i.attributes('class')?.includes('flex-1'))
    await inputs[inputs.length - 1].setValue('   ')  // rien d'utile, sera filtré au trim
    // On retire aussitôt le champ vide qu'on vient d'ajouter — retour à l'état initial.
    const derniereSuppr = w.findAll('button').filter((b: any) => b.attributes('aria-label') === 'Supprimer')
    await derniereSuppr[derniereSuppr.length - 1].trigger('click')

    await bouton(w, 'Enregistrer')!.trigger('click')
    await flushPromises()

    expect(updateCaseMetier).not.toHaveBeenCalled()
  })
})
