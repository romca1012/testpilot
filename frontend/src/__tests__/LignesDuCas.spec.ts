/**
 * A57/A58 — les lignes propres à un cas, dans sa fiche : ses classes de valeurs, une itération chacune.
 *
 * Ce que ces tests gardent :
 * 1. une case vide se lit « — » (la valeur du projet), jamais une valeur inventée ;
 * 2. modifier puis enregistrer envoie toutes les lignes, cases vides retirées, colonne retirée oubliée ;
 * 3. sans droit de modifier, aucun bouton ; un projet sans variable ne montre rien.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const getCaseData = vi.fn()
const setCaseData = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    getCaseData: (...a: any[]) => getCaseData(...a),
    setCaseData: (...a: any[]) => setCaseData(...a),
  },
}))

import LignesDuCas from '../components/case/LignesDuCas.vue'

const DONNEES = {
  variables: [{ id: 1, nom: 'client', description: '' }, { id: 2, nom: 'age', description: '' }, { id: 3, nom: 'resultat', description: '' }],
  lignes: [{ id: 7, nom: 'Mineur', valeurs: { '2': '16', '3': 'Accès refusé' } },
           { id: 8, nom: '', valeurs: { '2': '18' } }],
}

beforeEach(() => {
  vi.clearAllMocks()
  getCaseData.mockResolvedValue(DONNEES)
  setCaseData.mockImplementation((_id: number, lignes: any[]) =>
    Promise.resolve({ variables: DONNEES.variables, lignes: lignes.map((l, i) => ({ id: 100 + i, ...l })) }))
})

async function fiche(peutModifier = true) {
  const w = mount(LignesDuCas, { props: { caseId: 5, peutModifier } })
  await flushPromises()
  return w
}

describe('LignesDuCas', () => {
  it('falsifiable : montre les lignes, une case vide se lit « — » (valeur du projet)', async () => {
    const w = await fiche()

    expect(w.findAll('[data-testid="colonne"]').map((c) => c.text())).toEqual(['{{age}}', '{{resultat}}'])
    const lignes = w.findAll('[data-testid="ligne"]').map((l) => l.findAll('td').map((c) => c.text()))
    expect(lignes).toEqual([['1', 'Mineur', '16', 'Accès refusé'], ['2', 'Ligne 2', '18', '—']])
    expect(w.get('[data-testid="nombre-iterations"]').text()).toBe('2 itérations')
  })

  it('falsifiable : enregistrer envoie toutes les lignes, sans case vide ni colonne retirée', async () => {
    const w = await fiche()
    await w.get('[data-testid="modifier-lignes"]').trigger('click')
    await w.get('[data-testid="ajouter-ligne"]').trigger('click')
    await w.get('[data-testid="case-2-2"]').setValue(' 17 ')
    await w.get('button[aria-label="Retirer la colonne resultat"]').trigger('click')
    await w.get('[data-testid="enregistrer-lignes"]').trigger('click')
    await flushPromises()

    // L'identifiant d'une ligne existante repart : ses valeurs d'une variable à la corbeille sont gardées par le serveur.
    expect(setCaseData).toHaveBeenCalledWith(5, [
      { id: 7, nom: 'Mineur', valeurs: { '2': '16' } }, { id: 8, nom: '', valeurs: { '2': '18' } }, { nom: '', valeurs: { '2': '17' } }])
    expect(w.findAll('[data-testid="ligne"]')).toHaveLength(3)
  })

  it('ajouter une colonne la place dans l’ordre du projet', async () => {
    const w = await fiche()
    await w.get('[data-testid="modifier-lignes"]').trigger('click')
    await w.get('[data-testid="ajouter-colonne"]').setValue('1')

    expect(w.findAll('[data-testid="colonne"]').map((c) => c.text().replace('×', '').trim())).toEqual(['{{client}}', '{{age}}', '{{resultat}}'])
  })

  it('sans droit de modifier : aucun bouton', async () => {
    const w = await fiche(false)
    expect(w.find('[data-testid="modifier-lignes"]').exists()).toBe(false)
  })

  it('un projet sans variable ne montre rien', async () => {
    getCaseData.mockResolvedValue({ variables: [], lignes: [] })
    const w = await fiche()
    expect(w.find('[data-testid="lignes-du-cas"]').exists()).toBe(false)
  })

  it('falsifiable : le test n’emploie pas une variable des lignes — l’écran le dit', async () => {
    getCaseData.mockResolvedValue({ ...DONNEES, ecarts: ["les lignes du cas donnent « {{age}} », le test ne l'emploie pas"] })
    const w = await fiche()
    expect(w.get('[data-testid="ecarts-lignes"]').text()).toContain('{{age}}')
    expect(w.find('[data-testid="nombre-iterations"]').exists()).toBe(false)   // rien ne sera joué : aucun décompte
    expect(w.get('[data-testid="non-joue"]').text()).toBe('Non joué')
  })

  it('étape 6 (IT-3d) : le texte du cas a changé depuis l’enregistrement des lignes — l’écran le dit', async () => {
    getCaseData.mockResolvedValue({ ...DONNEES, lignes_a_relire: 'Le texte du cas a changé depuis l’enregistrement de ses lignes' })
    const w = await fiche()
    expect(w.get('[data-testid="lignes-a-relire"]').text()).toContain('Le texte du cas a changé')
  })

  it('sans changement du texte du cas, aucun signal', async () => {
    getCaseData.mockResolvedValue({ ...DONNEES })
    const w = await fiche()
    expect(w.find('[data-testid="lignes-a-relire"]').exists()).toBe(false)
  })

  it('A90-A92 : la colonne « Compte » dit avec quel compte chaque ligne sera jouée, et envoie le choix', async () => {
    getCaseData.mockResolvedValue({
      ...DONNEES,
      comptes: [{ id: null, libelle: 'principal' }, { id: 4, libelle: 'Lecteur' }],
      lignes: [{ id: 7, nom: 'Mineur', valeurs: { '2': '16' }, compte_choisi: false, compte_id: null, compte_joue: 'Lecteur (compte du cas)' },
               { id: 8, nom: 'Majeur', valeurs: { '2': '18' }, compte_choisi: true, compte_id: 9, compte_joue: 'compte supprimé' }],
    })
    const w = await fiche()
    expect(w.get('[data-testid="colonne-compte"]').text()).toBe('Compte')
    expect(w.get('[data-testid="compte-0"]').text()).toBe('Lecteur (compte du cas)')
    expect(w.get('[data-testid="compte-1"] span').classes()).toContain('text-warning')

    await w.get('[data-testid="modifier-lignes"]').trigger('click')
    await w.get('[data-testid="compte-0"] select').setValue('4')
    await w.get('[data-testid="compte-1"] select').setValue('principal')
    await w.get('[data-testid="enregistrer-lignes"]').trigger('click')
    await flushPromises()
    expect(setCaseData.mock.calls[0][1].map((l: any) => [l.compte_choisi, l.compte_id])).toEqual([[true, 4], [true, null]])
  })

  it('sans autre compte que le principal : pas de colonne « Compte », envoi inchangé', async () => {
    const w = await fiche()
    expect(w.find('[data-testid="colonne-compte"]').exists()).toBe(false)
  })
})
