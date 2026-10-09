/**
 * D32 (2026-10-09) — « Valeurs refusées à confirmer » : un refus d'une valeur que le métier demande n'est
 * appris qu'après la décision d'un humain. La section se tait quand il n'y a rien à trancher, et chaque
 * bouton envoie l'identité EXACTE de la règle avec la décision.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const refusAConfirmer = vi.fn()
const deciderRefus = vi.fn()
vi.mock('../lib/api', () => ({
  api: {
    refusAConfirmer: (...a: any[]) => refusAConfirmer(...a),
    deciderRefus: (...a: any[]) => deciderRefus(...a),
  },
}))

import RefusAConfirmer from '../components/RefusAConfirmer.vue'

const REFUS = {
  route: '/fournisseur/creation', champ: 'date_fin', type_contrainte: 'customError', valeur_contrainte: '',
  valeur_refusee: '2027', preuve: 'Date invalide', occurrences: 2, derniere_le: '2026-10-09T10:00:00+00:00',
}

beforeEach(() => { refusAConfirmer.mockReset(); deciderRefus.mockReset() })

async function section(liste: any[]) {
  refusAConfirmer.mockResolvedValue(liste)
  const w = mount(RefusAConfirmer, { props: { projectId: '7' } })
  await flushPromises()
  return w
}

describe('RefusAConfirmer', () => {
  it('ne montre rien quand aucun refus n\'attend', async () => {
    const w = await section([])
    expect(w.text()).toBe('')
  })

  it('dit que la valeur refusée est demandée par le métier et pas encore apprise', async () => {
    const w = await section([REFUS])
    expect(w.text()).toContain('« 2027 »')
    expect(w.text()).toContain('date_fin')
    expect(w.text()).toContain('bug probable')
    expect(w.text()).toContain('pas appris')
    expect(w.text()).toContain('Date invalide')
  })

  it.each([
    ['règle de l\'application', 'confirmee'],
    ['bug', 'rejetee'],
  ])('« %s » envoie la décision %s avec la règle exacte, puis retire le refus traité', async (libelle, decision) => {
    deciderRefus.mockResolvedValue([])
    const w = await section([REFUS])

    await w.findAll('button').find((b) => b.text().includes(libelle))!.trigger('click')
    await flushPromises()

    expect(deciderRefus).toHaveBeenCalledWith('7', REFUS, decision)
    expect(w.text()).toBe('')
  })
})
