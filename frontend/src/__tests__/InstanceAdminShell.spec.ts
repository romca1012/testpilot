import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import InstanceAdminShell from '../components/InstanceAdminShell.vue'

describe('administration de l’instance', () => {
  it('sépare clairement les réglages globaux des paramètres projet', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/projects', component: { template: '<div />' } },
        { path: '/admin/projects', component: { template: '<div />' } },
        { path: '/settings', component: { template: '<div />' } },
        { path: '/settings/general', component: { template: '<div />' } },
        { path: '/settings/security', component: { template: '<div />' } },
        { path: '/utilisateurs', component: { template: '<div />' } },
      ],
    })
    await router.push('/settings')
    await router.isReady()

    const wrapper = mount(InstanceAdminShell, {
      global: { plugins: [router] },
      slots: { default: '<p>Contenu administré</p>' },
    })

    expect(wrapper.text()).toContain('Instance')
    expect(wrapper.text()).toContain('TestPilot')
    expect(wrapper.text()).toContain('Intégrations')
    expect(wrapper.text()).toContain('Paramètres du site')
    expect(wrapper.text()).toContain('Sécurité')
    expect(wrapper.text()).toContain('Utilisateurs et rôles')
    expect(wrapper.text()).not.toContain('Cas de test')
    expect(wrapper.findAll('a[href="/admin/projects"]').some(link => link.text().includes('Projets'))).toBe(true)
  })
})
