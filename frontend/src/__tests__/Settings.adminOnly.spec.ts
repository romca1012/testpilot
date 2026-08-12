/**
 * Réglages réservés à l'Admin (2026-08-11, mis à jour le 2026-08-12) — le SERVEUR est la seule
 * vraie garde (403 sinon) ; cet écran ne fait que désactiver ce qui serait de toute façon refusé.
 *
 * ⚠️ `service_account_name` (le seul réglage NON admin_only) a été RETIRÉ du vocabulaire le
 * 2026-08-12 (demande du porteur : plus un réglage modifiable depuis l'écran). Aujourd'hui, tous
 * les réglages génériques connus sont admin_only — ce test le reflète avec deux réglages
 * admin_only plutôt qu'un contraste admin/non-admin qui n'existe plus.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listSettings = vi.fn()
vi.mock('../lib/api', () => ({ api: { listSettings: (...a: any[]) => listSettings(...a) } }))

const session = { value: { authenticated: true, role: 'testeur', name: 'Awa' } as any }
vi.mock('../lib/useSession', () => ({ useSession: () => ({ session }) }))

import Settings from '../pages/Settings.vue'

const REGLAGES = [
  { key: 'reference_url_template', value: '', source: 'default',
    description: 'desc refs', admin_only: true, secret: false },
]

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

async function page() {
  listSettings.mockResolvedValue(REGLAGES)
  const w = mount(Settings, { global: { stubs } })
  await flushPromises()
  return w
}

beforeEach(() => { vi.clearAllMocks() })

describe('Settings — réglages réservés à l\'Admin', () => {
  it('un Testeur voit le champ Admin-only désactivé, avec une explication', async () => {
    session.value.role = 'testeur'
    const w = await page()
    const champRefs = w.find('input')
    expect(champRefs.attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('Réservé au rôle Admin')
  })

  it('un Admin voit le champ actif', async () => {
    session.value.role = 'admin'
    const w = await page()
    const champRefs = w.find('input')
    expect(champRefs.attributes('disabled')).toBeUndefined()
    expect(w.text()).not.toContain('Réservé au rôle Admin')
  })
})
