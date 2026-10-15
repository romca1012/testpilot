/**
 * Verrou du défilement des fenêtres (Modal, ConfirmDialog).
 *
 * Mesuré le 2026-10-15 : après « Associer », la fenêtre se fermait et disparaissait avec son bouton DANS LE MÊME RENDU (plus
 * rien à proposer) — le verrou n'était jamais rendu, la page restait figée. Ces tests le reproduisent.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'
import Modal from '../components/ui/Modal.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'

afterEach(() => { document.body.style.overflow = '' })

function parent(fenetre: any, props: Record<string, unknown>) {
  const ouvert = ref(false)
  const present = ref(true)
  const Parent = defineComponent({
    setup: () => () => (present.value ? h(fenetre, { ...props, open: ouvert.value }) : null),
  })
  return { w: mount(Parent, { attachTo: document.body }), ouvert, present }
}

describe.each([
  ['Modal', Modal, { title: 'T' }],
  ['ConfirmDialog', ConfirmDialog, { title: 'T', message: 'M' }],
])('%s — verrou du défilement', (_nom, fenetre, props) => {
  it('falsifiable : fermée ET retirée dans le même rendu, la page défile de nouveau', async () => {
    const { w, ouvert, present } = parent(fenetre, props)
    ouvert.value = true
    await nextTick()
    expect(document.body.style.overflow).toBe('hidden')

    ouvert.value = false
    present.value = false
    await nextTick()

    expect(document.body.style.overflow).toBe('')
    w.unmount()
  })

  it('fermée normalement, la page défile de nouveau', async () => {
    const { w, ouvert } = parent(fenetre, props)
    ouvert.value = true
    await nextTick()

    ouvert.value = false
    await nextTick()

    expect(document.body.style.overflow).toBe('')
    w.unmount()
    expect(document.body.style.overflow).toBe('')
  })
})
