/**
 * D33 (2026-10-10, prolonge D25) — « Sans repli par l'IA » : COCHÉE par défaut sur une campagne automatique, transmise telle
 * quelle ; masquée sous une campagne stricte (qui l'inclut déjà) ; une campagne manuelle ne la transmet jamais.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const createRun = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    listCases: () => Promise.resolve({ items: [], next_cursor: null, total: 0 }),
    listGroups: () => Promise.resolve([]),
    createRun: (...a: any[]) => createRun(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import AddTestRunForm from '../pages/AddTestRunForm.vue'

beforeEach(() => { createRun.mockReset(); createRun.mockResolvedValue({ id: 9 }) })

async function formulaire() {
  const w = monter(AddTestRunForm)
  await flushPromises()
  await w.get('input[required]').setValue('Campagne')
  return w
}

describe('AddTestRunForm — sans repli par l\'IA (D33)', () => {
  it('est cochée par défaut et envoyée au serveur', async () => {
    const w = await formulaire()
    const option = w.get('[data-testid="campagne-sans-repli"]')

    expect((option.element as HTMLInputElement).checked).toBe(true)
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(createRun.mock.calls[0][1]).toMatchObject({ sans_repli: true, strict: false })
  })

  it('décochée, la campagne autorise le repli', async () => {
    const w = await formulaire()
    await w.get('[data-testid="campagne-sans-repli"]').setValue(false)
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(createRun.mock.calls[0][1]).toMatchObject({ sans_repli: false })
  })

  it('une campagne stricte la masque et l\'inclut', async () => {
    const w = await formulaire()
    await w.get('[data-testid="campagne-sans-repli"]').setValue(false)
    await w.get('[data-testid="campagne-stricte"]').setValue(true)

    expect(w.find('[data-testid="campagne-sans-repli"]').exists()).toBe(false)
    await w.get('form').trigger('submit')
    await flushPromises()
    expect(createRun.mock.calls[0][1]).toMatchObject({ strict: true, sans_repli: true })
  })
})
