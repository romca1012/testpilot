/**
 * Glisser-déposer une SECTION (pas un cas) — étape 2bis, parité TestRail, 2026-08-06 : imbriquer
 * une Section top-level sous une autre, repromouvoir une sous-section au premier niveau en la
 * lâchant sur l'en-tête du module, et le refus serveur (imbrication invalide) remonté sans agir
 * en silence. Une Section n'a jamais l'option « Copier » — copier dupliquerait en cascade tous
 * ses cas (décision actée, voir le plan).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listCases = vi.fn()
const listGroups = vi.fn()
const deplacerGroupe = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listCases: (...a: any[]) => listCases(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    deplacerGroupe: (...a: any[]) => deplacerGroupe(...a),
    renameModule: vi.fn(),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot/></a>', props: ['to'] },
}))

import TestCasesList from '../pages/TestCasesList.vue'

const CAS = [
  { id: 95, title: 'Cas A', module: 'Demandes', module_id: 10,
    group_id: 86, group_title: 'Section A', type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
  { id: 96, title: 'Cas B', module: 'Demandes', module_id: 10,
    group_id: 87, group_title: 'Section B', type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
]

const GROUPES = [
  { id: 86, module_id: 10, title: 'Section A', case_count: 1, parent_group_id: null },
  { id: 87, module_id: 10, title: 'Section B', case_count: 1, parent_group_id: null },
  { id: 88, module_id: 10, title: 'Sous-section', case_count: 0, parent_group_id: 86 },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  listModules.mockResolvedValue([{ id: 10, name: 'Demandes', case_count: 2 }])
  listCases.mockResolvedValue({ items: CAS, next_cursor: null, total: CAS.length })
  listGroups.mockResolvedValue(GROUPES)
})

async function monterListe() {
  const w = monter(TestCasesList)
  await flushPromises()
  await flushPromises()
  return w
}

// `dataTransfer` minimal — même patron que TestCasesList.deplacerCopier.spec.ts.
function fakeDataTransfer() {
  const store: Record<string, string> = {}
  return {
    setData: (type: string, value: string) => { store[type] = value },
    getData: (type: string) => store[type] ?? '',
    get types() { return Object.keys(store) },
  }
}

// Une poignée de Section par titre : plusieurs sections partagent le même `title` d'icône, on
// désambiguïse par la ligne (`<tr>`) qui la porte.
function poigneeDeSection(w: any, titre: string) {
  return w.findAll('[title="Glisser pour déplacer cette section"]')
    .find((el: any) => el.element.closest('tr')?.textContent?.includes(titre))!
}
function poigneeDeSousSection(w: any, titre: string) {
  return w.findAll('[title="Glisser pour déplacer cette sous-section"]')
    .find((el: any) => el.element.closest('tr')?.textContent?.includes(titre))!
}
// L'événement `drop` bubblera jusqu'au conteneur de l'en-tête (Section ou module) qui porte
// réellement l'écouteur — pas besoin de cibler l'élément exact, JSDOM boucle les événements.
function enteteSection(w: any, titre: string) {
  return w.findAll('tr').find((r: any) => r.text().includes(titre))!
}
function nomDuModule(w: any, nom: string) {
  return w.findAll('span').find((el: any) => el.text() === nom)!
}

describe('glisser-déposer une Section', () => {
  it('glisser une Section top-level sur une autre l\'imbrique dessous', async () => {
    deplacerGroupe.mockResolvedValue(undefined)
    const w = await monterListe()
    const dt = fakeDataTransfer()

    await poigneeDeSection(w, 'Section A').trigger('dragstart', { dataTransfer: dt })
    await enteteSection(w, 'Section B').trigger('drop', { dataTransfer: dt, ctrlKey: true })
    await flushPromises()

    expect(deplacerGroupe).toHaveBeenCalledWith(86, 87)
  })

  it('glisser une sous-section sur l\'en-tête du MODULE la repromeut en Section (parent_group_id: null)', async () => {
    deplacerGroupe.mockResolvedValue(undefined)
    const w = await monterListe()
    const dt = fakeDataTransfer()

    await poigneeDeSousSection(w, 'Sous-section').trigger('dragstart', { dataTransfer: dt })
    await nomDuModule(w, 'Demandes').trigger('drop', { dataTransfer: dt, ctrlKey: true })
    await flushPromises()

    expect(deplacerGroupe).toHaveBeenCalledWith(88, null)
  })

  it('un dépôt simple sur une Section ouvre le menu flottant avec SEULEMENT « Déplacer ici » — jamais « Copier »', async () => {
    const w = await monterListe()
    const dt = fakeDataTransfer()

    await poigneeDeSection(w, 'Section A').trigger('dragstart', { dataTransfer: dt })
    await enteteSection(w, 'Section B').trigger('drop', { dataTransfer: dt })

    expect(w.text()).toContain('Déplacer ici')
    expect(w.text()).not.toContain('Copier ici')
  })

  it('une Section refusée par le serveur (imbrication invalide) affiche l\'erreur, sans agir en silence', async () => {
    deplacerGroupe.mockRejectedValue(new Error('une section avec des sous-sections ne peut pas être imbriquée'))
    const w = await monterListe()
    const dt = fakeDataTransfer()

    await poigneeDeSection(w, 'Section A').trigger('dragstart', { dataTransfer: dt })
    await enteteSection(w, 'Section B').trigger('drop', { dataTransfer: dt, ctrlKey: true })
    await flushPromises()

    expect(w.text()).toContain('une section avec des sous-sections ne peut pas être imbriquée')
  })
})
