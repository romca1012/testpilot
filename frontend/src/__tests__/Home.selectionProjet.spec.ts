import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const replace = vi.fn()
vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }))

import Home from '../pages/Home.vue'

describe('Accueil après connexion', () => {
  it('ouvre toujours la sélection de projets', async () => {
    mount(Home)
    await flushPromises()
    expect(replace).toHaveBeenCalledWith('/projects')
  })
})
