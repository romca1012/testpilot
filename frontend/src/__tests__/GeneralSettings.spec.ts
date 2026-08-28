import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const listSettings = vi.fn()
const setSetting = vi.fn()
const listTimezoneOptions = vi.fn()
const ensureLoaded = vi.fn()
const session = { value: { authenticated: true, role: 'admin' } }

vi.mock('../lib/api', () => ({
  api: {
    listSettings: (...a: any[]) => listSettings(...a),
    setSetting: (...a: any[]) => setSetting(...a),
    listTimezoneOptions: (...a: any[]) => listTimezoneOptions(...a),
  },
}))
vi.mock('../lib/useSession', () => ({ useSession: () => ({ session }) }))
vi.mock('../lib/useSettings', () => ({ useSettings: () => ({ ensureLoaded }) }))

import GeneralSettings from '../pages/GeneralSettings.vue'

const valeurs = [
  ['instance_name', 'TestPilot'], ['instance_timezone', 'Europe/Paris'],
  ['date_format', 'DD/MM/YYYY'],
].map(([key, value]) => ({ key, value, source: 'default', description: '', admin_only: true, secret: false }))

describe('Paramètres généraux de l’instance', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    session.value.role = 'admin'
    listSettings.mockResolvedValue(valeurs)
    listTimezoneOptions.mockResolvedValue([
      { value: 'Europe/Paris', label: 'Paris' },
      { value: 'Africa/Dakar', label: 'Sénégal' },
    ])
    setSetting.mockImplementation((key: string, value: string) => Promise.resolve({
      key, value, source: 'db', description: '', admin_only: true, secret: false,
    }))
  })

  it('charge les valeurs et ne propose pas une sauvegarde inutile', async () => {
    const w = mount(GeneralSettings)
    await flushPromises()
    expect((w.get('input').element as HTMLInputElement).value).toBe('TestPilot')
    expect(w.findAll('select')).toHaveLength(2)
    expect(w.text()).not.toContain('English')
    expect(w.text()).toContain('Sénégal — Africa/Dakar')
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  })

  it('enregistre le formulaire modifié et rafraîchit les réglages partagés', async () => {
    listSettings.mockResolvedValueOnce(valeurs).mockResolvedValueOnce(
      valeurs.map((r) => r.key === 'instance_name' ? { ...r, value: 'TestPilot AXENEO' } : r),
    )
    const w = mount(GeneralSettings)
    await flushPromises()
    await w.get('input').setValue('TestPilot AXENEO')
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(setSetting).toHaveBeenCalledWith('instance_name', 'TestPilot AXENEO')
    expect(setSetting).toHaveBeenCalledTimes(3)
    expect(ensureLoaded).toHaveBeenCalledWith(true)
    expect(w.text()).toContain('Paramètres généraux enregistrés.')
  })

  it('reste en consultation seule pour un non-administrateur', async () => {
    session.value.role = 'testeur'
    const w = mount(GeneralSettings)
    await flushPromises()
    expect(w.text()).toContain('Consultation uniquement')
    expect(w.get('input').attributes('disabled')).toBeDefined()
    expect(w.get('button[type="submit"]').attributes('disabled')).toBeDefined()
  })
})
