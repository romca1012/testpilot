/** Étape 7b (A109) : la fiche du cas montre le mode opératoire du dernier parcours, et le bouton à qui peut enregistrer. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount, RouterLinkStub } from '@vue/test-utils'
import ParcoursDuCas from '../components/case/ParcoursDuCas.vue'

const getParcours = vi.fn()
vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return { ...actual, api: { ...actual.api, getParcours: (...a: any[]) => getParcours(...a) } }
})

const monter = (peutEnregistrer: boolean) => mount(ParcoursDuCas, {
  props: { caseId: 5, projectId: 1, peutEnregistrer }, global: { stubs: { RouterLink: RouterLinkStub } },
})

beforeEach(() => getParcours.mockReset())

describe('ParcoursDuCas', () => {
  it('montre le mode opératoire le plus récent', async () => {
    getParcours.mockResolvedValue({ parcours: [
      { id: 2, auteur: 'Ana', created_at: '2026-10-23T10:00:00', version_id: null, actions: [],
        mode_operatoire: ['1. Cliquer sur « Nouveau » (bouton)'] },
      { id: 1, auteur: 'Bo', created_at: '2026-10-22T10:00:00', version_id: 4, actions: [], mode_operatoire: ['1. Ancien'] },
    ] })
    const w = monter(true)
    await flushPromises()
    expect(w.get('[data-testid="mode-operatoire"]').text()).toBe('1. Cliquer sur « Nouveau » (bouton)')
    expect(w.text()).toContain('Enregistrer à nouveau')
    expect(w.text()).toContain('1 plus ancien(s) gardé(s)')
  })

  it('sans parcours et sans droit, rien ne s\'affiche', async () => {
    getParcours.mockResolvedValue({ parcours: [] })
    const w = monter(false)
    await flushPromises()
    expect(w.find('[data-testid="parcours-du-cas"]').exists()).toBe(false)
  })

  it('sans parcours, qui peut enregistrer voit le bouton', async () => {
    getParcours.mockResolvedValue({ parcours: [] })
    const w = monter(true)
    await flushPromises()
    expect(w.getComponent(RouterLinkStub).props('to')).toBe('/projects/1/cases/5/parcours')
    expect(w.text()).toContain('Enregistrer le parcours')
  })
})
