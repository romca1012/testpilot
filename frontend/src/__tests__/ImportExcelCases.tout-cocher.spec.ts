/**
 * Porteur, 2026-10-23 — import Excel : une ligne sans étapes ni résultat attendu reconnus est décochée d'office. Quand la
 * colonne n'a pas été devinée, toutes le sont : un geste « Tout cocher / Tout décocher » évite de les recocher une à une.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const previewExcelImport = vi.fn()
const confirmExcelImport = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    listModules: () => Promise.resolve([{ id: 3, name: 'Ventes' }]),
    listGroups: () => Promise.resolve([]),
    previewExcelImport: (...a: any[]) => previewExcelImport(...a),
    confirmExcelImport: (...a: any[]) => confirmExcelImport(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import ImportExcelCases from '../pages/ImportExcelCases.vue'

const ligne = (n: number) => ({ numero_ligne: n, titre: `Cas ${n}`, identifiant: '', section: '', priority: '',
  statut_manuel: null, test_steps: [], avertissements: ['ligne ignorée par défaut — étapes manquant(s)'], retenue: false })

beforeEach(() => {
  vi.clearAllMocks()
  previewExcelImport.mockResolvedValue({ fichier_hash: 'h', filename: 'c.xlsx', feuilles_disponibles: ['F'], feuille: 'F',
    ligne_entete: 1, mapping: {}, entetes_brutes: { 1: 'Titre' }, lignes: [ligne(2), ligne(3), ligne(4)] })
  confirmExcelImport.mockResolvedValue({ cree: 3, ignore: 0, run_id: null })
})

async function apercu() {
  const w = monter(ImportExcelCases)
  await flushPromises()
  const fichier = w.get('input[type="file"]')
  Object.defineProperty(fichier.element, 'files', { value: [new File(['x'], 'c.xlsx')] })
  await fichier.trigger('change')
  await w.findAll('button').find((b) => b.text().includes('Analyser'))!.trigger('click')
  await flushPromises()
  return w
}

describe('Import Excel — tout cocher', () => {
  it('falsifiable : un geste coche toutes les lignes décochées d’office, et elles partent toutes', async () => {
    const w = await apercu()
    expect(w.text()).toContain('0 retenu sur 3')

    await w.get('[data-testid="tout-cocher"]').trigger('click')
    expect(w.text()).toContain('3 retenus sur 3')
    expect(w.get('[data-testid="tout-cocher"]').text()).toBe('Tout décocher')

    await w.findAll('button').find((b) => b.text().includes('Confirmer'))!.trigger('click')
    await flushPromises()
    expect(confirmExcelImport.mock.calls[0][1].numeros_lignes_retenues).toEqual([2, 3, 4])
  })

  it('tout décocher remet à zéro', async () => {
    const w = await apercu()
    await w.get('[data-testid="tout-cocher"]').trigger('click')
    await w.get('[data-testid="tout-cocher"]').trigger('click')
    expect(w.text()).toContain('0 retenu sur 3')
  })
})
