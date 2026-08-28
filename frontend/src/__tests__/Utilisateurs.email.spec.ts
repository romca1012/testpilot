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
const listProjects = vi.fn()
const getUserProjects = vi.fn()
const putUserProjects = vi.fn()
const listUserGroups = vi.fn()
const push = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query: {} }),
}))
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<any>('../lib/api')
  return {
    api: {
      listUsers: (...a: any[]) => listUsers(...a),
      createUser: (...a: any[]) => createUser(...a),
      patchUser: (...a: any[]) => patchUser(...a),
      listProjects: (...a: any[]) => listProjects(...a),
      listAdminProjects: (...a: any[]) => listProjects(...a),
      getUserProjects: (...a: any[]) => getUserProjects(...a),
      putUserProjects: (...a: any[]) => putUserProjects(...a),
      listUserGroups: (...a: any[]) => listUserGroups(...a),
    },
    LIBELLE_ROLE: actual.LIBELLE_ROLE,
    ROLES: actual.ROLES,
    ACCES_PROJET_REFUSE: actual.ACCES_PROJET_REFUSE,
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
  listProjects.mockResolvedValue([])
  listUserGroups.mockResolvedValue([])
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
    await w.findAll('button').find(b => b.text().includes('Ajouter un utilisateur'))!.trigger('click')
    await w.find('input[name="username"]').setValue('leo')
    await w.find('input[name="new-password"]').setValue('mdp12345')
    await w.find('input[name="email"]').setValue('leo@exemple.fr')
    await w.find('#create-user').trigger('submit')
    await flushPromises()

    expect(createUser).toHaveBeenCalledWith(
      expect.objectContaining({ email: 'leo@exemple.fr' }))
  })

  it('ouvre la page dédiée du compte existant', async () => {
    const w = await page()
    await w.findAll('button').find(b => b.text().includes('Modifier'))!.trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith({ name: 'utilisateur-detail', params: { id: 1 } })
  })

  it('la liste ne modifie plus silencieusement un compte', async () => {
    const w = await page()
    expect(w.find('input[aria-label="Email de awa"]').exists()).toBe(false)
    expect(patchUser).not.toHaveBeenCalled()
  })
})
