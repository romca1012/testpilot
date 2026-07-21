/**
 * « Ajouter un cas de test » = saisie MANUELLE, sans IA (correction du porteur 2026-07-21).
 *
 * Ce fichier garde la distinction avec « Générer » : ce formulaire NE lance PAS l'IA, il crée un
 * cas directement depuis le métier saisi. La confusion d'origine (le bouton « Ajouter » lançait
 * l'IA) ne doit pas revenir.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listModules = vi.fn()
const createManualCase = vi.fn()
const createModule = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listModules: (...a: any[]) => listModules(...a),
    createManualCase: (...a: any[]) => createManualCase(...a),
    createModule: (...a: any[]) => createModule(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot/></a>' },
}))

import AddManualCase from '../pages/AddManualCase.vue'

beforeEach(() => {
  vi.clearAllMocks()
  listModules.mockResolvedValue([{ id: 1, name: 'Demande matériel' }])
  createManualCase.mockResolvedValue({ id: 50, title: 'Cas manuel' })
})

async function remplir(w: any) {
  const inputs = w.findAll('input')
  // 0 = titre, 1 = 1re étape (le select module précède si modules existent)
  const titre = inputs.find((i: any) => i.attributes('placeholder')?.includes('vérifié'))
  await titre.setValue('Connexion valide')
  const etape = w.findAll('input').find((i: any) => i.attributes('placeholder')?.includes('Action'))
  await etape.setValue('Ouvrir la page')
  const attendu = w.find('textarea:last-of-type')
  await w.findAll('textarea').at(-1).setValue('Accès au tableau de bord.')
}

describe('AddManualCase — création manuelle sans IA', () => {
  it('crée le cas directement, sans passer par la génération', async () => {
    const w = mount(AddManualCase)
    await flushPromises()
    await remplir(w)

    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createManualCase).toHaveBeenCalledWith(1, expect.objectContaining({
      title: 'Connexion valide',
      expected_result: 'Accès au tableau de bord.',
    }))
    expect(createManualCase.mock.calls[0][1].test_steps).toContain('Ouvrir la page')
    // On atterrit sur le détail du cas créé.
    expect(push).toHaveBeenCalledWith(expect.objectContaining({ name: 'case-detail' }))
  })

  it('exige titre, étape et résultat (bouton désactivé sinon)', async () => {
    const w = mount(AddManualCase)
    await flushPromises()

    const submit = w.findAll('button').find((b: any) => b.text().includes('Créer le cas'))!
    expect(submit.attributes('disabled')).toBeDefined()
  })

  it('renvoie vers « Générer » pour le flux IA', async () => {
    const w = mount(AddManualCase)
    await flushPromises()

    expect(w.text()).toContain('Générer des cas de test')
    expect(w.text()).toContain('sans test technique')
  })
})
