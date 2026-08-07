/**
 * « Sélectionner des cas de test spécifiques » (AddTestRunForm.vue) — le picker groupait
 * uniquement par Module, hérité d'avant les Sections/Sous-sections. Mis à jour le 2026-08-07
 * (demande du porteur : « l'affichage des cas doit être modifié conformément à leur nouvelle
 * structure ») pour Module → Section → Sous-section, même hiérarchie que `TestCasesList.vue`.
 *
 * Ce que ces tests figent :
 * - un cas apparaît sous SA Section, sous SA sous-section (pas juste sous son module) ;
 * - une Section/sous-section SANS AUCUN cas n'apparaît pas (picker, pas outil de gestion) ;
 * - un cas sans `group_id` (orphelin) tombe dans « Sans section », jamais perdu ;
 * - cocher une Section coche AUSSI ses sous-sections ; cocher une sous-section reste local à elle.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listCases = vi.fn()
const listGroups = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listCases: (...a: any[]) => listCases(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    createRun: vi.fn(),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import AddTestRunForm from '../pages/AddTestRunForm.vue'

function cas(id: number, title: string, moduleId: number, moduleName: string,
            groupId: number | null, groupTitle: string | null) {
  return {
    id, title, module: moduleName, module_id: moduleId, project_id: 1,
    group_id: groupId, group_title: groupTitle, refs: '', estimate: '',
    type: 'fonctionnel', etat: 'new', statut: 'untested', priority: 'medium',
    last_execution_status: null, last_functional_status: null, last_executed_at: null,
    last_verdict_version_id: null, verdict_from_other_version: false,
  }
}

const CASES = [
  cas(1, 'Connexion réussie', 10, 'Demandes', 100, 'Connexion'),
  cas(2, 'Connexion refusée', 10, 'Demandes', 100, 'Connexion'),
  cas(3, 'Lien expiré', 10, 'Demandes', 101, 'Réinitialisation'),
  cas(4, 'Cas orphelin', 10, 'Demandes', null, null),
]
const GROUPES = [
  { id: 100, module_id: 10, title: 'Connexion', case_count: 2, parent_group_id: null },
  { id: 101, module_id: 10, title: 'Réinitialisation', case_count: 1, parent_group_id: 100 },
  { id: 102, module_id: 10, title: 'Section vide', case_count: 0, parent_group_id: null },
]

beforeEach(() => {
  vi.clearAllMocks()
  listCases.mockResolvedValue({ items: CASES, next_cursor: null, total: CASES.length })
  listGroups.mockResolvedValue(GROUPES)
})

async function ouvrirLeChoix() {
  const w = monter(AddTestRunForm)
  await flushPromises()
  await flushPromises()
  const radio = w.findAll('input[type=radio]').find(
    (r: any) => r.attributes('value') === 'frozen')!
  await radio.setValue()
  await flushPromises()
  return w
}

describe('AddTestRunForm — cas groupés Module → Section → Sous-section', () => {
  it('un cas apparaît sous sa Section, une sous-section sous sa Section', async () => {
    const w = await ouvrirLeChoix()

    const texte = w.text()
    expect(texte).toContain('Connexion')
    expect(texte).toContain('Réinitialisation')
    expect(texte).toContain('Connexion réussie')
    expect(texte).toContain('Lien expiré')
  })

  it('une Section SANS AUCUN cas n\'apparaît pas — c\'est un picker, pas la gestion des sections', async () => {
    const w = await ouvrirLeChoix()

    expect(w.text()).not.toContain('Section vide')
  })

  it('un cas SANS group_id tombe dans « Sans section », jamais perdu', async () => {
    const w = await ouvrirLeChoix()

    expect(w.text()).toContain('Sans section')
    expect(w.text()).toContain('Cas orphelin')
  })

  it('cocher la Section « Connexion » coche AUSSI sa sous-section « Réinitialisation »', async () => {
    const w = await ouvrirLeChoix()

    const boutonSection = w.findAll('button').find((b: any) => b.text().includes('Connexion') && b.text().includes('cas'))!
    await boutonSection.trigger('click')

    // Les 3 cas de la branche (2 directs + 1 en sous-section) doivent être cochés.
    const cases = w.findAll('input[type=checkbox]')
    const cochees = cases.filter((c: any) => (c.element as HTMLInputElement).checked)
    expect(cochees.length).toBe(3)
  })

  it('cocher la sous-section « Réinitialisation » reste LOCAL à elle-même', async () => {
    const w = await ouvrirLeChoix()

    const boutonSousSection = w.findAll('button').find((b: any) => b.text().includes('Réinitialisation'))!
    await boutonSousSection.trigger('click')

    const cases = w.findAll('input[type=checkbox]')
    const cochees = cases.filter((c: any) => (c.element as HTMLInputElement).checked)
    expect(cochees.length).toBe(1)   // seulement « Lien expiré »
  })
})
