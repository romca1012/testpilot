/**
 * Mot de passe initial FACULTATIF (audit 2026-09-09) : un Admin qui invente et transmet
 * lui-même le mot de passe d'un compte qu'il ne détient pas est la faille corrigée — laisser le
 * champ vide fait générer un mot de passe temporaire côté serveur, envoyé par email si possible.
 * Ce fichier couvre le CÔTÉ ÉCRAN : le serveur est bouchonné, voir `test_comptes_utilisateurs.py`
 * pour la génération/l'envoi réels.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listUsers = vi.fn()
const createUser = vi.fn()
const listProjects = vi.fn()
const listUserGroups = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ query: {} }),
}))
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<any>('../lib/api')
  return {
    api: {
      listUsers: (...a: any[]) => listUsers(...a),
      createUser: (...a: any[]) => createUser(...a),
      patchUser: vi.fn(),
      listProjects: (...a: any[]) => listProjects(...a),
      listAdminProjects: (...a: any[]) => listProjects(...a),
      getUserProjects: vi.fn(),
      putUserProjects: vi.fn(),
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

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

async function page() {
  listUsers.mockResolvedValue([])
  listProjects.mockResolvedValue([])
  listUserGroups.mockResolvedValue([])
  const w = mount(Utilisateurs, { global: { stubs } })
  await flushPromises()
  return w
}

async function ouvrirCreationEtRemplirIdentifiant(w: any, username: string) {
  await w.findAll('button').find((b: any) => b.text().includes('Ajouter un utilisateur'))!.trigger('click')
  await w.find('input[name="username"]').setValue(username)
}

beforeEach(() => { vi.clearAllMocks() })

describe('Utilisateurs — mot de passe initial facultatif', () => {
  it('le bouton de création n\'exige plus un mot de passe saisi', async () => {
    const w = await page()
    await ouvrirCreationEtRemplirIdentifiant(w, 'leo')

    const bouton = w.findAll('button').find((b: any) => b.text() === 'Créer l’utilisateur')!
    expect(bouton.attributes('disabled')).toBeUndefined()
  })

  it('un mot de passe saisi TROP COURT bloque toujours la création', async () => {
    const w = await page()
    await ouvrirCreationEtRemplirIdentifiant(w, 'leo')
    await w.find('input[name="new-password"]').setValue('court')

    const bouton = w.findAll('button').find((b: any) => b.text() === 'Créer l’utilisateur')!
    expect(bouton.attributes('disabled')).toBeDefined()
  })

  it('n\'envoie PAS de mot de passe vide au serveur (undefined, pas "")', async () => {
    createUser.mockResolvedValue({
      id: 2, username: 'leo', role: 'testeur', email: '', is_active: true, created_at: '',
      email_envoye: false, mot_de_passe_initial: 'temp-genere-xyz',
    })
    const w = await page()
    await ouvrirCreationEtRemplirIdentifiant(w, 'leo')
    await w.find('#create-user').trigger('submit')
    await flushPromises()

    expect(createUser).toHaveBeenCalledWith(expect.objectContaining({ password: undefined }))
  })

  it('affiche le mot de passe temporaire QUAND aucun email n\'a pu partir', async () => {
    createUser.mockResolvedValue({
      id: 2, username: 'leo', role: 'testeur', email: '', is_active: true, created_at: '',
      email_envoye: false, mot_de_passe_initial: 'temp-genere-xyz',
    })
    const w = await page()
    await ouvrirCreationEtRemplirIdentifiant(w, 'leo')
    await w.find('#create-user').trigger('submit')
    await flushPromises()

    expect(w.text()).toContain('temp-genere-xyz')
  })

  it('n\'affiche RIEN quand l\'email a bien été envoyé', async () => {
    createUser.mockResolvedValue({
      id: 3, username: 'awa', role: 'testeur', email: 'awa@exemple.fr', is_active: true,
      created_at: '', email_envoye: true, mot_de_passe_initial: null,
    })
    const w = await page()
    await ouvrirCreationEtRemplirIdentifiant(w, 'awa')
    await w.find('input[name="email"]').setValue('awa@exemple.fr')
    await w.find('#create-user').trigger('submit')
    await flushPromises()

    expect(w.text()).not.toContain('Compte créé')
  })
})
