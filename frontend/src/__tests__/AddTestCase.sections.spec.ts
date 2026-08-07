/**
 * Choix de la Section, sur l'écran de spécification, AVANT de lancer la génération — étape 3bis,
 * 2026-08-07 (retour du manager du porteur sur l'étape 3 initiale, qui la choisissait cas par
 * cas après coup).
 *
 * Ce que ces tests figent :
 * - un sélecteur unique, MÊME PATRON que le Module (existante ou « + Créer une section… »),
 *   OBLIGATOIRE au même titre que lui — impossible de soumettre sans Section choisie/nommée ;
 * - la liste propose les Sections/sous-sections du module ciblé, au format
 *   « Section › Sous-section » (même convention que le glisser-déposer de l'étape 2bis) ;
 * - le sélecteur se vide si le Module change (une Section n'existe que sous un module précis) ;
 * - créer une Section se fait AVANT le premier appel LLM, exactement comme un module.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listGroups = vi.fn()
const addCase = vi.fn()
const getGenerationJob = vi.fn()
const createModule = vi.fn()
const createGroup = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    addCase: (...a: any[]) => addCase(...a),
    getGenerationJob: (...a: any[]) => getGenerationJob(...a),
    validateMetier: vi.fn(),
    createModule: (...a: any[]) => createModule(...a),
    createGroup: (...a: any[]) => createGroup(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push }),
}))

import AddTestCase from '../pages/AddTestCase.vue'

const MODULES = [
  { id: 1, name: 'Demandes' },
  { id: 2, name: 'Facturation' },
]
const GROUPES = [
  { id: 50, module_id: 1, title: 'Connexion', case_count: 0, parent_group_id: null },
  { id: 51, module_id: 1, title: 'Facturation', case_count: 0, parent_group_id: null },
  { id: 52, module_id: 1, title: 'Relance', case_count: 0, parent_group_id: 51 },
  { id: 53, module_id: 2, title: 'Ailleurs', case_count: 0, parent_group_id: null },
]

beforeEach(() => {
  vi.clearAllMocks()
  listModules.mockResolvedValue(MODULES)
  listGroups.mockResolvedValue(GROUPES)
  addCase.mockResolvedValue({ job_id: 'J1', status: 'running', case_ids: [], error: '' })
})

async function monterEcran() {
  const w = monter(AddTestCase)
  await flushPromises()
  return w
}

function selectSection(w: any) {
  return w.findAll('select')[1]   // [0] = Module, [1] = Section
}

describe('sélecteur de Section, avant génération', () => {
  it('propose les Sections/sous-sections DU MODULE CIBLÉ, au format « Section › Sous-section »', async () => {
    const w = await monterEcran()

    const options = selectSection(w).findAll('option').map((o: any) => o.text())
    expect(options).toContain('Connexion')
    expect(options).toContain('Facturation › Relance')
    expect(options).not.toContain('Ailleurs')   // appartient au module 2, pas au module 1 ciblé
  })

  it('le bouton est DÉSACTIVÉ tant qu\'aucune Section n\'est choisie', async () => {
    const w = await monterEcran()
    await w.find('textarea').setValue('La spécification')

    const bouton = w.find('button[type=submit]')
    expect(bouton.attributes('disabled')).toBeDefined()
  })

  it('choisir une Section existante l\'envoie à addCase', async () => {
    const w = await monterEcran()
    await w.find('textarea').setValue('La spécification')
    await selectSection(w).setValue('50')
    await flushPromises()

    const bouton = w.find('button[type=submit]')
    expect(bouton.attributes('disabled')).toBeUndefined()

    await w.find('form').trigger('submit')
    await flushPromises()

    expect(addCase).toHaveBeenCalledWith(1, 'La spécification', '', 50)
  })

  it('le choix se VIDE si le Module change (une Section est module-scoped)', async () => {
    const w = await monterEcran()
    await selectSection(w).setValue('50')
    await flushPromises()

    await w.findAll('select')[0].setValue('2')   // bascule sur le module Facturation
    await flushPromises()

    // Le nouveau module a « Ailleurs » comme seule Section — « Connexion » (module 1) a disparu.
    const options = selectSection(w).findAll('option').map((o: any) => o.text())
    expect(options).toContain('Ailleurs')
    expect(options).not.toContain('Connexion')
    // Et le bouton redevient désactivé : le choix précédent ne survit pas au changement.
    await w.find('textarea').setValue('La spécification')
    expect(w.find('button[type=submit]').attributes('disabled')).toBeDefined()
  })
})

describe('« + Créer une section… », AVANT le premier appel LLM', () => {
  it('crée la Section puis l\'envoie à addCase, dans cet ordre', async () => {
    createGroup.mockResolvedValue({ id: 99, module_id: 1, title: 'Toute nouvelle', case_count: 0 })
    const w = await monterEcran()
    await w.find('textarea').setValue('La spécification')
    await selectSection(w).setValue('-2')   // NOUVELLE_SECTION
    await flushPromises()

    const nomSection = w.findAll('input').find((i: any) => i.attributes('placeholder')?.includes('Nom de la section'))!
    await nomSection.setValue('Toute nouvelle')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createGroup).toHaveBeenCalledWith(1, { title: 'Toute nouvelle' })
    expect(addCase).toHaveBeenCalledWith(1, 'La spécification', '', 99)
  })

  it('une erreur de création REMONTE sans lancer addCase (pas de dépense pour rien)', async () => {
    createGroup.mockRejectedValue(new Error('ce module a déjà une spécification « Toute nouvelle »'))
    const w = await monterEcran()
    await w.find('textarea').setValue('La spécification')
    await selectSection(w).setValue('-2')
    await flushPromises()
    const nomSection = w.findAll('input').find((i: any) => i.attributes('placeholder')?.includes('Nom de la section'))!
    await nomSection.setValue('Toute nouvelle')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(w.text()).toContain('déjà une spécification')
    expect(addCase).not.toHaveBeenCalled()
  })

  it('un module SANS aucune section propose directement le champ de création', async () => {
    listGroups.mockResolvedValue([])
    const w = await monterEcran()

    expect(w.find('select').exists()).toBe(true)   // le sélecteur de Module, lui, existe
    // Aucune Section dans ce module : pas de <select> de Section, directement le champ texte.
    const selects = w.findAll('select')
    expect(selects.length).toBe(1)
    expect(w.findAll('input').some((i: any) => i.attributes('placeholder')?.includes('Nom de la section'))).toBe(true)
  })
})
