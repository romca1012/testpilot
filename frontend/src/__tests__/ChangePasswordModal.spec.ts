/**
 * Changer SON PROPRE mot de passe (2026-09-03) — jusqu'ici, seul un Admin pouvait en
 * réinitialiser un (Réglages > Utilisateurs). Formulaire accessible depuis AccountMenu.vue.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const changePassword = vi.fn()
vi.mock('../lib/api', async () => {
  const actual = await vi.importActual<any>('../lib/api')
  return {
    ...actual,
    api: { ...actual.api, changePassword: (...a: any[]) => changePassword(...a) },
  }
})

import ChangePasswordModal from '../components/ChangePasswordModal.vue'
import { ApiError } from '../lib/api'

beforeEach(() => { vi.clearAllMocks() })

async function remplirEtSoumettre(w: ReturnType<typeof mount>, ancien: string, nouveau: string, confirmation = nouveau) {
  await w.find('input[name="old-password"]').setValue(ancien)
  await w.find('input[name="new-password"]').setValue(nouveau)
  await w.find('input[name="confirm-password"]').setValue(confirmation)
  await w.find('#change-password').trigger('submit')
  await flushPromises()
}

describe('ChangePasswordModal', () => {
  it('le formulaire existe avec ses trois champs quand ouvert', () => {
    const w = mount(ChangePasswordModal, { props: { open: true } })
    expect(w.find('input[name="old-password"]').exists()).toBe(true)
    expect(w.find('input[name="new-password"]').exists()).toBe(true)
    expect(w.find('input[name="confirm-password"]').exists()).toBe(true)
  })

  it('rien ne se rend quand fermé', () => {
    const w = mount(ChangePasswordModal, { props: { open: false } })
    expect(w.find('input[name="old-password"]').exists()).toBe(false)
  })

  it('se soumet avec les deux mots de passe et affiche la confirmation de succès', async () => {
    changePassword.mockResolvedValue({ authenticated: true, name: 'Awa', role: 'testeur', lock_enabled: true })
    const w = mount(ChangePasswordModal, { props: { open: true } })

    await remplirEtSoumettre(w, 'ancienmdp', 'nouveaumdp')

    expect(changePassword).toHaveBeenCalledWith('ancienmdp', 'nouveaumdp')
    expect(w.text()).toContain('changé avec succès')
  })

  it('affiche un message ciblé si l’ancien mot de passe est refusé (code mot_de_passe_incorrect)', async () => {
    changePassword.mockRejectedValue(new ApiError(401, 'Mot de passe incorrect', 'mot_de_passe_incorrect'))
    const w = mount(ChangePasswordModal, { props: { open: true } })

    await remplirEtSoumettre(w, 'faux', 'nouveaumdp')

    expect(w.find('[role="alert"]').text()).toContain('incorrect')
    expect(w.text()).not.toContain('changé avec succès')
  })

  it('refuse localement un nouveau mot de passe trop court, sans appeler l’API', async () => {
    const w = mount(ChangePasswordModal, { props: { open: true } })

    await w.find('input[name="old-password"]').setValue('ancienmdp')
    await w.find('input[name="new-password"]').setValue('court')
    await w.find('input[name="confirm-password"]').setValue('court')
    await w.find('#change-password').trigger('submit')
    await flushPromises()

    expect(changePassword).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').text()).toContain('8 caractères')
  })

  it('refuse localement une confirmation qui ne correspond pas', async () => {
    const w = mount(ChangePasswordModal, { props: { open: true } })

    await remplirEtSoumettre(w, 'ancienmdp', 'nouveaumdp', 'autrechose')

    expect(changePassword).not.toHaveBeenCalled()
    expect(w.find('[role="alert"]').text()).toContain('correspond')
  })

  it('émet close quand on clique Annuler', async () => {
    const w = mount(ChangePasswordModal, { props: { open: true } })
    await w.findAll('button').find(b => b.text() === 'Annuler')!.trigger('click')
    expect(w.emitted('close')).toBeTruthy()
  })
})
