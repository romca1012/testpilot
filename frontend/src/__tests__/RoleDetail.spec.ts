import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const role = { params: { role: 'testeur' } }
vi.mock('vue-router', () => ({
  useRoute: () => role,
  useRouter: () => ({ push: vi.fn() }),
}))

import RoleDetail from '../pages/RoleDetail.vue'

describe('Fiche d’un rôle', () => {
  it('présente uniquement les permissions réellement héritées', () => {
    const w = mount(RoleDetail)
    expect(w.get('h1').text()).toBe('Testeur')
    expect(w.text()).toContain('Créer, déplacer et modifier les cas')
    expect(w.text()).toContain('Générer et modifier les scripts')
    const lignes = w.findAll('tbody tr')
    expect(lignes.find(l => l.text().includes('Créer, déplacer et modifier les cas'))?.text()).toContain('Autorisé')
    expect(lignes.find(l => l.text().includes('Générer et modifier les scripts'))?.text()).toContain('Non autorisé')
  })

  it('refuse un rôle inconnu sans inventer de droits', async () => {
    role.params.role = 'inconnu'
    const w = mount(RoleDetail)
    expect(w.get('[role="alert"]').text()).toContain('n’existe pas')
    expect(w.find('table').exists()).toBe(false)
    role.params.role = 'testeur'
  })
})
