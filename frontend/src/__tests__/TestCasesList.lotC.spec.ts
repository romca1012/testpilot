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
const push = vi.fn()

vi.mock('../lib/api', () => ({
  roleSuffisant: () => true,
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listCases: (...a: any[]) => listCases(...a),
    prioriteEnLot: (...a: any[]) => prioriteEnLot(...a),
    supprimerEnLot: (...a: any[]) => supprimerEnLot(...a),
    renameModule: vi.fn(),
  },
}))
vi.mock('../lib/useSession', () => ({
  useSession: () => ({ session: { value: { role: 'admin' } } }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot/></a>' },
}))

import TestCasesList from '../pages/TestCasesList.vue'

const CAS = [
  { id: 11, title: 'Déclaration de sinistre', module: 'Demandes', module_id: 1, group_id: null,
    group_title: null, type: 'fonctionnel', etat: 'new', priority: 'medium',
    last_execution_status: 'success', last_functional_status: 'conforme', statut: 'passed' },
  { id: 12, title: 'Retour matériel', module: 'Demandes', module_id: 1, group_id: null,
    group_title: null, type: 'non_fonctionnel', etat: 'design', priority: 'high',
    last_execution_status: null, last_functional_status: null, statut: 'untested' },
]

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  listModules.mockResolvedValue([{ id: 1, name: 'Demandes', case_count: 2 }])
  // Paginée depuis le 2026-07-24 : le simulacre rend une page, comme le serveur.
  listCases.mockResolvedValue({ items: CAS, next_cursor: null, total: CAS.length })
  prioriteEnLot.mockResolvedValue({ traites: 2, ignores: 0 })
  supprimerEnLot.mockResolvedValue({ traites: 2, ignores: 0 })
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

describe('la recherche et le filtre', () => {
  // ⚠️ Ces tests vérifiaient un filtrage LOCAL jusqu'à la pagination (2026-07-24). Filtrer côté
  // navigateur ne porte que sur la page chargée : chercher un cas de la page 3 répondrait
  // « aucun résultat », et l'utilisateur conclurait qu'il n'existe pas. Un filtre qui ment sur
  // l'absence est pire que pas de filtre — recherche et statut partent donc au serveur.
  it('envoie la recherche AU SERVEUR', async () => {
    const w = await monterListe()
    listCases.mockClear()
    await w.find('input[type="search"]').setValue('sinistre')
    await flushPromises()

    expect(listCases).toHaveBeenCalledWith('1', expect.objectContaining({ q: 'sinistre' }))
  })

  it('envoie AUSSI le filtre de statut au serveur', async () => {
    const w = await monterListe()
    listCases.mockClear()
    await w.findAll('select').find((s: any) => s.element.value === '')!.setValue('failed')
    await flushPromises()

    expect(listCases).toHaveBeenCalledWith('1', expect.objectContaining({ statut: 'failed' }))
  })

  it('DIT combien de cas sont affichés sur le total', async () => {
    // Sans ce compte, une liste tronquée a l'air complète — et l'utilisateur conclut qu'un cas
    // n'existe pas alors qu'il est simplement au-delà de ce qui a été chargé.
    listCases.mockResolvedValue({ items: CAS, next_cursor: 'x', total: 2000 })
    const w = await monterListe()

    expect(w.text()).toContain('sur 2000')
    expect(w.text()).toContain('Charger')
  })
})

describe('la sélection', () => {
  it('n\'affiche la barre d\'actions QUE lorsqu\'il y a une sélection', async () => {
    const w = await monterListe()
    expect(w.text()).not.toContain('cas sélectionné')

    await cases_a_cocher(w)[1].setValue(true)

    expect(w.text()).toContain('1 cas sélectionné')
    expect(w.text()).toContain('Priorité :')
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

    listCases.mockResolvedValue({ items: [], next_cursor: null, total: 0 })
    await w.find('input[type="search"]').setValue('rien')
    await flushPromises()

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
