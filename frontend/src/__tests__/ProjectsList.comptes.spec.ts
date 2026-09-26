/**
 * Lot 07b-1 (D8) — les comptes de test d'un projet, côté écran.
 *
 * Deux invariants décisifs :
 * 1. le mot de passe d'un compte est en ÉCRITURE SEULE : jamais réaffiché, et une édition sans nouveau mot de passe ne l'envoie pas
 *    (l'envoyer vide l'effacerait) ;
 * 2. seuls `admin` et `dev` voient les gestes de création / modification / suppression (le serveur tranche aussi).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listProjects = vi.fn()
const listProjectAccounts = vi.fn()
const createProjectAccount = vi.fn()
const updateProjectAccount = vi.fn()
const deleteProjectAccount = vi.fn()
const getExploration = vi.fn()

const PAS_EXPLORE = { explored: false, running: false, job_id: '', mesure_le: '', pages: 0, transitions: 0, champs: 0, resume: '', error: '' }

vi.mock('../lib/api', () => ({
  api: {
    listProjects: (...a: any[]) => listProjects(...a),
    listAdminProjects: (...a: any[]) => listProjects(...a),
    updateProject: vi.fn(),
    createProject: vi.fn(),
    deleteProject: vi.fn(),
    getExploration: (...a: any[]) => getExploration(...a),
    startExploration: vi.fn(),
    listProjectAccounts: (...a: any[]) => listProjectAccounts(...a),
    createProjectAccount: (...a: any[]) => createProjectAccount(...a),
    updateProjectAccount: (...a: any[]) => updateProjectAccount(...a),
    deleteProjectAccount: (...a: any[]) => deleteProjectAccount(...a),
  },
}))
vi.mock('../lib/useProjects', () => ({ useProjects: () => ({ ensureLoaded: vi.fn() }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ name: 'admin-projects' }) }))

import ProjectsList from '../pages/ProjectsList.vue'

const SECRET = 'S3cret-Commercial-9f2c'
const projet = (role: string) => ({
  id: 1, name: 'Portail', description: '', connector_type: 'web', base_url: 'https://app.example', database: '', username: 'admin',
  module_count: 1, case_count: 3, effective_role: role,
})
const COMPTES = [
  { id: null, label: 'principal', username: 'admin', business_role: '', has_secret: true, principal: true },
  { id: 7, label: 'Commercial', username: 'banc_commercial', business_role: 'Vendeur', has_secret: true, principal: false },
]
const stubs = { Card: true, Icon: true, ConfirmDialog: true, Button: { template: '<button type="button"><slot/></button>' } }

async function ouvrir(role: string) {
  listProjects.mockResolvedValue([projet(role)])
  const w = mount(ProjectsList, { global: { stubs } })
  await flushPromises()
  await w.findAll('button').find((b) => b.attributes('title')?.includes('Modifier'))!.trigger('click')
  await flushPromises()
  return w
}

beforeEach(() => {
  vi.clearAllMocks()
  getExploration.mockResolvedValue(PAS_EXPLORE)
  listProjectAccounts.mockResolvedValue(COMPTES)
  createProjectAccount.mockResolvedValue({ ...COMPTES[1], id: 8 })
  updateProjectAccount.mockResolvedValue(COMPTES[1])
  deleteProjectAccount.mockResolvedValue(undefined)
})

describe('ProjectsList — comptes de test du projet', () => {
  it('liste le compte principal puis les comptes secondaires, sans jamais afficher un secret', async () => {
    const w = await ouvrir('admin')
    const lignes = w.findAll('[data-testid="compte-ligne"]')

    expect(lignes).toHaveLength(2)
    expect(lignes[0].text()).toContain('principal')
    expect(lignes[0].text()).toContain('compte de la connexion du projet')
    expect(lignes[1].text()).toContain('Commercial')
    expect(lignes[1].text()).toContain('Vendeur')
    expect(lignes[1].text()).toContain('mot de passe enregistré')
    expect(w.html()).not.toContain(SECRET)
  })

  it('crée un compte, puis vide le formulaire : le mot de passe saisi ne reste ni à l\'écran ni dans le champ', async () => {
    const w = await ouvrir('admin')
    await w.find('[data-testid="compte-ajouter"]').trigger('click')
    await w.find('[data-testid="compte-libelle"]').setValue('Responsable')
    await w.find('[data-testid="compte-identifiant"]').setValue('banc_resp')
    await w.find('[data-testid="compte-mot-de-passe"]').setValue(SECRET)

    await w.find('[data-testid="compte-enregistrer"]').trigger('click')
    await flushPromises()

    expect(createProjectAccount).toHaveBeenCalledWith(1, { label: 'Responsable', username: 'banc_resp', password: SECRET, business_role: '' })
    expect(w.find('[data-testid="compte-formulaire"]').exists()).toBe(false)
    expect(w.html()).not.toContain(SECRET)
  })

  it('FALSIFIABLE : modifier un compte sans saisir de mot de passe n\'envoie PAS le champ (l\'envoyer effacerait le secret)', async () => {
    const w = await ouvrir('admin')
    const boutonModifier = w.findAll('[data-testid="compte-ligne"]')[1].findAll('button').find((b) => b.text() === 'Modifier')!
    await boutonModifier.trigger('click')
    expect((w.find('[data-testid="compte-mot-de-passe"]').element as HTMLInputElement).value).toBe('')
    await w.find('[data-testid="compte-identifiant"]').setValue('banc_commercial2')

    await w.find('[data-testid="compte-enregistrer"]').trigger('click')
    await flushPromises()

    expect(updateProjectAccount).toHaveBeenCalledTimes(1)
    const patch = updateProjectAccount.mock.calls[0][2]
    expect(patch).toEqual({ label: 'Commercial', username: 'banc_commercial2', business_role: 'Vendeur' })
    expect('password' in patch).toBe(false)
  })

  it('envoie le mot de passe quand il est saisi', async () => {
    const w = await ouvrir('admin')
    await w.findAll('[data-testid="compte-ligne"]')[1].findAll('button').find((b) => b.text() === 'Modifier')!.trigger('click')
    await w.find('[data-testid="compte-mot-de-passe"]').setValue(SECRET)

    await w.find('[data-testid="compte-enregistrer"]').trigger('click')
    await flushPromises()

    expect(updateProjectAccount.mock.calls[0][2].password).toBe(SECRET)
  })

  it('supprime un compte secondaire, jamais le principal (qui n\'a pas de bouton)', async () => {
    const w = await ouvrir('admin')
    const lignes = w.findAll('[data-testid="compte-ligne"]')

    expect(lignes[0].findAll('button')).toHaveLength(0)
    await lignes[1].findAll('button').find((b) => b.text() === 'Supprimer')!.trigger('click')
    await flushPromises()

    expect(deleteProjectAccount).toHaveBeenCalledWith(1, 7)
  })

  it('un dev gère les comptes', async () => {
    const w = await ouvrir('dev')
    expect(w.find('[data-testid="compte-ajouter"]').exists()).toBe(true)
  })

  it.each(['testeur', 'lecture_seule'])('FALSIFIABLE : un %s voit les libellés mais aucun geste de gestion', async (role) => {
    const w = await ouvrir(role)

    expect(w.findAll('[data-testid="compte-ligne"]')).toHaveLength(2)
    expect(w.find('[data-testid="compte-ajouter"]').exists()).toBe(false)
    expect(w.findAll('[data-testid="compte-ligne"]')[1].findAll('button')).toHaveLength(0)
  })

  it('affiche l\'erreur du serveur (libellé en double, réservé…) au lieu de l\'avaler', async () => {
    createProjectAccount.mockRejectedValue(new Error('un compte « Commercial » existe déjà sur ce projet'))
    const w = await ouvrir('admin')
    await w.find('[data-testid="compte-ajouter"]').trigger('click')
    await w.find('[data-testid="compte-libelle"]').setValue('commercial')
    await w.find('[data-testid="compte-identifiant"]').setValue('x')

    await w.find('[data-testid="compte-enregistrer"]').trigger('click')
    await flushPromises()

    expect(w.find('[data-testid="compte-erreur"]').text()).toContain('existe déjà')
    expect(w.find('[data-testid="compte-formulaire"]').exists()).toBe(true)
  })
})
