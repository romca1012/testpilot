/**
 * Étape 7 (A110) — « Calcul détecté » sur l'écran de validation des cas, et les trois choix.
 *
 * Ce que ces tests gardent :
 * 1. sans choix, pas de calcul : la validation part sans fiche retenue (le défaut) ;
 * 2. la fiche de l'IA, une fois choisie, ne part que PRÊTE (vérifiée par le serveur : exemples retrouvés, taux datés) —
 *    sinon le bouton de validation reste éteint (falsifiabilité) ;
 * 3. « Calcul nécessaire » sur un cas non détecté ouvre les choix, et le calcul fourni part avec origine « personne ».
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listGroups = vi.fn()
const addCase = vi.fn()
const getGenerationJob = vi.fn()
const validateMetier = vi.fn()
const verifierFiche = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    addCase: (...a: any[]) => addCase(...a),
    getGenerationJob: (...a: any[]) => getGenerationJob(...a),
    validateMetier: (...a: any[]) => validateMetier(...a),
    verifierFiche: (...a: any[]) => verifierFiche(...a),
    createModule: vi.fn(),
    createGroup: vi.fn(),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

import AddTestCase from '../pages/AddTestCase.vue'

const FICHE = { nom: 'Total TTC', resultat: 'total', unite: 'EUR',
  elements: [{ nom: 'quantite', source: 'la quantité' }, { nom: 'taux_tva', valeur: '20', source: '20 % de TVA' }],
  etapes: [{ resultat: 'total', operation: 'pourcentage', de: 'quantite', taux: 'taux_tva' }],
  exemples: [], a_confirmer: ['exemple chiffré à fournir'] }
const DETECTE = { title: 'Total', preconditions: '', steps: ['Commander'], expected_result: 'Le total s\'affiche',
                  calcul_detecte: 'le total dépend de la quantité', fiches_proposees: [FICHE] }
const SIMPLE = { title: 'Consulter', preconditions: '', steps: ['Ouvrir'], expected_result: 'Affiché' }
const PRETE = { utilisable: true, erreur: '', entrees: ['quantite'], a_confirmer: [],
                exemples: [{ numero: 1, attendu: '36', obtenu: '36', retrouve: true, detail: [] }] }
const A_CORRIGER = { utilisable: false, erreur: 'élément « taux_tva » : sa date de vérification manque', entrees: ['quantite'],
                     a_confirmer: [], exemples: [] }

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  listModules.mockResolvedValue([{ id: 1, name: 'Boutique' }])
  listGroups.mockResolvedValue([{ id: 50, module_id: 1, title: 'Boutique', case_count: 0, parent_group_id: null }])
  addCase.mockResolvedValue({ job_id: 'J1', status: 'running', case_ids: [], error: '' })
  validateMetier.mockResolvedValue({ job_id: 'J1', status: 'running' })
  verifierFiche.mockResolvedValue(A_CORRIGER)
})

async function ecranDeValidation(cases: any[]) {
  const w = monter(AddTestCase)
  await flushPromises()
  await w.find('textarea').setValue('La spécification')
  await w.findAll('select')[1].setValue('50')
  await w.find('form').trigger('submit')
  await flushPromises()
  getGenerationJob.mockResolvedValue({ status: 'awaiting_metier', cases, case_ids: [], error: '', couverture: {} })
  await vi.advanceTimersByTimeAsync(2100)
  await flushPromises()
  return w
}
const bouton = (w: any) => w.findAll('button').find((b: any) => b.text().startsWith('Valider'))!
async function deplier(w: any, titre: string) {
  await w.findAll('button').find((b: any) => b.attributes('aria-label') === `Déplier ${titre}`)!.trigger('click')
}
async function verifiee() { await vi.advanceTimersByTimeAsync(500); await flushPromises() }

describe('AddTestCase — calculs (étape 7)', () => {
  it('« Calcul détecté » ; sans choix, la validation part sans calcul', async () => {
    const w = await ecranDeValidation([DETECTE])
    expect(w.get('[data-testid="calcul-detecte"]').text()).toBe('Calcul détecté')
    await bouton(w).trigger('click')
    await flushPromises()
    const envoye = validateMetier.mock.calls[0][1][0]
    expect(envoye.fiches_retenues).toEqual([])
    expect(envoye.fiches_proposees).toEqual([FICHE])
    expect(envoye).not.toHaveProperty('choixCalcul')
  })

  it('falsifiable : la fiche de l’IA choisie ne part que prête', async () => {
    const w = await ecranDeValidation([DETECTE])
    await deplier(w, 'Total')
    await w.get('[data-testid="calcul-ia"]').setValue(true)
    await verifiee()
    expect(w.get('[data-testid="fiche-a-corriger"]').text()).toContain('date de vérification manque')
    expect(w.get('[data-testid="a-confirmer"]').text()).toContain('exemple chiffré à fournir')
    expect(bouton(w).attributes('disabled')).toBeDefined()

    verifierFiche.mockResolvedValue(PRETE)
    await w.get('[data-testid="verifie-le-1"]').setValue('2026-10-23')
    await verifiee()
    expect(bouton(w).attributes('disabled')).toBeUndefined()
    await bouton(w).trigger('click')
    await flushPromises()
    const [retenue] = validateMetier.mock.calls[0][1][0].fiches_retenues
    expect(retenue.origine).toBe('ia')
    expect(retenue.contenu.elements[1].verifie_le).toBe('2026-10-23')
    expect(DETECTE.fiches_proposees[0].elements[1]).not.toHaveProperty('verifie_le')   // la proposition n'est pas modifiée
  })

  it('« Calcul nécessaire » sur un cas non détecté : le calcul fourni part avec origine « personne »', async () => {
    verifierFiche.mockResolvedValue(PRETE)
    const w = await ecranDeValidation([SIMPLE])
    await deplier(w, 'Consulter')
    expect(w.find('[data-testid="calcul-personne"]').exists()).toBe(false)
    await w.get('[data-testid="calcul-necessaire"]').setValue(true)
    await w.get('[data-testid="calcul-personne"]').setValue(true)
    await verifiee()
    await bouton(w).trigger('click')
    await flushPromises()
    const envoye = validateMetier.mock.calls[0][1][0]
    expect(envoye.fiches_retenues[0].origine).toBe('personne')
    expect(envoye.calcul_detecte).toContain('Calcul nécessaire')
  })
})
