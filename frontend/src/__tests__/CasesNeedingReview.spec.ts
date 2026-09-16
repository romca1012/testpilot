/**
 * L'écran « Cas à relire » — la liste rendue nécessaire par l'amendement §4.3-bis (2026-09-15) :
 * un cas approuvé automatiquement seulement s'il est propre, sinon il doit rester TROUVABLE.
 *
 * LA règle à ne pas casser : un cas listé ici s'ouvre sur sa fiche (où vit le geste
 * d'approbation/rejet, `ReviewGate`) — cet écran ne fait qu'aider à le trouver, il ne décide rien.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const casesNeedingReview = vi.fn()
const push = vi.fn()
vi.mock('../lib/api', () => ({ api: { casesNeedingReview: (...a: any[]) => casesNeedingReview(...a) } }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' } }),
  useRouter: () => ({ push }),
}))

import CasesNeedingReview from '../pages/CasesNeedingReview.vue'

beforeEach(() => { casesNeedingReview.mockReset(); push.mockReset() })

async function page(cas: any[]) {
  casesNeedingReview.mockResolvedValue(cas)
  const w = mount(CasesNeedingReview)
  await flushPromises()
  return w
}

describe('CasesNeedingReview', () => {
  it("dit qu'il n'y a rien à relire quand la liste est vide", async () => {
    const w = await page([])
    expect(w.text()).toContain('Aucun cas à relire')
  })

  it('liste un cas bloqué avec sa raison et son nombre de points de vigilance', async () => {
    const w = await page([{
      case_id: 82, title: 'Catalogue produits', module_name: 'Boutique',
      version_id: 5, reason: 'relecture humaine obligatoire avant la première exécution',
      lint_warnings_count: 2,
    }])

    expect(w.text()).toContain('C82')
    expect(w.text()).toContain('Catalogue produits')
    expect(w.text()).toContain('Boutique')
    expect(w.text()).toContain('relecture humaine obligatoire')
    expect(w.text()).toContain('2')
  })

  it('ouvrir un cas renvoie vers sa fiche (où vit le geste d’approbation)', async () => {
    const w = await page([{
      case_id: 82, title: 'Catalogue produits', module_name: 'Boutique',
      version_id: 5, reason: 'relecture humaine obligatoire', lint_warnings_count: 1,
    }])

    await w.get('tbody tr').trigger('click')

    expect(push).toHaveBeenCalledWith({ name: 'case-detail', params: { pid: '1', id: '82' } })
  })

  it('rend une erreur explicite et permet de relancer le chargement', async () => {
    casesNeedingReview.mockRejectedValueOnce(new Error('Droits insuffisants'))
      .mockResolvedValueOnce([])
    const w = mount(CasesNeedingReview)
    await flushPromises()

    expect(w.find('[role="alert"]').text()).toContain('Droits insuffisants')
    await w.get('button').trigger('click')
    await flushPromises()
    expect(casesNeedingReview).toHaveBeenCalledTimes(2)
  })
})
