/**
 * Onglet Script — consultation PAR VERSION (2026-08-11).
 *
 * Une régénération (spec plus évoluée, réparation automatique...) crée une NOUVELLE version,
 * jamais un écrasement — le contenu de chaque version était déjà transmis par l'API
 * (`versions[].feature_content`/`steps_content`), mais rien à l'écran ne le rendait consultable :
 * l'onglet Script montrait toujours la version courante, sans échappatoire.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import type { CaseDetail } from '../lib/api'

const getCase = vi.fn()
const getScriptEffectif = vi.fn()
vi.mock('../lib/api', () => ({
  // Temps réel (SSE, audit 2026-09-07) : un faux flux qui ne fait jamais rien — ces tests
  // portent sur la consultation par version, pas sur la mise à jour en direct.
  openProjectEvents: () => ({ close: () => {}, onmessage: null }),
  api: {
    getCase: (...a: any[]) => getCase(...a),
    getCaseScenarios: vi.fn().mockResolvedValue([]),
    listCases: vi.fn().mockResolvedValue({ items: [] }),
    updateCaseScript: vi.fn().mockResolvedValue({}),
    getScriptEffectif: (...a: any[]) => getScriptEffectif(...a),
  },
  roleSuffisant: (role: string, min: string) =>
    ['lecture_seule', 'testeur', 'dev', 'admin'].indexOf(role) >= ['lecture_seule', 'testeur', 'dev', 'admin'].indexOf(min),
}))
vi.mock('../lib/useSession', () => ({
  useSession: () => ({ session: { value: { role: 'dev', name: 'Awa' } } }),
}))

import CaseDetailTR from '../pages/CaseDetailTR.vue'

// Route/routeur RÉACTIFS — la fonctionnalité est PORTÉE PAR L'URL (`?version=`), comme `tab` :
// un mock statique ne peut pas exercer un changement de query en cours de test.
const route = reactive<{ params: Record<string, string>; query: Record<string, string> }>(
  { params: { pid: '1', id: '1' }, query: { tab: 'script' } })
const router = {
  push: vi.fn(),
  replace: vi.fn((to: { query?: Record<string, string> }) => {
    if (!to.query) return
    for (const k of Object.keys(route.query)) delete route.query[k]
    Object.assign(route.query, to.query)
  }),
}
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => router,
}))

const V1 = {
  id: 7, version_number: 1, feature_content: '# language: fr\nScénario: ancien',
  steps_content: 'def ancien(): pass', created_at: '2026-08-01T10:00:00Z',
  created_by: 'ia', preconditions: '', test_steps: '', expected_result: '',
  spec_hash: '', change_summary: '',
}
const V2 = {
  id: 8, version_number: 2, feature_content: '# language: fr\nScénario: courant',
  steps_content: 'def courant(): pass', created_at: '2026-08-10T10:00:00Z',
  created_by: 'ia', preconditions: '', test_steps: '', expected_result: '',
  spec_hash: '', change_summary: 'spec mise à jour',
}

function detail(): CaseDetail {
  return {
    case: { id: 1, title: 'Cas', etat: 'new', type: 'fonctionnel', refs: '', estimate: '' } as any,
    current_version_id: 8,
    versions: [V1, V2],
    reviews: [], executions: [],
    gate: { allowed: true, needs_review: false, reason: '', repair_budget: 0, repair_budget_default: 2 },
  } as any
}

const stubs = { CaseHeader: true, TestsResultsTab: true, DefectsTab: true }

beforeEach(() => {
  getCase.mockReset().mockResolvedValue(detail())
  getScriptEffectif.mockReset().mockResolvedValue({
    feature_content: V2.feature_content, steps_content: V2.steps_content,
    shared_steps: [{ keyword: 'when', label: 'un step partagé', source: 'generic/x.py',
                    note: '', code: 'def step_partage(): pass' }],
    steps_effectif: `${V2.steps_content}\n\ndef step_partage(): pass`,
  })
  router.push.mockClear()
  router.replace.mockClear()
  route.query = { tab: 'script' }
})

describe('CaseDetailTR — onglet Script, consultation par version', () => {
  it('affiche la version COURANTE par défaut', async () => {
    const w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()
    expect(w.text()).toContain('Scénario: courant')
    expect(w.text()).not.toContain('Scénario: ancien')
    expect(w.text()).not.toContain('pas la version courante')
  })

  it('sélectionner une version passée affiche SON contenu et le bandeau lecture seule', async () => {
    const w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()

    await w.find('select').setValue('7')
    await flushPromises()

    expect(w.text()).toContain('Scénario: ancien')
    expect(w.text()).not.toContain('Scénario: courant')
    expect(w.text()).toContain('pas la version courante')
    // Pas de bouton « Modifier » sur une version qui n'est pas la courante, même pour un Dev.
    expect(w.findAll('button').some((b) => b.text() === 'Modifier')).toBe(false)
  })

  it('« Revenir à la version courante » restaure la version 2', async () => {
    route.query = { tab: 'script', version: '7' }
    const w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()
    expect(w.text()).toContain('Scénario: ancien')

    const revenir = w.findAll('button').find((b) => b.text().includes('Revenir à la version courante'))
    expect(revenir).toBeDefined()
    await revenir!.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('Scénario: courant')
    expect(w.text()).not.toContain('pas la version courante')
  })

  it('« Voir le script » depuis l\'Historique bascule sur l\'onglet Script à la bonne version', async () => {
    route.query = { tab: 'historique' }
    const w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()

    // Deux boutons « Voir le script » (un par version) — on cible précisément la ligne V1.
    const lien = w.findAll('button')
      .filter((b) => b.text().includes('Voir le script'))
      .find((b) => b.element.closest('.rounded-lg')?.textContent?.includes('Version : 1'))
    expect(lien).toBeDefined()
    await lien!.trigger('click')
    await flushPromises()

    expect(route.query.tab).toBe('script')
    expect(w.text()).toContain('Scénario: ancien')
  })
})

describe('CaseDetailTR — sélecteur « Script complet » (Phase 2)', () => {
  // `route` est un objet réactif PARTAGÉ par tout le fichier (mock de `vue-router`) : un
  // composant jamais démonté garde son `watch(versionAffichee, …)` actif et réagit encore aux
  // mutations de `route.query` faites par les tests SUIVANTS — invisible pour les assertions par
  // TEXTE (idempotentes), mais fausse le COMPTAGE d'appels à `getScriptEffectif`. Démonter
  // explicitement après chaque test coupe cette fuite.
  let w: ReturnType<typeof mount> | null = null
  afterEach(() => { w?.unmount(); w = null })

  it('affiche le fichier du cas par défaut, sans appeler getScriptEffectif', async () => {
    w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('def courant(): pass')
    expect(w.text()).not.toContain('step_partage')
    expect(getScriptEffectif).not.toHaveBeenCalled()
  })

  it('cliquer « Script complet » charge et affiche le script résolu, avec le bandeau lecture seule', async () => {
    w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()

    const bouton = w.findAll('button').find((b) => b.text() === 'Script complet')
    expect(bouton).toBeDefined()
    await bouton!.trigger('click')
    await flushPromises()

    expect(getScriptEffectif).toHaveBeenCalledWith(1, 8)
    expect(w.text()).toContain('step_partage')
    expect(w.text()).toContain('les steps partagés se modifient dans la bibliothèque')
  })

  it('revenir sur « Fichier du cas » réaffiche le script propre, sans nouvel appel', async () => {
    w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'Script complet')!.trigger('click')
    await flushPromises()

    await w.findAll('button').find((b) => b.text() === 'Fichier du cas')!.trigger('click')
    await flushPromises()

    expect(w.text()).not.toContain('step_partage')
    expect(w.text()).not.toContain('les steps partagés se modifient dans la bibliothèque')
  })

  it('le cache est PAR VERSION : re-cliquer sur la même version ne réappelle pas l\'API', async () => {
    w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'Script complet')!.trigger('click')
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'Fichier du cas')!.trigger('click')
    await w.findAll('button').find((b) => b.text() === 'Script complet')!.trigger('click')
    await flushPromises()

    expect(getScriptEffectif).toHaveBeenCalledTimes(1)
  })

  it('changer de version en vue « Script complet » recharge pour la nouvelle version', async () => {
    w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'Script complet')!.trigger('click')
    await flushPromises()
    expect(getScriptEffectif).toHaveBeenCalledWith(1, 8)

    await w.find('select').setValue('7')
    await flushPromises()

    expect(getScriptEffectif).toHaveBeenCalledWith(1, 7)
    expect(getScriptEffectif).toHaveBeenCalledTimes(2)
  })

  it('entrer en édition depuis la vue « Script complet » ne charge JAMAIS le texte fusionné dans le brouillon', async () => {
    w = mount(CaseDetailTR, { global: { stubs } })
    await flushPromises()
    await w.findAll('button').find((b) => b.text() === 'Script complet')!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('step_partage') // bien en vue fusionnée avant d'éditer

    await w.findAll('button').find((b) => b.text() === 'Modifier')!.trigger('click')
    await flushPromises()

    const textarea = w.findAll('textarea')[1] // [0] = Gherkin, [1] = Python
    expect(textarea.element.value).toBe(V2.steps_content)
    expect(textarea.element.value).not.toContain('step_partage')
  })
})
