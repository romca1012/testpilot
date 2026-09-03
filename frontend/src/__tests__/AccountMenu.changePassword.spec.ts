/**
 * « Changer mon mot de passe » depuis le menu de compte (2026-09-03) — accessible à TOUT rôle
 * connecté, y compris Lecture seule (voir ChangePasswordModal.vue).
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<any>('../lib/api')
  return { ...actual, api: { ...actual.api, logout: vi.fn() } }
})

// Un vrai `ref` (pas un objet `{ value: ... }` figé) : AccountMenu.vue lit `session?.authenticated`
// DIRECTEMENT dans son template — seul un ref est auto-déballé par le contexte de rendu de Vue.
const session = ref<any>({ authenticated: true, role: 'lecture_seule', name: 'Lea', lock_enabled: true })
vi.mock('../lib/useSession', () => ({ useSession: () => ({ session }) }))

import AccountMenu from '../components/AccountMenu.vue'

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

describe('AccountMenu — changer mon mot de passe', () => {
  it('propose le geste même pour un rôle Lecture seule', async () => {
    const w = mount(AccountMenu, { global: { stubs } })
    await w.find('button[aria-haspopup="menu"]').trigger('click')
    const item = w.findAll('button[role="menuitem"]').find(b => b.text().includes('Changer mon mot de passe'))
    expect(item).toBeTruthy()
  })

  it('ouvre le formulaire de changement au clic', async () => {
    const w = mount(AccountMenu, { global: { stubs } })
    await w.find('button[aria-haspopup="menu"]').trigger('click')
    await w.findAll('button[role="menuitem"]').find(b => b.text().includes('Changer mon mot de passe'))!.trigger('click')
    expect(w.find('input[name="old-password"]').exists()).toBe(true)
  })
})
