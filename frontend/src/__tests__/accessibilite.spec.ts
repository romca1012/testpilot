/**
 * ACCESSIBILITÉ — le garde-fou, et les deux mécanismes du clavier (lot D, 2026-07-24).
 *
 * L'audit avait mesuré **21 attributs `aria`/`role`/`tabindex` pour 91 boutons** : l'outil était
 * inutilisable au lecteur d'écran, et hors WCAG 2.2 AA.
 *
 * ⚠️ **Le premier test est un garde-fou de non-régression, pas une vérification ponctuelle.**
 * Corriger 19 boutons une fois ne sert à rien si le vingtième arrive la semaine suivante : ce
 * test lit les fichiers source et échoue dès qu'un bouton muet apparaît. C'est la seule façon
 * qu'une règle d'accessibilité tienne dans la durée sans discipline surhumaine.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { flushPromises } from '@vue/test-utils'
import { monter } from './_montage'

// ── 1. Le garde-fou ──────────────────────────────────────────────────────────

function fichiersVue(racine: string): string[] {
  return readdirSync(racine).flatMap((nom) => {
    const chemin = join(racine, nom)
    if (statSync(chemin).isDirectory()) return fichiersVue(chemin)
    return chemin.endsWith('.vue') ? [chemin] : []
  })
}

describe('le garde-fou des noms accessibles', () => {
  it('AUCUN bouton ne doit être muet (ni texte, ni aria-label)', () => {
    const muets: string[] = []
    for (const chemin of fichiersVue(join(process.cwd(), 'src'))) {
      const source = readFileSync(chemin, 'utf-8')
      for (const m of source.matchAll(/<button\b([^>]*)>(.*?)<\/button>/gs)) {
        const [, attrs, contenu] = m
        // Un `<slot />` : le nom vient de l'appelant, c'est lui qui en répond.
        if (attrs.includes('aria-label') || contenu.includes('<slot')) continue
        const texte = contenu.replace(/<[^>]+>/g, '').trim()
        if (texte) continue
        muets.push(`${chemin.split(/[\\/]/).pop()} : ${attrs.trim().slice(0, 60)}`)
      }
    }
    expect(muets, `boutons sans nom accessible :\n${muets.join('\n')}`).toEqual([])
  })

  it('`title` seul ne compte PAS comme un nom accessible', () => {
    // ⚠️ La règle que ce lot applique : `title` est une infobulle. Elle n'apparaît qu'au survol
    // de la souris, et les lecteurs d'écran ne s'en servent qu'en dernier recours — quand ils
    // s'en servent. Un bouton identifié par son seul `title` est muet pour qui n'a pas de souris.
    const bouton = '<button title="Supprimer"><svg /></button>'
    const attrs = bouton.match(/<button\b([^>]*)>/)![1]
    expect(attrs.includes('aria-label')).toBe(false)   // ce que le garde-fou refuserait
  })
})

// ── 2. La modale : piège de focus et Échap ───────────────────────────────────

import Modal from '../components/ui/Modal.vue'

describe('la modale au clavier', () => {
  it('donne le focus au premier champ à l\'ouverture', async () => {
    const w = monter(Modal, {
      props: { open: false, title: 'Test' },
      slots: { default: '<input id="a" /><input id="b" />' },
      attachTo: document.body,
    })
    await w.setProps({ open: true })
    await flushPromises()

    expect(document.activeElement?.id).toBe('a')
    w.unmount()
  })

  it('ferme à Échap', async () => {
    const w = monter(Modal, { props: { open: true, title: 'Test' }, attachTo: document.body })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(w.emitted('close')).toBeTruthy()
    w.unmount()
  })

  it('ENFERME le focus : après le dernier élément, on revient au premier', async () => {
    // Sans ce piège, `Tab` sort de la modale et parcourt la page qui est DERRIÈRE, masquée par
    // le fond : on navigue dans un écran qu'on ne voit plus, sans moyen de comprendre où on est.
    const w = monter(Modal, {
      props: { open: false, title: 'Test' },
      slots: { default: '<input id="a" /><input id="b" />' },
      attachTo: document.body,
    })
    await w.setProps({ open: true })
    await flushPromises()

    // Le dernier élément focusable est le bouton « Fermer » ou le second champ selon l'ordre du
    // DOM : on place le focus sur le dernier, puis on tabule.
    const focusables = w.element.querySelectorAll<HTMLElement>('input, button')
    const dernier = focusables[focusables.length - 1]
    dernier.focus()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab' }))
    await flushPromises()

    expect(w.element.contains(document.activeElement)).toBe(true)
    w.unmount()
  })
})

// ── 3. La palette de commandes ───────────────────────────────────────────────

const listCases = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: { listCases: (...a: any[]) => listCases(...a) },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1' }, query: {} }),
  useRouter: () => ({ push }),
  RouterLink: { template: '<a><slot/></a>' },
}))

import PaletteCommandes from '../components/PaletteCommandes.vue'

beforeEach(() => {
  vi.clearAllMocks()
  listCases.mockResolvedValue([
    { id: 12, title: 'Retour matériel', module: 'Demandes' },
  ])
})

async function ouvrirPalette() {
  const w = monter(PaletteCommandes, { attachTo: document.body })
  await flushPromises()
  window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }))
  await flushPromises()
  return w
}

describe('la palette de commandes', () => {
  it('s\'ouvre à Ctrl+K et se ferme à Échap', async () => {
    const w = await ouvrirPalette()
    // ⚠️ On vise le RÔLE, pas le texte du champ : `text()` ne rend pas les attributs, donc
    // chercher le `placeholder` dedans testait l'absence d'une chose qui n'y est jamais.
    expect(w.find('[role="dialog"]').exists()).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    expect(w.find('[role="dialog"]').exists()).toBe(false)
    w.unmount()
  })

  it('répond aussi à ⌘K — sinon elle est inatteignable sur Mac', async () => {
    const w = monter(PaletteCommandes, { attachTo: document.body })
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', metaKey: true }))
    await flushPromises()

    expect(w.find('[role="dialog"]').exists()).toBe(true)
    w.unmount()
  })

  it('trouve un CAS par son titre, sans requête serveur', async () => {
    const w = await ouvrirPalette()
    listCases.mockClear()
    await w.find('input').setValue('matériel')
    await flushPromises()

    expect(w.text()).toContain('Retour matériel')
    expect(listCases).not.toHaveBeenCalled()   // le cache du lot A suffit
    w.unmount()
  })

  it('ouvre l\'entrée sélectionnée avec Entrée', async () => {
    const w = await ouvrirPalette()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await flushPromises()

    expect(push).toHaveBeenCalled()
    w.unmount()
  })

  it('AFFICHE ses raccourcis — c\'est ainsi qu\'on les apprend', async () => {
    const w = await ouvrirPalette()

    expect(w.text()).toContain('naviguer')
    expect(w.text()).toContain('ouvrir')
    w.unmount()
  })
})
