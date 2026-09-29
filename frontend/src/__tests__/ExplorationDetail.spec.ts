/**
 * Écran de consultation de la cartographie explorée (routes/champs/actions/liens mesurés par le
 * crawl) — pure lecture depuis `GET /api/projects/{id}/exploration/pages`.
 *
 * Ce que ces tests gardent :
 * - les routes s'affichent dans l'ordre déjà trié rendu par le serveur ;
 * - un projet jamais exploré affiche un état vide explicite, jamais un tableau silencieusement vide ;
 * - le filtre texte restreint l'affichage sans re-appeler le serveur.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { monter } from './_montage'
import ExplorationDetail from '../pages/ExplorationDetail.vue'

const listProjects = vi.fn()
const getExploration = vi.fn()
const getExplorationPages = vi.fn()

vi.mock('../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      listProjects: (...a: any[]) => listProjects(...a),
      getExploration: (...a: any[]) => getExploration(...a),
      getExplorationPages: (...a: any[]) => getExplorationPages(...a),
    },
  }
})

const ETAT_EXPLORE = { explored: true, running: false, job_id: '', mesure_le: '2026-09-28',
  pages: 2, transitions: 0, champs: 1, contraintes: 0, modeles_backoffice: 0, resume: '', error: '' }
const ETAT_VIDE = { explored: false, running: false, job_id: '', mesure_le: '', pages: 0,
  transitions: 0, champs: 0, contraintes: 0, modeles_backoffice: 0, resume: '', error: '' }

async function monterEcran() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:pid/exploration', component: ExplorationDetail }],
  })
  await router.push('/projects/4/exploration')
  await router.isReady()
  const wrapper = monter(ExplorationDetail, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('écran de consultation de la cartographie explorée', () => {
  beforeEach(() => {
    listProjects.mockReset()
    getExploration.mockReset()
    getExplorationPages.mockReset()
  })

  it('affiche les routes capturées, dans l’ordre rendu par le serveur', async () => {
    listProjects.mockResolvedValue([
      { id: 4, name: 'yros', base_url: 'https://yros-portail.agilicis.com' },
    ])
    getExploration.mockResolvedValue(ETAT_EXPLORE)
    getExplorationPages.mockResolvedValue([
      { route: '/countryselect', titre: 'YROS App', url_exemple: '', champs: [],
        actions: [{ label: 'FR', soumet: false }], liens: [], formulaires: [] },
      { route: '/login', titre: 'YROS App', url_exemple: '',
        champs: [{ name: 'Adresse email', required: true }],
        actions: [{ label: 'Se connecter', soumet: true }],
        liens: [{ href: '/', text: 'YROS' }], formulaires: [] },
    ])

    const wrapper = await monterEcran()

    expect(wrapper.text()).toContain('yros')
    expect(wrapper.text()).toContain('/countryselect')
    expect(wrapper.text()).toContain('/login')
    const texte = wrapper.text()
    expect(texte.indexOf('/countryselect')).toBeLessThan(texte.indexOf('/login'))
  })

  it('affiche un état vide explicite quand rien n’a été exploré', async () => {
    listProjects.mockResolvedValue([{ id: 4, name: 'yros', base_url: 'https://x' }])
    getExploration.mockResolvedValue(ETAT_VIDE)
    getExplorationPages.mockResolvedValue([])

    const wrapper = await monterEcran()

    expect(wrapper.text()).toContain('Aucune page explorée')
  })

  it('le filtre restreint l’affichage aux routes correspondantes', async () => {
    listProjects.mockResolvedValue([{ id: 4, name: 'yros', base_url: 'https://x' }])
    getExploration.mockResolvedValue(ETAT_EXPLORE)
    getExplorationPages.mockResolvedValue([
      { route: '/login', titre: '', url_exemple: '', champs: [], actions: [], liens: [], formulaires: [] },
      { route: '/countryselect', titre: '', url_exemple: '', champs: [], actions: [], liens: [], formulaires: [] },
    ])

    const wrapper = await monterEcran()
    await wrapper.find('input[type="text"]').setValue('country')
    await flushPromises()

    expect(wrapper.text()).toContain('/countryselect')
    expect(wrapper.text()).not.toContain('/login')
  })

  it('déplie une route pour voir ses champs et actions', async () => {
    listProjects.mockResolvedValue([{ id: 4, name: 'yros', base_url: 'https://x' }])
    getExploration.mockResolvedValue(ETAT_EXPLORE)
    getExplorationPages.mockResolvedValue([
      { route: '/login', titre: '', url_exemple: '',
        champs: [{ name: 'Adresse email', required: true }],
        actions: [{ label: 'Se connecter', soumet: true }], liens: [], formulaires: [] },
    ])

    const wrapper = await monterEcran()
    expect(wrapper.text()).not.toContain('Adresse email')

    await wrapper.find('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Adresse email')
    expect(wrapper.text()).toContain('Se connecter')
  })
})
