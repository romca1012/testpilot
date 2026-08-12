/**
 * Onglet Script — consultation PAR VERSION (2026-08-11).
 *
 * Une régénération (spec plus évoluée, réparation automatique...) crée une NOUVELLE version,
 * jamais un écrasement — le contenu de chaque version était déjà transmis par l'API
 * (`versions[].feature_content`/`steps_content`), mais rien à l'écran ne le rendait consultable :
 * l'onglet Script montrait toujours la version courante, sans échappatoire.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import type { CaseDetail } from '../lib/api'

const getCase = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    getCase: (...a: any[]) => getCase(...a),
    getCaseScenarios: vi.fn().mockResolvedValue([]),
    listCases: vi.fn().mockResolvedValue({ items: [] }),
    updateCaseScript: vi.fn().mockResolvedValue({}),
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
