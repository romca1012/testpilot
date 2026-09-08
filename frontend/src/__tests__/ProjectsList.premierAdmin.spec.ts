/**
 * Garde de NON-RÉGRESSION : un Admin sur une instance SANS AUCUN projet (ex. tout premier
 * démarrage, juste après la connexion) doit pouvoir créer son premier projet DIRECTEMENT sur
 * cette page — jamais un aiguillage vers un second écran. C'est le modèle TestRail : le bouton
 * « Add Project » vit sur LA page projets pour un compte Administrator, qu'il y ait déjà des
 * projets ou non (audit déploiement Scaleway, 2026-09-08 — constaté en conditions réelles sur le
 * tout premier compte d'une instance neuve, qui ne voyait que « contactez un administrateur »).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listProjects = vi.fn()
const createProject = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listProjects: (...a: any[]) => listProjects(...a),
    listAdminProjects: (...a: any[]) => listProjects(...a),
    createProject: (...a: any[]) => createProject(...a),
    getExploration: vi.fn(),
  },
}))
vi.mock('../lib/useProjects', () => ({ useProjects: () => ({ ensureLoaded: vi.fn() }) }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  // Page « Projets » ordinaire (PAS admin-projects) — celle que tout compte, admin compris,
  // voit juste après connexion.
  useRoute: () => ({ name: 'projects' }),
}))

const stubs = { Icon: true, ConfirmDialog: true, Button: { template: '<button><slot/></button>' } }

beforeEach(() => {
  vi.clearAllMocks()
  // ⚠️ Chaque test mocke `useSession` avec un rôle DIFFÉRENT via `vi.doMock` + import
  // dynamique — sans ce reset, le module (et son `useSession` déjà résolu) reste celui mis en
  // cache par le test précédent, et le rôle du premier test « fuit » silencieusement vers les
  // suivants (constaté : le test non-admin voyait encore le bouton de création de l'Admin).
  vi.resetModules()
  listProjects.mockResolvedValue([])
  createProject.mockResolvedValue({ id: 7, name: 'Portail Sapian' })
})

describe('ProjectsList — instance sans aucun projet, vue par un Admin', () => {
  it('propose de créer directement ici, jamais « contactez un administrateur »', async () => {
    vi.doMock('../lib/useSession', () => ({
      useSession: () => ({ session: { value: { authenticated: true, role: 'admin', name: 'Admin' } } }),
    }))
    const { default: ProjectsList } = await import('../pages/ProjectsList.vue')
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).not.toContain('Contactez un administrateur')
    const bouton = w.findAll('button').find((b) => b.text().includes('Créer le premier projet'))
    expect(bouton).toBeTruthy()

    await bouton!.trigger('click')
    // La modale de création s'ouvre SUR PLACE — aucune navigation vers un autre écran.
    expect(w.text()).toContain('Nom de l\'application')
    expect(push).not.toHaveBeenCalled()
  })

  it('crée bien le projet et rejoint sa page de cas', async () => {
    vi.doMock('../lib/useSession', () => ({
      useSession: () => ({ session: { value: { authenticated: true, role: 'admin', name: 'Admin' } } }),
    }))
    const { default: ProjectsList } = await import('../pages/ProjectsList.vue')
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    await w.findAll('button').find((b) => b.text().includes('Créer le premier projet'))!.trigger('click')
    await w.find('input[placeholder="ex. Portail Sapian"]').setValue('Portail Sapian')
    await w.find('#form-create-project').trigger('submit')
    await flushPromises()

    expect(createProject).toHaveBeenCalled()
    expect(push).toHaveBeenCalledWith('/projects/7/cases')
  })

  it('garde le message habituel pour un rôle non-admin (aucun accès à créer)', async () => {
    vi.doMock('../lib/useSession', () => ({
      useSession: () => ({ session: { value: { authenticated: true, role: 'testeur', name: 'Awa' } } }),
    }))
    const { default: ProjectsList } = await import('../pages/ProjectsList.vue')
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('Contactez un administrateur')
    expect(w.findAll('button').find((b) => b.text().includes('Créer'))).toBeFalsy()
  })
})
