/**
 * Sous-sections dans la liste des cas (migration 28, 2026-08-06) — parité TestRail : une Section
 * peut désormais en contenir d'autres, affichées imbriquées, avec les liens « Ajouter un cas » /
 * « Ajouter une sous-section » à l'endroit où TestRail les place — sous chaque Section/module dans
 * l'écran principal, pas dans la barre latérale (retirée dans le même lot).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'
import { useSectionCreate } from '../lib/useSectionCreate'

const listModules = vi.fn()
const listCases = vi.fn()
const listGroups = vi.fn()

vi.mock('../lib/api', () => ({
  roleSuffisant: () => true,
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listCases: (...a: any[]) => listCases(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    renameModule: vi.fn(),
    deleteGroup: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot/></a>', props: ['to'] },
}))

import TestCasesList from '../pages/TestCasesList.vue'

// Une Section « Notifications » (86) avec une sous-section « Email » (88) qui porte un cas ; la
// Section elle-même a aussi un cas direct — le cas le plus révélateur : les deux niveaux coexistent.
const CAS = [
  { id: 95, title: 'Notification créée', module: 'Demandes', module_id: 10,
    group_id: 86, group_title: 'Notifications', type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
  { id: 96, title: "Email envoyé à l'ouverture", module: 'Demandes', module_id: 10,
    group_id: 88, group_title: 'Email', type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
]

const GROUPES = [
  { id: 86, module_id: 10, title: 'Notifications', case_count: 1, parent_group_id: null },
  { id: 88, module_id: 10, title: 'Email', case_count: 1, parent_group_id: 86 },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  listModules.mockResolvedValue([{ id: 10, name: 'Demandes', case_count: 2 }])
  listCases.mockResolvedValue({ items: CAS, next_cursor: null, total: CAS.length })
  listGroups.mockResolvedValue(GROUPES)
  // Le composable est un SINGLETON module-level : on le remet à zéro entre les tests, sinon
  // l'état d'un test précédent (modale ouverte) fuit dans le suivant.
  useSectionCreate().close()
})

async function monterListe() {
  const w = monter(TestCasesList)
  await flushPromises()
  await flushPromises()
  return w
}

describe('les sous-sections dans la liste des cas', () => {
  it('une sous-section apparaît imbriquée sous sa Section, avec son propre cas', async () => {
    const w = await monterListe()
    const texte = w.text()
    expect(texte).toContain('Notifications')
    expect(texte).toContain('Email')
    expect(texte).toContain('Notification créée')
    expect(texte).toContain("Email envoyé à l'ouverture")
    // La sous-section apparaît APRÈS sa Section parente, pas avant.
    expect(texte.indexOf('Notifications')).toBeLessThan(texte.indexOf('Email'))
  })

  it('« Ajouter une section » sous le module ouvre la modale pour CE module', async () => {
    const w = await monterListe()
    const bouton = w.findAll('button').find((b) => b.text() === '+ Ajouter une section')!

    await bouton.trigger('click')

    const sc = useSectionCreate()
    expect(sc.open.value).toBe(true)
    expect(sc.moduleId.value).toBe(10)
    expect(sc.parentGroupId.value).toBe(null)
  })

  it('« Ajouter une sous-section » sous une Section ouvre la modale avec CETTE Section en parent', async () => {
    const w = await monterListe()
    const bouton = w.findAll('button').find((b) => b.text() === 'Ajouter une sous-section')!

    await bouton.trigger('click')

    const sc = useSectionCreate()
    expect(sc.open.value).toBe(true)
    expect(sc.moduleId.value).toBe(10)
    expect(sc.parentGroupId.value).toBe(86)
  })

  it('aucun lien « Ajouter une sous-section » sous une sous-section — une seule profondeur', async () => {
    const w = await monterListe()
    const liens = w.findAll('button').filter((b) => b.text() === 'Ajouter une sous-section')
    // Une seule Section porte ce lien (« Notifications ») ; « Email », la sous-section, n'en a pas.
    expect(liens.length).toBe(1)
  })

  it('une Section VIDE (sans cas) apparaît quand même, avec ses liens', async () => {
    listGroups.mockResolvedValue([
      ...GROUPES,
      { id: 89, module_id: 10, title: 'Section vide', case_count: 0, parent_group_id: null },
    ])
    const w = await monterListe()

    expect(w.text()).toContain('Section vide')
  })
})
