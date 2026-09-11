/**
 * « Ajouter un cas de test » = saisie MANUELLE, sans IA (correction du porteur 2026-07-21).
 *
 * Ce fichier garde la distinction avec « Générer » : ce formulaire NE lance PAS l'IA, il crée un
 * cas directement depuis le métier saisi. La confusion d'origine (le bouton « Ajouter » lançait
 * l'IA) ne doit pas revenir.
 *
 * ⚠️ **La Section est OBLIGATOIRE depuis le 2026-09-11** — même patron exact que « Générer des
 * cas » (AddTestCase.vue, étape 3bis, 2026-08-07), pour la même raison : avant, ce formulaire
 * auto-enveloppait chaque cas dans sa propre Section privée, jamais partagée, un écart de fait
 * avec le reste de l'application. Deux cas créés depuis la MÊME Section doivent désormais s'y
 * retrouver ENSEMBLE, comme dans TestRail — sans glisser-déposer après coup.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const listModules = vi.fn()
const listGroups = vi.fn()
const createManualCase = vi.fn()
const createModule = vi.fn()
const createGroup = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    listGroups: (...a: any[]) => listGroups(...a),
    createManualCase: (...a: any[]) => createManualCase(...a),
    createModule: (...a: any[]) => createModule(...a),
    createGroup: (...a: any[]) => createGroup(...a),
  },
}))
let currentQuery: Record<string, string> = {}
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, get query() { return currentQuery } }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot/></a>' },
}))

import AddManualCase from '../pages/AddManualCase.vue'

beforeEach(() => {
  vi.clearAllMocks()
  currentQuery = {}
  listModules.mockResolvedValue([{ id: 1, name: 'Demande matériel' }, { id: 2, name: 'Facturation' }])
  listGroups.mockResolvedValue([{ id: 9, module_id: 1, title: 'Authentification', case_count: 2, parent_group_id: null }])
  createManualCase.mockResolvedValue({ id: 50, title: 'Cas manuel' })
  createGroup.mockResolvedValue({ id: 99, module_id: 1, title: 'Nouvelle section' })
})

async function remplir(w: any) {
  const inputs = w.findAll('input')
  const titre = inputs.find((i: any) => i.attributes('placeholder')?.includes('vérifié'))
  await titre.setValue('Connexion valide')
  const etape = w.findAll('input').find((i: any) => i.attributes('placeholder')?.includes('Action'))
  await etape.setValue('Ouvrir la page')
  await w.findAll('textarea').at(-1).setValue('Accès au tableau de bord.')
}

describe('AddManualCase — création manuelle sans IA', () => {
  it('crée le cas dans la section existante choisie, sans passer par la génération', async () => {
    const w = monter(AddManualCase)
    await flushPromises()
    // Une seule section existe pour le module 1 : le select n'a qu'un choix réel, mais reste
    // à sélectionner explicitement (comportement natif du <select>, valeur déjà en tête de liste).
    await w.findAll('select')[1].setValue('9')
    await remplir(w)

    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createManualCase).toHaveBeenCalledWith(1, expect.objectContaining({
      title: 'Connexion valide',
      expected_result: 'Accès au tableau de bord.',
      group_id: 9,
    }))
    expect(createManualCase.mock.calls[0][1].test_steps).toContain('Ouvrir la page')
    expect(push).toHaveBeenCalledWith(expect.objectContaining({ name: 'case-detail' }))
  })

  it('exige titre, étape, résultat ET section (bouton désactivé sinon)', async () => {
    const w = monter(AddManualCase)
    await flushPromises()

    const submit = w.findAll('button').find((b: any) => b.text().includes('Créer le cas'))!
    expect(submit.attributes('disabled')).toBeDefined()

    await remplir(w)
    await flushPromises()
    // Le métier est complet mais AUCUNE section n'est encore choisie : toujours désactivé.
    expect(submit.attributes('disabled')).toBeDefined()

    await w.findAll('select')[1].setValue('9')
    await flushPromises()
    expect(submit.attributes('disabled')).toBeUndefined()
  })

  it('renvoie vers « Générer » pour le flux IA', async () => {
    const w = monter(AddManualCase)
    await flushPromises()

    expect(w.text()).toContain('Générer des cas de test')
    expect(w.text()).toContain('sans test technique')
  })

  it('module sans section : propose « + Créer une section » et l\'utilise à la création', async () => {
    listGroups.mockResolvedValue([]) // aucune section nulle part
    const w = monter(AddManualCase)
    await flushPromises()

    expect(w.text()).toContain("n'a pas encore de section")
    const nomSection = w.findAll('input').find((i: any) => i.attributes('placeholder')?.includes('Connexion'))
    await nomSection!.setValue('Authentification')
    await remplir(w)
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createGroup).toHaveBeenCalledWith(1, { title: 'Authentification' })
    expect(createManualCase).toHaveBeenCalledWith(1, expect.objectContaining({ group_id: 99 }))
  })
})

describe('AddManualCase — Section pré-choisie (2026-09-11, parité TestRail)', () => {
  it('venu d\'une Section précise : elle est déjà sélectionnée, et envoyée avec le cas', async () => {
    currentQuery = { module: '1', section: '9' }
    const w = monter(AddManualCase)
    await flushPromises()

    const select = w.findAll('select')[1]
    expect((select.element as HTMLSelectElement).value).toBe('9')

    await remplir(w)
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createManualCase).toHaveBeenCalledWith(1, expect.objectContaining({ group_id: 9 }))
    expect(createGroup).not.toHaveBeenCalled()   // section EXISTANTE réutilisée, pas recréée
  })

  it('changer de module réinitialise la Section pré-choisie (elle n\'existe que sous UN module)', async () => {
    currentQuery = { module: '1', section: '9' }
    const w = monter(AddManualCase)
    await flushPromises()
    expect((w.findAll('select')[1].element as HTMLSelectElement).value).toBe('9')

    await w.findAll('select')[0].setValue('2') // « Facturation » — un AUTRE module
    await flushPromises()

    // Plus aucune section n'est sélectionnée : le module 2 n'a pas de section « 9 ».
    expect(w.text()).toContain("n'a pas encore de section")
  })
})
