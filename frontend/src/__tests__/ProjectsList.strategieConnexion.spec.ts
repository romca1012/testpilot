/**
 * Lot 07b-2 (C2) — l'écran de la stratégie de connexion du compte principal.
 *
 * Deux invariants décisifs :
 * 1. `totp_secret`/`injected_session` sont en ÉCRITURE SEULE : jamais réaffichés, et une édition sans nouvelle valeur ne les
 *    envoie pas (les envoyer vides les effacerait) ;
 * 2. réservé au connecteur `web` — Odoo se connecte par sa propre session RPC, ce réglage n'a rien à y faire.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listProjects = vi.fn()
const updateProject = vi.fn()
const getExploration = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listProjects: (...a: any[]) => listProjects(...a),
    listAdminProjects: (...a: any[]) => listProjects(...a),
    updateProject: (...a: any[]) => updateProject(...a),
    createProject: vi.fn(), deleteProject: vi.fn(),
    getExploration: (...a: any[]) => getExploration(...a), startExploration: vi.fn(),
    listProjectAccounts: vi.fn().mockResolvedValue([]),
    createProjectAccount: vi.fn(), updateProjectAccount: vi.fn(), deleteProjectAccount: vi.fn(),
  },
  AUTH_STRATEGIES: ['formulaire', 'totp', 'session_injectee', 'aucune'],
  LIBELLE_AUTH_STRATEGIE: { formulaire: 'Formulaire de connexion', totp: 'Code à usage unique (TOTP)',
                           session_injectee: 'Session déjà ouverte (jeton fourni)', aucune: 'Aucune connexion' },
}))
vi.mock('../lib/useProjects', () => ({ useProjects: () => ({ ensureLoaded: vi.fn() }) }))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), useRoute: () => ({ name: 'admin-projects' }) }))

import ProjectsList from '../pages/ProjectsList.vue'

const SECRET_TOTP = 'JBSWY3DPEHPK3PXP'
const projet = (connector_type: string, extra: Record<string, unknown> = {}) => ({
  id: 1, name: 'Portail', description: '', connector_type, base_url: 'https://app.example', database: '', username: 'admin',
  module_count: 1, case_count: 3, auth_strategie: 'formulaire', has_totp_secret: false, has_injected_session: false, ...extra,
})
const stubs = { Card: true, Icon: true, ConfirmDialog: true, Button: { template: '<button type="button"><slot/></button>' } }

async function ouvrir(p: ReturnType<typeof projet>) {
  listProjects.mockResolvedValue([p])
  const w = mount(ProjectsList, { global: { stubs } })
  await flushPromises()
  await w.findAll('button').find((b) => b.attributes('title')?.includes('Modifier'))!.trigger('click')
  await flushPromises()
  return w
}

const PAS_EXPLORE = { explored: false, running: false, job_id: '', mesure_le: '', pages: 0, transitions: 0, champs: 0, resume: '', error: '' }

beforeEach(() => {
  vi.clearAllMocks()
  getExploration.mockResolvedValue(PAS_EXPLORE)
  updateProject.mockResolvedValue(projet('web'))
})

describe('ProjectsList — stratégie de connexion du compte principal', () => {
  it('réservée au connecteur web : absente pour un projet Odoo', async () => {
    const w = await ouvrir(projet('odoo'))
    expect(w.find('[data-testid="strategie-connexion"]').exists()).toBe(false)
  })

  it('propose les quatre stratégies avec un libellé français, jamais la valeur brute', async () => {
    const w = await ouvrir(projet('web'))
    const options = w.find('[data-testid="auth-strategie"]').findAll('option')
    expect(options.map((o) => o.text())).toEqual([
      'Formulaire de connexion', 'Code à usage unique (TOTP)', 'Session déjà ouverte (jeton fourni)', 'Aucune connexion'])
  })

  it('affiche le champ secret TOTP seulement quand cette stratégie est choisie', async () => {
    const w = await ouvrir(projet('web', { auth_strategie: 'totp' }))
    expect(w.find('[data-testid="totp-secret"]').exists()).toBe(true)
    expect(w.find('[data-testid="injected-session"]').exists()).toBe(false)
  })

  it('affiche le champ de session fournie seulement pour session_injectee', async () => {
    const w = await ouvrir(projet('web', { auth_strategie: 'session_injectee' }))
    expect(w.find('[data-testid="injected-session"]').exists()).toBe(true)
    expect(w.find('[data-testid="totp-secret"]').exists()).toBe(false)
  })

  it('un secret déjà enregistré n\'est JAMAIS réaffiché', async () => {
    const w = await ouvrir(projet('web', { auth_strategie: 'totp', has_totp_secret: true }))
    expect((w.find('[data-testid="totp-secret"]').element as HTMLInputElement).value).toBe('')
    expect(w.html()).not.toContain(SECRET_TOTP)
  })

  it('FALSIFIABLE : enregistrer sans toucher au secret ne l\'envoie pas (l\'envoyer vide l\'effacerait)', async () => {
    const w = await ouvrir(projet('web', { auth_strategie: 'totp', has_totp_secret: true }))
    await w.find('form').trigger('submit')
    await flushPromises()

    const patch = updateProject.mock.calls[0][1]
    expect(patch.auth_strategie).toBe('totp')
    expect('totp_secret' in patch).toBe(false)
  })

  it('envoie le secret TOTP quand il est saisi', async () => {
    const w = await ouvrir(projet('web', { auth_strategie: 'totp' }))
    await w.find('[data-testid="totp-secret"]').setValue(SECRET_TOTP)
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(updateProject.mock.calls[0][1].totp_secret).toBe(SECRET_TOTP)
  })

  it('change de stratégie et l\'envoie', async () => {
    const w = await ouvrir(projet('web'))
    await w.find('[data-testid="auth-strategie"]').setValue('aucune')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(updateProject.mock.calls[0][1].auth_strategie).toBe('aucune')
  })
})
