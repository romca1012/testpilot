/**
 * Lot PT-01a — la page « Paramètres de test » d'un projet et son point d'entrée.
 *
 * Ce que ces tests gardent :
 * 1. interrupteur ÉTEINT : aucun bouton, la page des projets est celle d'avant (décisions A6 et A17) ;
 * 2. chaque onglet a sa propre adresse, et une adresse inconnue retombe sur le premier onglet ;
 * 3. le rôle sur le projet décide de ce que l'écran propose ;
 * 4. on ne quitte pas un onglet modifié sans confirmation ;
 * 5. (PT-01b) organisation allumée, la fenêtre « Identité et application » ne garde que le nom, le connecteur, la version et
 *    l'adresse, et n'envoie que ces champs.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

const listProjects = vi.fn()
const listAdminProjects = vi.fn()
const getExploration = vi.fn()
const updateProject = vi.fn()
const push = vi.fn()
const route = { name: 'admin-projects', params: {} as Record<string, string> }
const session = ref<any>({ authenticated: true, role: 'admin' })
const actifs = ref(false)
const gardes: Array<(to: any) => any> = []

vi.mock('../lib/api', () => ({
  api: {
    listProjects: (...a: any[]) => listProjects(...a),
    listAdminProjects: (...a: any[]) => listAdminProjects(...a),
    getExploration: (...a: any[]) => getExploration(...a),
    updateProject: (...a: any[]) => updateProject(...a), createProject: vi.fn(), deleteProject: vi.fn(), startExploration: vi.fn(),
    listProjectAccounts: vi.fn().mockResolvedValue([]),
  },
  AUTH_STRATEGIES: ['formulaire', 'totp', 'session_injectee', 'aucune'],
  LIBELLE_AUTH_STRATEGIE: { formulaire: 'Formulaire de connexion', totp: 'TOTP', session_injectee: 'Session', aucune: 'Aucune' },
}))
vi.mock('../lib/useProjects', () => ({ useProjects: () => ({ ensureLoaded: vi.fn() }) }))
vi.mock('../lib/useSession', () => ({ useSession: () => ({ session }) }))
vi.mock('../lib/parametresDeTest', () => ({ useParametresDeTest: () => ({ actifs }) }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => route,
  onBeforeRouteLeave: (g: (to: any) => any) => { gardes.push(g) },
  onBeforeRouteUpdate: (g: (to: any) => any) => { gardes.push(g) },
}))

import ProjectsList from '../pages/ProjectsList.vue'
import ProjectTestParameters from '../pages/ProjectTestParameters.vue'

const PROJET = {
  id: 4, name: 'Portail', description: '', connector_type: 'web', connector_version: '', base_url: 'https://app.example',
  database: '', username: 'admin', module_count: 1, case_count: 3, effective_role: 'admin', calibration_writes_enabled: false,
}
const PAS_EXPLORE = { explored: false, running: false, job_id: '', mesure_le: '', pages: 0, transitions: 0, champs: 0, resume: '', error: '' }
const onglet = (nom: string) => ({ props: ['projet', 'peutRegler', 'peutGerer'], emits: ['modifie', 'enregistre'],
  template: `<div data-testid="contenu-${nom}" :data-regler="String(peutRegler)" :data-gerer="String(peutGerer)"><button data-testid="modifier" @click="$emit('modifie', true)">m</button></div>` })
const stubs = {
  Card: true, Icon: true,
  Modal: { props: ['open'], template: '<div v-if="open" data-testid="fenetre"><slot/><slot name="footer"/></div>' },
  Button: { template: '<button type="button"><slot/></button>' },
  RouterLink: { props: ['to'], template: '<a :data-vers="JSON.stringify(to)"><slot/></a>' },
  ConfirmDialog: { props: ['open'], emits: ['confirm', 'cancel'],
                   template: '<div v-if="open" data-testid="confirmation"><button data-testid="quitter" @click="$emit(\'confirm\')">q</button></div>' },
  OngletConfigurations: onglet('configurations'), OngletComptes: onglet('comptes'), OngletEtatDeDepart: onglet('etat-de-depart'),
}

beforeEach(() => {
  vi.clearAllMocks()
  gardes.length = 0
  actifs.value = false
  session.value = { authenticated: true, role: 'admin' }
  route.name = 'admin-projects'
  route.params = {}
  listProjects.mockResolvedValue([PROJET])
  listAdminProjects.mockResolvedValue([PROJET])
  getExploration.mockResolvedValue(PAS_EXPLORE)
  updateProject.mockResolvedValue(PROJET)
})

describe('Page des projets — bouton « Paramètres de test »', () => {
  it('falsifiable : interrupteur éteint, aucun bouton — la page est celle d\'avant', async () => {
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.find('[data-testid="ouvrir-parametres-de-test"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Paramètres de test')
    expect(w.text()).toContain('Identité et application')
  })

  it('interrupteur allumé : le bouton ouvre la page du projet sur son premier onglet', async () => {
    actifs.value = true
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()
    await w.get('[data-testid="ouvrir-parametres-de-test"]').trigger('click')

    expect(push).toHaveBeenCalledWith({ name: 'project-test-params', params: { pid: '4', onglet: 'configurations' } })
    // Les deux boutons d'avant sont toujours là.
    expect(w.text()).toContain('Identité et application')
  })
})

describe('Fenêtre « Identité et application » — organisation allumée (PT-01b)', () => {
  const RUBRIQUES_DEPLACEES = ['navigateur-de-test', 'strategie-connexion', 'comptes-du-projet', 'bac-a-sable']

  async function ouvrirLaFenetre() {
    const boutons = { ...stubs, Button: { template: '<button v-bind="$attrs"><slot/></button>', inheritAttrs: false } }
    const w = mount(ProjectsList, { global: { stubs: boutons } })
    await flushPromises()
    await w.findAll('button').find((b) => b.attributes('title')?.includes('Modifier'))!.trigger('click')
    await flushPromises()
    return w
  }

  it('ne garde que le nom, le connecteur, la version et l’adresse', async () => {
    actifs.value = true
    const fenetre = (await ouvrirLaFenetre()).get('[data-testid="fenetre"]')

    expect(fenetre.findAll('legend').map((l) => l.text())).toEqual(['Identité', 'Application cible'])
    for (const rubrique of RUBRIQUES_DEPLACEES) expect(fenetre.find(`[data-testid="${rubrique}"]`).exists()).toBe(false)
    expect(fenetre.find('input[type="password"]').exists()).toBe(false)
    expect(fenetre.text()).not.toContain('Utilisateur')
  })

  it('falsifiable : n’envoie que ces champs — ni compte, ni navigateur, ni remise à zéro (réglés dans les onglets)', async () => {
    actifs.value = true
    const w = await ouvrirLaFenetre()
    await w.get('#form-edit-project').trigger('submit')
    await flushPromises()

    expect(updateProject).toHaveBeenCalledTimes(1)
    expect(updateProject).toHaveBeenCalledWith(4, {
      name: 'Portail', connector_type: 'web', connector_version: '', base_url: 'https://app.example', database: '' })
  })

  it('organisation éteinte : la fenêtre est celle d’avant, avec toutes ses rubriques', async () => {
    const fenetre = (await ouvrirLaFenetre()).get('[data-testid="fenetre"]')

    for (const rubrique of RUBRIQUES_DEPLACEES) expect(fenetre.find(`[data-testid="${rubrique}"]`).exists()).toBe(true)
    expect(fenetre.find('input[type="password"]').exists()).toBe(true)
  })
})

describe('Page « Paramètres de test » d\'un projet', () => {
  async function ouvrir(params: Record<string, string>) {
    route.name = 'project-test-params'
    route.params = params
    const w = mount(ProjectTestParameters, { global: { stubs } })
    await flushPromises()
    return w
  }

  it('montre le projet et trois onglets, chacun avec sa propre adresse', async () => {
    const w = await ouvrir({ pid: '4', onglet: 'comptes' })

    expect(w.get('[data-testid="nom-du-projet"]').text()).toBe('Portail')
    for (const cle of ['configurations', 'comptes', 'etat-de-depart']) {
      expect(JSON.parse(w.get(`[data-testid="onglet-${cle}"]`).attributes('data-vers')!))
        .toEqual({ name: 'project-test-params', params: { pid: '4', onglet: cle } })
    }
    expect(w.get('[data-testid="onglet-comptes"]').attributes('aria-selected')).toBe('true')
    expect(w.find('[data-testid="contenu-comptes"]').exists()).toBe(true)
    expect(w.find('[data-testid="contenu-configurations"]').exists()).toBe(false)
  })

  it('une adresse sans onglet, ou avec un onglet inconnu, ouvre le premier', async () => {
    expect((await ouvrir({ pid: '4' })).find('[data-testid="contenu-configurations"]').exists()).toBe(true)
    expect((await ouvrir({ pid: '4', onglet: 'inconnu' })).find('[data-testid="contenu-configurations"]').exists()).toBe(true)
  })

  it('un projet inconnu est dit, et aucun onglet n\'est montré', async () => {
    const w = await ouvrir({ pid: '99', onglet: 'comptes' })

    expect(w.get('[role="alert"]').text()).toContain('Projet introuvable')
    expect(w.find('[role="tablist"]').exists()).toBe(false)
  })

  it('le rôle sur le projet décide : un « dev » gère les comptes, il ne règle pas le reste', async () => {
    session.value = { authenticated: true, role: 'testeur' }
    listProjects.mockResolvedValue([{ ...PROJET, effective_role: 'dev' }])

    expect((await ouvrir({ pid: '4', onglet: 'comptes' })).get('[data-testid="contenu-comptes"]').attributes('data-gerer')).toBe('true')
    expect((await ouvrir({ pid: '4', onglet: 'configurations' })).get('[data-testid="contenu-configurations"]').attributes('data-regler')).toBe('false')
    expect(listAdminProjects).not.toHaveBeenCalled()
  })

  it('falsifiable : on ne quitte pas un onglet modifié sans confirmation', async () => {
    const w = await ouvrir({ pid: '4', onglet: 'configurations' })
    // Rien de modifié : la navigation passe.
    expect(gardes.every((g) => g({ fullPath: '/admin/projects' }) === true)).toBe(true)

    await w.get('[data-testid="modifier"]').trigger('click')
    expect(gardes[0]({ fullPath: '/admin/projects' })).toBe(false)
    await flushPromises()
    expect(w.find('[data-testid="confirmation"]').exists()).toBe(true)
    expect(push).not.toHaveBeenCalled()

    await w.get('[data-testid="quitter"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/admin/projects')
    // La sortie confirmée n'est pas redemandée.
    expect(gardes[0]({ fullPath: '/admin/projects' })).toBe(true)
  })
})
