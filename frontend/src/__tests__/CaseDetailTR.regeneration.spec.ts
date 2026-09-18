import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import CaseDetailTR from '../pages/CaseDetailTR.vue'

const { getCase, automateCase, getGenerationJob, permissions } = vi.hoisted(() => ({
  getCase: vi.fn(), automateCase: vi.fn(), getGenerationJob: vi.fn(), permissions: { dev: true },
}))
vi.mock('../lib/api', () => ({
  roleSuffisant: (_role: string, minimum: string) => minimum !== 'dev' || permissions.dev,
  openProjectEvents: () => ({ close: () => {} }),
  api: { getCase, automateCase, getGenerationJob, getCaseScenarios: vi.fn().mockResolvedValue([]) },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '19' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
const stubs = { TestsResultsTab: true, DefectsTab: true, HistoryTab: true, ReviewGate: true,
  RouterLink: { template: '<a><slot/></a>' } }
function detail(feature = 'Scénario: création') {
  return { case: { id: 19, title: 'Créer un équipement', module: 'Parc IT' }, current_version_id: 24,
    versions: [{ id: 24, feature_content: feature, preconditions: 'DSI', test_steps: '["Confirmer"]', expected_result: 'Équipement créé' }],
    reviews: [], executions: [], gate: { allowed: true, needs_review: false } }
}
async function page(feature?: string) {
  getCase.mockResolvedValue(detail(feature))
  const w = mount(CaseDetailTR, { global: { stubs } })
  await flushPromises()
  return w
}
beforeEach(() => { vi.clearAllMocks(); permissions.dev = true })
afterEach(() => { vi.useRealTimers() })

describe('18/09/2026 : C19 avec technique masquait toute régénération', () => {
  it('propose Régénérer sur la vraie page du cas déjà technique', async () => {
    const w = await page()
    expect(w.findAll('button').some(b => b.text() === 'Régénérer')).toBe(true)
    expect(w.text()).not.toContain("Automatiser avec l'IA")
    w.unmount()
  })
  it('conserve Automatiser pour un cas manuel', async () => {
    const w = await page('')
    expect(w.text()).toContain("Automatiser avec l'IA")
    expect(w.text()).not.toContain('Régénérer')
    w.unmount()
  })
  it('réserve la régénération au rôle développeur', async () => {
    permissions.dev = false
    const w = await page()
    expect(w.text()).not.toContain('Régénérer')
    w.unmount()
  })
  it('indique le travail en cours puis recharge la version à relire', async () => {
    vi.useFakeTimers()
    automateCase.mockResolvedValue({ job_id: 'job' })
    getGenerationJob.mockResolvedValue({ status: 'done' })
    const w = await page()
    const button = w.findAll('button').find(b => b.text() === 'Régénérer')!
    await button.trigger('click')
    await flushPromises()
    expect(automateCase).toHaveBeenCalledExactlyOnceWith(19)
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.attributes('aria-busy')).toBe('true')
    expect(button.text()).toBe('Génération…')
    getCase.mockResolvedValue({ ...detail(), gate: { allowed: false, needs_review: true } })
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(getCase).toHaveBeenCalledTimes(2)
    expect(w.findComponent({ name: 'ReviewGate' }).exists()).toBe(true)
    w.unmount()
  })
})
