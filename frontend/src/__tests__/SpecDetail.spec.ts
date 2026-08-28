/**
 * L'écran de la SPÉCIFICATION — lot 4 du déploiement (2026-07-24).
 *
 * Le CRUD existait côté serveur depuis le 2026-07-20 sans qu'aucun écran ne l'appelle : un
 * utilisateur ne pouvait ni créer ni relire une spécification. Les seules qui existaient étaient
 * les « enveloppes » créées automatiquement par la génération, une par cas — le modèle du brief
 * (une spec → N cas) était donc inatteignable par l'interface.
 *
 * Ce que ces tests figent :
 *   • éditer le document ne génère RIEN et ne dépense RIEN (la génération reste un geste séparé) ;
 *   • un modèle vierge n'est pas une spécification : on refuse de lancer une génération dessus ;
 *   • le refus de suppression (409, la spec porte des cas) est affiché TEL QUEL — il dit combien.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
// Monté AVEC la couche de données (lot A) : sans elle, le composant plante au `setup()`.
import { monter } from './_montage'

const getGroup = vi.fn()
const updateGroup = vi.fn()
const deleteGroup = vi.fn()
const listCases = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  roleSuffisant: () => true,
  api: {
    getGroup: (...a: any[]) => getGroup(...a),
    updateGroup: (...a: any[]) => updateGroup(...a),
    deleteGroup: (...a: any[]) => deleteGroup(...a),
    listCases: (...a: any[]) => listCases(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '7' }, query: {} }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot/></a>' },
}))

import SpecDetail from '../pages/SpecDetail.vue'
import { MODELE_SPECIFICATION } from '../lib/modeleSpecification'

const SPEC = {
  id: 7, module_id: 3, title: 'Déclaration de sinistre', description: '',
  spec_content: 'Un employé déclare un sinistre.', spec_hash: 'abc123def456789',
  case_count: 2, created_at: '', updated_at: '',
}

beforeEach(() => {
  vi.clearAllMocks()
  getGroup.mockResolvedValue({ ...SPEC })
  // ⚠️ Le filtre par spécification est fait par le SERVEUR depuis la pagination : le simulacre
  // rend donc ce que le serveur rendrait — les cas de CETTE spécification, et eux seuls.
  listCases.mockResolvedValue({
    items: [
      { id: 11, title: 'Sinistre déclaré', group_id: 7, statut: 'passed' },
      { id: 12, title: 'Sinistre sans pièce jointe', group_id: 7, statut: 'untested' },
    ],
    next_cursor: null, total: 2,
  })
})

async function monterFiche() {
  const w = monter(SpecDetail)
  await flushPromises()
  await flushPromises()   // la requête du cache résout au tick suivant
  return w
}

describe('la fiche de la spécification', () => {
  it('affiche le document et les cas QUI EN SONT NÉS, pas les autres', async () => {
    const w = await monterFiche()
    expect(w.find('textarea').element.value).toBe('Un employé déclare un sinistre.')
    expect(w.text()).toContain('Sinistre déclaré')
    expect(w.text()).toContain('Sinistre sans pièce jointe')
    // Le serveur a filtré : la fiche affiche ce qu'il lui a rendu, sans re-trier localement.
    expect(listCases).toHaveBeenCalledWith('1', expect.objectContaining({ group_id: 7 }))
  })

  it('n\'enregistre RIEN tant que rien n\'a changé', async () => {
    const w = await monterFiche()
    const bouton = w.findAll('button').find((b) => b.text() === 'Enregistrer')!
    expect(bouton.attributes('disabled')).toBeDefined()
  })

  it('enregistre le document SANS rien générer ni dépenser', async () => {
    updateGroup.mockResolvedValue({ ...SPEC, spec_content: 'Nouveau texte' })
    const w = await monterFiche()
    await w.find('textarea').setValue('Nouveau texte')
    await w.findAll('button').find((b) => b.text() === 'Enregistrer')!.trigger('click')
    await flushPromises()

    expect(updateGroup).toHaveBeenCalledWith(7, expect.objectContaining({ spec_content: 'Nouveau texte' }))
    // ⚠️ La garde : aucune navigation vers la génération, aucun appel qui dépenserait.
    expect(push).not.toHaveBeenCalled()
    expect(w.text()).toContain('Spécification enregistrée.')
  })

  it('propose le MODÈLE quand le document est vide, et pas quand il est rédigé', async () => {
    getGroup.mockResolvedValue({ ...SPEC, spec_content: '' })
    const w = await monterFiche()
    const lien = w.findAll('button').find((b) => b.text().includes('Partir du modèle'))!
    await lien.trigger('click')
    expect(w.find('textarea').element.value).toBe(MODELE_SPECIFICATION)
  })

  it('REFUSE de lancer une génération sur un modèle vierge', async () => {
    // Un modèle non rempli contient des consignes, pas une spécification : générer dessus
    // produirait un test écrit d'après « Décrivez en une ou deux phrases… ».
    getGroup.mockResolvedValue({ ...SPEC, spec_content: MODELE_SPECIFICATION })
    const w = await monterFiche()
    const bouton = w.findAll('button').find((b) => b.text().includes('Générer un cas'))!
    expect(bouton.attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('Rédigez d\'abord le document')
  })

  it('emmène vers la génération AVEC la spécification, en un geste explicite', async () => {
    const w = await monterFiche()
    await w.findAll('button').find((b) => b.text().includes('Générer un cas'))!.trigger('click')
    expect(push).toHaveBeenCalledWith(expect.objectContaining({
      name: 'case-new', query: { spec: '7' },
    }))
  })

  it('affiche le refus de suppression TEL QUEL — il dit combien de cas bloquent', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    deleteGroup.mockRejectedValue(
      Object.assign(new Error('cette spécification porte encore 2 cas'), { status: 409 }))
    const w = await monterFiche()
    await w.findAll('button').find((b) => b.text().includes('Supprimer'))!.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('porte encore 2 cas')
    expect(push).not.toHaveBeenCalled()   // on reste sur la fiche : rien n'a été supprimé
  })
})
