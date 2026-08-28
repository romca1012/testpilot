/**
 * Notifications par email (2026-08-12) — section dédiée de Settings.vue, distincte de la boucle
 * générique (7 champs SMTP alignés y recréeraient le problème signalé par le porteur : « onglet
 * réglages mal utilisé »).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listSettings = vi.fn()
const setSetting = vi.fn()
const testSmtp = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    listSettings: (...a: any[]) => listSettings(...a),
    setSetting: (...a: any[]) => setSetting(...a),
    testSmtp: (...a: any[]) => testSmtp(...a),
  },
}))

const session = { value: { authenticated: true, role: 'admin', name: 'Root' } as any }
vi.mock('../lib/useSession', () => ({ useSession: () => ({ session }) }))

import Settings from '../pages/Settings.vue'

const REGLAGES_BASE = [
  { key: 'reference_url_template', value: '', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'instance_name', value: 'TestPilot', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'instance_timezone', value: 'Europe/Paris', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'date_format', value: 'DD/MM/YYYY', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'notifications_enabled', value: '', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'smtp_host', value: '', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'smtp_port', value: '587', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'smtp_username', value: '', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'smtp_password', value: '', source: 'default', description: 'd', admin_only: true, secret: true },
  { key: 'smtp_from', value: '', source: 'default', description: 'd', admin_only: true, secret: false },
  { key: 'smtp_use_tls', value: '1', source: 'default', description: 'd', admin_only: true, secret: false },
]

const stubs = { RouterLink: { template: '<a><slot/></a>' } }

async function page(reglages = REGLAGES_BASE) {
  listSettings.mockResolvedValue(reglages)
  const w = mount(Settings, { global: { stubs } })
  await flushPromises()
  return w
}

beforeEach(() => { vi.clearAllMocks() })

describe('Settings — section Notifications par email', () => {
  it('les clés SMTP ne polluent pas la liste générique', async () => {
    const w = await page()
    expect(w.text()).not.toContain('smtp_host')
    expect(w.text()).not.toContain('notifications_enabled')
    expect(w.text()).not.toContain('instance_name')
    expect(w.text()).not.toContain('instance_timezone')
  })

  it('le mot de passe secret n\'est jamais préaffiché, même masqué', async () => {
    const avecMotDePasse = REGLAGES_BASE.map((r) =>
      r.key === 'smtp_password' ? { ...r, value: '••••••••' } : r)
    const w = await page(avecMotDePasse)
    const champMdp = w.find('input[type="password"]')
    expect((champMdp.element as HTMLInputElement).value).toBe('')
    expect(champMdp.attributes('placeholder')).toContain('Déjà défini')
  })

  it('enregistrer envoie chaque champ, mais PAS le mot de passe si laissé vide', async () => {
    setSetting.mockResolvedValue({})
    const w = await page()
    await w.find('input[placeholder="smtp.exemple.fr"]').setValue('smtp.exemple.fr')
    const boutonEnregistrer = w.findAll('button').find((b) => b.text() === 'Enregistrer' && b.element.closest('section')?.textContent?.includes('Notifications par email'))
    await boutonEnregistrer!.trigger('click')
    await flushPromises()

    const clesEnvoyees = setSetting.mock.calls.map((c) => c[0])
    expect(clesEnvoyees).toContain('smtp_host')
    expect(clesEnvoyees).not.toContain('smtp_password')
  })

  it('un mot de passe saisi EST envoyé', async () => {
    setSetting.mockResolvedValue({})
    const w = await page()
    await w.find('input[type="password"]').setValue('nouveau-secret')
    const boutonEnregistrer = w.findAll('button').find((b) => b.text() === 'Enregistrer' && b.element.closest('section')?.textContent?.includes('Notifications par email'))
    await boutonEnregistrer!.trigger('click')
    await flushPromises()

    expect(setSetting).toHaveBeenCalledWith('smtp_password', 'nouveau-secret')
  })

  it('tester envoie un email de test et affiche le résultat', async () => {
    testSmtp.mockResolvedValue({ succes: true, erreur: '' })
    const w = await page()
    await w.find('input[placeholder="vous@exemple.fr"]').setValue('moi@exemple.fr')
    const boutonTester = w.findAll('button').find((b) => b.text() === 'Tester')
    await boutonTester!.trigger('click')
    await flushPromises()

    expect(testSmtp).toHaveBeenCalledWith('moi@exemple.fr')
    expect(w.text()).toContain('Email envoyé')
  })

  it('un échec de test affiche l\'erreur, pas un succès muet', async () => {
    testSmtp.mockResolvedValue({ succes: false, erreur: 'authentification refusée' })
    const w = await page()
    await w.find('input[placeholder="vous@exemple.fr"]').setValue('moi@exemple.fr')
    const boutonTester = w.findAll('button').find((b) => b.text() === 'Tester')
    await boutonTester!.trigger('click')
    await flushPromises()

    expect(w.text()).toContain('authentification refusée')
  })

  it('un Testeur voit la section désactivée', async () => {
    session.value.role = 'testeur'
    const w = await page()
    const champHote = w.find('input[placeholder="smtp.exemple.fr"]')
    expect(champHote.attributes('disabled')).toBeDefined()
    session.value.role = 'admin'
  })
})
