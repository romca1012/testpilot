import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ThemeSwitch from '../components/ThemeSwitch.vue'

describe('ThemeSwitch', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.className = 'dark'
  })

  it('applique et mémorise le thème clair', async () => {
    const wrapper = mount(ThemeSwitch)
    await wrapper.get('button[aria-label="Utiliser le thème clair"]').trigger('click')

    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(document.documentElement.classList.contains('dark')).toBe(false)
    expect(localStorage.getItem('testpilot-theme')).toBe('light')
  })
})
