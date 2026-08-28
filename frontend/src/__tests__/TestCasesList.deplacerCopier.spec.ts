/**
 * Déplacer / copier un cas entre sections, depuis la liste des cas — glisser-déposer natif
 * (étape 2bis, parité TestRail, 2026-08-06) : une poignée par ligne, un dépôt sur une Section,
 * un petit menu AU POINT DE DÉPÔT (sauf Ctrl/Cmd ou Maj, qui agissent tout de suite). Remplace
 * l'ancien menu ⋮ → liste de cibles (étape 2).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listCases = vi.fn()
const listGroups = vi.fn()
const deplacerCas = vi.fn()
const copierCas = vi.fn()

vi.mock('../lib/api', () => ({
  roleSuffisant: () => true,
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listCases: (...a: any[]) => listCases(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    deplacerCas: (...a: any[]) => deplacerCas(...a),
    copierCas: (...a: any[]) => copierCas(...a),
    renameModule: vi.fn(),
  },
}))

const routerPush = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push: routerPush }),
  RouterLink: { template: '<a><slot/></a>', props: ['to'] },
}))

import TestCasesList from '../pages/TestCasesList.vue'

const CAS = [
  { id: 95, title: 'Cas A', module: 'Demandes', module_id: 10,
    group_id: 86, group_title: 'Section A', type: 'fonctionnel', etat: 'new',
    priority: 'medium', last_execution_status: null, last_functional_status: null, statut: 'untested' },
]

const GROUPES = [
  { id: 86, module_id: 10, title: 'Section A', case_count: 1, parent_group_id: null },
  { id: 87, module_id: 10, title: 'Section B', case_count: 0, parent_group_id: null },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  listModules.mockResolvedValue([{ id: 10, name: 'Demandes', case_count: 1 }])
  listCases.mockResolvedValue({ items: CAS, next_cursor: null, total: CAS.length })
  listGroups.mockResolvedValue(GROUPES)
})

async function monterListe() {
  const w = monter(TestCasesList)
  await flushPromises()
  await flushPromises()
  return w
}

// `dataTransfer` minimal — jsdom n'implémente pas l'API DragEvent, patron standard pour tester
// le glisser-déposer natif sous VTU : un magasin clé/valeur passé tel quel via `trigger()`.
function fakeDataTransfer() {
  const store: Record<string, string> = {}
  return {
    setData: (type: string, value: string) => { store[type] = value },
    getData: (type: string) => store[type] ?? '',
    get types() { return Object.keys(store) },
  }
}

function poigneeDuCas(w: any) {
  return w.find('[aria-label="Glisser ce cas vers une autre section"]')
}
function enteteSection(w: any, titre: string) {
  return w.findAll('tr').find((r: any) => r.text().includes(titre))!
}

async function glisserCasVersSection(w: any, opts: { ctrlKey?: boolean; shiftKey?: boolean } = {}) {
  const dt = fakeDataTransfer()
  await poigneeDuCas(w).trigger('dragstart', { dataTransfer: dt })
  await enteteSection(w, 'Section B').trigger('drop', { dataTransfer: dt, ...opts })
}

describe('glisser-déposer un cas vers une autre section', () => {
  it('un dépôt simple ouvre le menu flottant AU POINT DE DÉPÔT, sans agir tout de suite', async () => {
    const w = await monterListe()
    await glisserCasVersSection(w)

    expect(deplacerCas).not.toHaveBeenCalled()
    expect(copierCas).not.toHaveBeenCalled()
    expect(w.text()).toContain('Déplacer ici (ctrl/cmd)')
    expect(w.text()).toContain('Copier ici (maj)')
    expect(w.text()).toContain('Annuler')
  })

  it('« Déplacer ici » du menu flottant appelle deplacerCas avec la bonne section', async () => {
    deplacerCas.mockResolvedValue({ id: 95 })
    const w = await monterListe()
    await glisserCasVersSection(w)

    const bouton = w.findAll('button').find((b: any) => b.text() === 'Déplacer ici (ctrl/cmd)')!
    await bouton.trigger('click')
    await flushPromises()

    expect(deplacerCas).toHaveBeenCalledWith(95, 87)
  })

  it('« Copier ici » du menu flottant appelle copierCas, pas deplacerCas', async () => {
    copierCas.mockResolvedValue({ id: 200 })
    const w = await monterListe()
    await glisserCasVersSection(w)

    const bouton = w.findAll('button').find((b: any) => b.text() === 'Copier ici (maj)')!
    await bouton.trigger('click')
    await flushPromises()

    expect(copierCas).toHaveBeenCalledWith(95, 87)
    expect(deplacerCas).not.toHaveBeenCalled()
  })

  it('« Annuler » ferme le menu sans rien appeler', async () => {
    const w = await monterListe()
    await glisserCasVersSection(w)

    const bouton = w.findAll('button').find((b: any) => b.text() === 'Annuler')!
    await bouton.trigger('click')
    await flushPromises()

    expect(deplacerCas).not.toHaveBeenCalled()
    expect(copierCas).not.toHaveBeenCalled()
    expect(w.text()).not.toContain('Déplacer ici (ctrl/cmd)')
  })

  it('un dépôt avec Ctrl/Cmd déplace directement, SANS faire apparaître le menu', async () => {
    deplacerCas.mockResolvedValue({ id: 95 })
    const w = await monterListe()
    await glisserCasVersSection(w, { ctrlKey: true })
    await flushPromises()

    expect(deplacerCas).toHaveBeenCalledWith(95, 87)
    expect(w.text()).not.toContain('Annuler')
  })

  it('un dépôt avec Maj copie directement, SANS faire apparaître le menu', async () => {
    copierCas.mockResolvedValue({ id: 200 })
    const w = await monterListe()
    await glisserCasVersSection(w, { shiftKey: true })
    await flushPromises()

    expect(copierCas).toHaveBeenCalledWith(95, 87)
    expect(deplacerCas).not.toHaveBeenCalled()
    expect(w.text()).not.toContain('Annuler')
  })

  it('une erreur serveur s\'affiche, sans échouer en silence', async () => {
    deplacerCas.mockRejectedValue(new Error('cette section porte déjà un cas du même titre'))
    const w = await monterListe()
    await glisserCasVersSection(w, { ctrlKey: true })
    await flushPromises()

    expect(w.text()).toContain('cette section porte déjà un cas du même titre')
  })

  it('cliquer la poignée seule (sans glisser) n\'ouvre PAS le cas', async () => {
    const w = await monterListe()
    await poigneeDuCas(w).trigger('click')

    expect(routerPush).not.toHaveBeenCalled()
  })
})
