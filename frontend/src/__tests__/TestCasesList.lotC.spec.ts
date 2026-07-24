/**
 * La liste des cas comme OUTIL DE TRAVAIL — lot C (2026-07-24).
 *
 * L'audit avait relevé que composer une campagne de 20 cas demandait 20 gestes, qu'aucune
 * recherche n'existait, et qu'aucune préférence d'affichage n'était conservée. C'est pourtant
 * l'écran où le testeur passe sa journée.
 *
 * Ce que ces tests figent :
 *   • la recherche porte sur ce qu'on LIT (titre, identifiant, module) ;
 *   • la barre d'actions n'apparaît QU'AVEC une sélection ;
 *   • cocher n'ouvre PAS le cas (deux intentions distinctes) ;
 *   • une action de masse part en UNE requête et rend un compte rendu ;
 *   • les préférences d'affichage survivent, et se réinitialisent.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listCases = vi.fn()
const prioriteEnLot = vi.fn()
const supprimerEnLot = vi.fn()
const createRun = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listCases: (...a: any[]) => listCases(...a),
    prioriteEnLot: (...a: any[]) => prioriteEnLot(...a),
    supprimerEnLot: (...a: any[]) => supprimerEnLot(...a),
    createRun: (...a: any[]) => createRun(...a),
    renameModule: vi.fn(),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot/></a>' },
}))

import TestCasesList from '../pages/TestCasesList.vue'

const CAS = [
  { id: 11, title: 'Déclaration de sinistre', module: 'Demandes', module_id: 1, group_id: null,
    group_title: null, angle: 'nominal', priority: 'medium',
    last_execution_status: 'success', last_functional_status: 'conforme' },
  { id: 12, title: 'Retour matériel', module: 'Demandes', module_id: 1, group_id: null,
    group_title: null, angle: 'erreur', priority: 'high',
    last_execution_status: null, last_functional_status: null },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  listModules.mockResolvedValue([{ id: 1, name: 'Demandes', case_count: 2 }])
  listCases.mockResolvedValue(CAS)
  prioriteEnLot.mockResolvedValue({ traites: 2, ignores: 0 })
  supprimerEnLot.mockResolvedValue({ traites: 2, ignores: 0 })
  createRun.mockResolvedValue({ id: 7, name: 'Campagne', case_count: 2 })
})

async function monterListe() {
  const w = monter(TestCasesList)
  await flushPromises()
  await flushPromises()
  return w
}

function cases_a_cocher(w: any) {
  // La première case de chaque section est le « tout sélectionner » de son en-tête.
  return w.findAll('input[type="checkbox"]')
}

describe('la recherche', () => {
  it('filtre sur le TITRE', async () => {
    const w = await monterListe()
    await w.find('input[type="search"]').setValue('sinistre')

    expect(w.text()).toContain('Déclaration de sinistre')
    expect(w.text()).not.toContain('Retour matériel')
  })

  it('filtre aussi sur l\'IDENTIFIANT affiché — « C12 » doit marcher', async () => {
    // C'est ce qu'on lit à l'écran et ce qu'on se dit entre collègues (« regarde C12 »).
    const w = await monterListe()
    await w.find('input[type="search"]').setValue('C12')

    expect(w.text()).toContain('Retour matériel')
    expect(w.text()).not.toContain('Déclaration de sinistre')
  })

  it('ne déclenche AUCUN appel serveur', async () => {
    // Les cas sont déjà en cache : un aller-retour n'apporterait que de la latence.
    const w = await monterListe()
    listCases.mockClear()
    await w.find('input[type="search"]').setValue('sinistre')

    expect(listCases).not.toHaveBeenCalled()
  })
})

describe('la sélection', () => {
  it('n\'affiche la barre d\'actions QUE lorsqu\'il y a une sélection', async () => {
    const w = await monterListe()
    expect(w.text()).not.toContain('Créer une campagne')

    await cases_a_cocher(w)[1].setValue(true)

    expect(w.text()).toContain('1 cas sélectionné')
    expect(w.text()).toContain('Créer une campagne')
  })

  it('cocher n\'OUVRE PAS le cas', async () => {
    // Sans `@click.stop`, le clic remonterait à la ligne : on se retrouverait sur la fiche du
    // cas au lieu de l'avoir sélectionné. Deux intentions, deux gestes.
    const w = await monterListe()
    await cases_a_cocher(w)[1].trigger('click')

    expect(push).not.toHaveBeenCalled()
  })

  it('« tout sélectionner » ne porte que sur SA section', async () => {
    const w = await monterListe()
    await cases_a_cocher(w)[0].setValue(true)

    expect(w.text()).toContain('2 cas sélectionnés')
  })

  it('vide la sélection quand la recherche change', async () => {
    // Garder des cases cochées devenues invisibles ferait agir sur ce qu'on ne voit plus.
    const w = await monterListe()
    await cases_a_cocher(w)[1].setValue(true)
    expect(w.text()).toContain('1 cas sélectionné')

    await w.find('input[type="search"]').setValue('rien')

    expect(w.text()).not.toContain('cas sélectionné')
  })
})

describe('les actions en lot', () => {
  it('change la priorité de la sélection en UNE requête', async () => {
    const w = await monterListe()
    await cases_a_cocher(w)[0].setValue(true)
    await w.findAll('button').find((b: any) => b.text() === 'Haute')!.trigger('click')
    await flushPromises()

    expect(prioriteEnLot).toHaveBeenCalledTimes(1)
    expect(prioriteEnLot).toHaveBeenCalledWith([11, 12], 'high')
  })

  it('DIT combien de cas ont été ignorés', async () => {
    // Un cas a pu disparaître entre l'affichage et le clic : annoncer « fait » serait faux.
    prioriteEnLot.mockResolvedValue({ traites: 1, ignores: 1 })
    const w = await monterListe()
    await cases_a_cocher(w)[0].setValue(true)
    await w.findAll('button').find((b: any) => b.text() === 'Basse')!.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('1 ignoré')
  })

  it('compose une campagne à SÉLECTION FIGÉE depuis les cas cochés', async () => {
    // Figée, et non « tous les cas du projet » : une campagne ne doit pas changer sous les
    // pieds de celui qui l'a composée.
    vi.spyOn(window, 'prompt').mockReturnValue('Campagne du jour')
    const w = await monterListe()
    await cases_a_cocher(w)[0].setValue(true)
    await w.findAll('button').find((b: any) => b.text() === 'Créer une campagne')!.trigger('click')
    await flushPromises()

    expect(createRun).toHaveBeenCalledWith('1', expect.objectContaining({
      selection_mode: 'frozen', case_ids: [11, 12],
    }))
    expect(push).toHaveBeenCalledWith(expect.objectContaining({ name: 'run-detail' }))
  })

  it('DEMANDE confirmation avant une suppression de masse', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const w = await monterListe()
    await cases_a_cocher(w)[0].setValue(true)
    await w.findAll('button').find((b: any) => b.text() === 'Supprimer')!.trigger('click')

    expect(confirm).toHaveBeenCalled()
    expect(supprimerEnLot).not.toHaveBeenCalled()   // refus respecté
  })
})

describe('les préférences d\'affichage', () => {
  it('conserve la densité d\'une visite à l\'autre', async () => {
    const w = await monterListe()
    await w.findAll('select').find((s: any) => s.element.value === 'normale')!.setValue('compacte')
    await flushPromises()

    expect(localStorage.getItem('tp.liste.1')).toContain('compacte')
  })

  it('propose « réinitialiser » SEULEMENT quand quelque chose a été modifié', async () => {
    const w = await monterListe()
    expect(w.text()).not.toContain("Réinitialiser l'affichage")

    await w.findAll('select').find((s: any) => s.element.value === 'normale')!.setValue('aeree')

    expect(w.text()).toContain("Réinitialiser l'affichage")
  })

  it('survit à une préférence enregistrée AVANT l\'ajout d\'un réglage', async () => {
    // Une préférence écrite par une version antérieure n'a pas toutes les clés. Sans fusion avec
    // les défauts, le réglage manquant vaudrait `undefined` et l'écran se casserait sur une
    // préférence pourtant valide au moment où elle a été écrite.
    localStorage.setItem('tp.liste.1', JSON.stringify({ densite: 'compacte' }))
    const w = await monterListe()

    expect(w.text()).toContain('Déclaration de sinistre')   // la liste s'affiche
  })
})
