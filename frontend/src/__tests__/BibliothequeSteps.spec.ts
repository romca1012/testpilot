/**
 * Bibliothèque de steps partagés (2026-08-11) — jusqu'ici visible SEULEMENT du prompt système de
 * l'agent de génération. Deux règles à ne pas casser : groupée par mot-clé Gherkin dans l'ordre
 * Soit → Quand → Alors (pas l'ordre d'arrivée du serveur), et la recherche filtre sur le libellé
 * ET la note ET le fichier d'origine.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listSharedSteps = vi.fn()
vi.mock('../lib/api', () => ({ api: { listSharedSteps: (...a: any[]) => listSharedSteps(...a) } }))

import BibliothequeSteps from '../pages/BibliothequeSteps.vue'

const STEPS = [
  { keyword: 'then', label: 'le champ "{f}" est vide', source: '_base_steps.py', note: '' },
  { keyword: 'given', label: 'je suis authentifié', source: '_base_steps.py',
    note: 'ouvre une session Odoo réelle' },
  { keyword: 'when', label: 'je clique sur "{label}"', source: '_generic_steps.py', note: '' },
]

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

async function page(steps = STEPS) {
  listSharedSteps.mockResolvedValue(steps)
  const w = mount(BibliothequeSteps, { global: { stubs } })
  await flushPromises()
  return w
}

beforeEach(() => vi.clearAllMocks())

describe('BibliothequeSteps', () => {
  it('groupe par mot-clé Gherkin, dans l\'ordre Soit → Quand → Alors', async () => {
    const w = await page()
    const headings = w.findAll('h2').map((h) => h.text())
    const ordre = headings.map((h) => (h.includes('Soit') ? 0 : h.includes('Quand') ? 1 : 2))
    expect(ordre).toEqual([...ordre].sort())
    expect(w.text()).toContain('Soit')
    expect(w.text()).toContain('Quand')
    expect(w.text()).toContain('Alors')
  })

  it('affiche la note quand elle existe', async () => {
    const w = await page()
    expect(w.text()).toContain('ouvre une session Odoo réelle')
  })

  it('la recherche filtre sur le libellé, la note ET le fichier d\'origine', async () => {
    const w = await page()
    await w.find('input[type="search"]').setValue('generic')
    await flushPromises()
    expect(w.text()).toContain('je clique sur')
    expect(w.text()).not.toContain('je suis authentifié')
  })

  it('liste vide : dit qu\'il n\'y a rien plutôt que de rendre un écran cassé', async () => {
    const w = await page([])
    expect(w.text()).toContain('Bibliothèque vide')
  })
})
