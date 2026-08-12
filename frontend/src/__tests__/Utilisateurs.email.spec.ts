/**
 * Email d'un compte (2026-08-12) — nécessaire pour le prévenir par notification (Réglages >
 * Notifications par email). Un Admin le saisit à la création ou l'édite ensuite, comme les
 * autres attributs d'un compte (rôle, mot de passe).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listUsers = vi.fn()
const createUser = vi.fn()
const patchUser = vi.fn()
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<any>('../lib/api')
  return {
    api: {
      listUsers: (...a: any[]) => listUsers(...a),
      createUser: (...a: any[]) => createUser(...a),
      patchUser: (...a: any[]) => patchUser(...a),
    },
    LIBELLE_ROLE: actual.LIBELLE_ROLE,
    ROLES: actual.ROLES,
  }
})

const session = { value: { authenticated: true, role: 'admin', name: 'Root' } as any }
vi.mock('../lib/useSession', () => ({ useSession: () => ({ session }) }))

import Utilisateurs from '../pages/Utilisateurs.vue'

const COMPTES = [
  { id: 1, username: 'awa', role: 'testeur', email: 'awa@exemple.fr', is_active: true, created_at: '' },
]

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

async function page() {
  listUsers.mockResolvedValue(COMPTES)
  const w = mount(Utilisateurs, { global: { stubs } })
  await flushPromises()
  return w
}

beforeEach(() => { vi.clearAllMocks() })

describe('Utilisateurs — email', () => {
  it('la création envoie l\'email saisi', async () => {
    createUser.mockResolvedValue({ id: 2, username: 'leo', role: 'testeur', email: 'leo@exemple.fr',
                                   is_active: true, created_at: '' })
    const w = await page()
    await w.find('input[placeholder="Identifiant"]').setValue('leo')
    await w.find('input[placeholder="Mot de passe initial"]').setValue('mdp12345')
    await w.find('input[placeholder="Email (facultatif)"]').setValue('leo@exemple.fr')
    await w.find('button:not([type])').trigger('click')
    await flushPromises()

    expect(createUser).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'leo@exemple.fr' }))
  })

  it('le compte existant affiche son email et le modifie', async () => {
    patchUser.mockResolvedValue({ ...COMPTES[0], email: 'nouveau@exemple.fr' })
    const w = await page()
    // Le 1er email est celui du formulaire de création (vide) ; le 2e, celui de la ligne du compte.
    const champEmail = w.findAll('input[type="email"]')[1]
    expect((champEmail.element as HTMLInputElement).value).toBe('awa@exemple.fr')

    await champEmail.setValue('nouveau@exemple.fr')
    await champEmail.trigger('change')
    await flushPromises()

    expect(patchUser).toHaveBeenCalledWith(1, { email: 'nouveau@exemple.fr' })
  })

  it('ne réenregistre pas si l\'email n\'a pas changé', async () => {
    const w = await page()
    const champEmail = w.findAll('input[type="email"]')[1]
    await champEmail.trigger('change')   // aucune modification de la valeur
    await flushPromises()

    expect(patchUser).not.toHaveBeenCalled()
  })
})
