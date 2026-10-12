/**
 * Une exécution AUTOMATIQUE ne joue que les cas dotés d'un test technique (2026-10-12).
 *
 * Le défaut : un cas saisi à la main ou importé d'Excel était proposé — et inclus — dans les exécutions automatiques, où il
 * restait « Untested » pour toujours et faussait le total. Le serveur le refuse désormais ; l'écran ne le propose plus, sans
 * message ajouté (retour du porteur : « faut juste le gérer »). En mode manuel, tous les cas restent proposés.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

const createRun = vi.fn()
const listCases = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    listCases: (...a: any[]) => listCases(...a),
    listGroups: () => Promise.resolve([]),
    createRun: (...a: any[]) => createRun(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import AddTestRunForm from '../pages/AddTestRunForm.vue'

function cas(id: number, title: string, automatise: boolean) {
  return {
    id, title, module: 'Clients', module_id: 10, project_id: 1, group_id: null, group_title: null,
    refs: '', estimate: '', type: 'fonctionnel', etat: 'new', statut: 'untested', priority: 'medium', automatise,
    last_execution_status: null, last_functional_status: null, last_executed_at: null,
    last_verdict_version_id: null, verdict_from_other_version: false,
  }
}
const CAS = [cas(1, 'Création d\'un client', true), cas(2, 'Contrôle visuel du bulletin', false)]

beforeEach(() => {
  vi.clearAllMocks()
  listCases.mockResolvedValue({ items: CAS, next_cursor: null, total: CAS.length })
  createRun.mockResolvedValue({ id: 9 })
})

async function formulaire() {
  const w = monter(AddTestRunForm)
  await flushPromises()
  await w.get('input[required]').setValue('Campagne')
  return w
}

describe('AddTestRunForm — une exécution automatique ne propose que les cas dotés d\'un test technique', () => {
  it('en automatique, « tous les cas » ne compte que les cas dotés d\'un test technique', async () => {
    const w = await formulaire()

    expect(w.text()).toContain('(1 cas aujourd\'hui.)')
  })

  it('en automatique, le cas sans test technique n\'est pas proposé dans la sélection', async () => {
    const w = await formulaire()
    await w.get('input[type="radio"][value="frozen"]').setValue(true)

    expect(w.text()).toContain('Création d\'un client')
    expect(w.text()).not.toContain('Contrôle visuel du bulletin')
  })

  it('en manuel, tous les cas sont proposés', async () => {
    const w = await formulaire()
    await w.get('input[type="radio"][value="manuelle"]').setValue(true)
    await w.get('input[type="radio"][value="frozen"]').setValue(true)

    expect(w.text()).toContain('Création d\'un client')
    expect(w.text()).toContain('Contrôle visuel du bulletin')
    expect(w.text()).toContain('(2 cas aujourd\'hui.)')
  })

  it('repasser en automatique retire de la sélection les cas sans test technique', async () => {
    const w = await formulaire()
    await w.get('input[type="radio"][value="manuelle"]').setValue(true)
    await w.get('input[type="radio"][value="frozen"]').setValue(true)
    await w.findAll('button').find((b) => b.text() === 'Tout cocher')!.trigger('click')
    expect(w.text()).toContain('2 sélectionné(s)')

    await w.get('input[type="radio"][value="automatique"]').setValue(true)
    expect(w.text()).toContain('1 sélectionné(s)')
    await w.get('form').trigger('submit')
    await flushPromises()

    expect(createRun.mock.calls[0][1]).toMatchObject({ mode: 'automatique', selection_mode: 'frozen', case_ids: [1] })
  })
})
