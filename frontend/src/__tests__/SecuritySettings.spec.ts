import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const getSecurityStatus = vi.fn()
vi.mock('../lib/api', () => ({ api: { getSecurityStatus: () => getSecurityStatus() } }))
import SecuritySettings from '../pages/SecuritySettings.vue'

const etat = {
  password_min_length: 8, password_hash: 'PBKDF2-HMAC-SHA256 (200 000 itérations)',
  session_days: 7, cookie_http_only: true, cookie_same_site: 'Lax', cookie_secure: false,
  session_secret_external: false, data_secret_external: false,
  login_max_failures: 5, login_window_minutes: 15, production_ready: false,
}

describe('Sécurité de l’instance', () => {
  beforeEach(() => { vi.clearAllMocks(); getSecurityStatus.mockResolvedValue(etat) })

  it('affiche l’état utile sans exposer les détails techniques du serveur', async () => {
    const w = mount(SecuritySettings)
    await flushPromises()
    expect(w.text()).toContain('8 caractères')
    expect(w.text()).toContain('5 échecs')
    expect(w.text()).toContain('15 minutes')
    expect(w.text()).not.toContain('PBKDF2')
    expect(w.text()).not.toContain('Cookie HTTPS uniquement')
    expect(w.text()).not.toContain('Secret de session externe')
    expect(w.text()).not.toContain('Clé de chiffrement externe')
    expect(w.text()).not.toContain('TESTPILOT_SESSION_SECRET=')
  })

  it('annonce une instance prête lorsque les protections de production sont actives', async () => {
    getSecurityStatus.mockResolvedValue({ ...etat, cookie_secure: true,
      session_secret_external: true, data_secret_external: true, production_ready: true })
    const w = mount(SecuritySettings)
    await flushPromises()
    expect(w.text()).toContain('Prêt')
    expect(w.text()).toContain('Les protections indispensables sont configurées.')
  })

  it('remplace l’erreur réseau technique par une action compréhensible', async () => {
    getSecurityStatus.mockRejectedValueOnce(new TypeError('Failed to fetch')).mockResolvedValueOnce(etat)
    const w = mount(SecuritySettings)
    await flushPromises()
    expect(w.text()).toContain('Le serveur TestPilot est momentanément inaccessible')
    expect(w.text()).not.toContain('Failed to fetch')
    await w.get('button').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Mots de passe')
  })
})
