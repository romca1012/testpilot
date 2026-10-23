/**
 * Lot VH-07 (décision D26) — le réglage « bac à sable » d'un projet.
 *
 * Deux invariants décisifs :
 * 1. ÉTEINT par défaut et jamais posé implicitement : sans la case cochée ET une adresse de remise à zéro, l'IA ne joue aucune
 *    action pendant la génération — l'écran n'envoie que ce que le porteur a déclaré ;
 * 2. réservé au connecteur `web` (première version : Odoo n'a pas de remise à zéro) ; un refus du serveur (adresse d'une autre
 *    application) reste visible, la fenêtre ne se ferme pas comme si c'était enregistré.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listProjects = vi.fn()
const updateProject = vi.fn()
const getExploration = vi.fn()

// Porteur, 2026-10-23 : l'organisation « Paramètres de test » est toujours active ; ces rubriques de la fenêtre du projet
// n'y sont plus affichées (elles vivent dans les onglets, testés par ParametresDeTest.*.spec.ts). Ce fichier garde la preuve
// de l'ancien écran tant que son code n'est pas retiré : il le monte explicitement « organisation éteinte ».
vi.mock('../lib/parametresDeTest', async (orig) => {
  const { ref } = await import('vue')
  return {
    ...(await orig<typeof import('../lib/parametresDeTest')>()),
    useParametresDeTest: () => ({ actifs: ref(false), connu: ref(true) }),
  }
})
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

const projet = (connector_type: string, extra: Record<string, unknown> = {}) => ({
  id: 1, name: 'Boutique', description: '', connector_type, base_url: 'https://recette.example', database: '', username: 'admin',
  module_count: 1, case_count: 3, auth_strategie: 'formulaire', has_totp_secret: false, has_injected_session: false,
  calibration_writes_enabled: false, bac_a_sable_reset: '', ...extra,
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

describe('ProjectsList — bac à sable de génération (D26)', () => {
  it('réservé au connecteur web : absent pour un projet Odoo', async () => {
    const w = await ouvrir(projet('odoo'))
    expect(w.find('[data-testid="bac-a-sable"]').exists()).toBe(false)
  })

  it('FALSIFIABLE : éteint par défaut — rien n\'est déclaré tant que le porteur ne le fait pas', async () => {
    const w = await ouvrir(projet('web'))
    expect((w.find('[data-testid="bac-a-sable-autorise"]').element as HTMLInputElement).checked).toBe(false)
    expect((w.find('[data-testid="bac-a-sable-reset"]').element as HTMLInputElement).value).toBe('')

    await w.find('form').trigger('submit')
    await flushPromises()

    const patch = updateProject.mock.calls[0][1]
    expect(patch.calibration_writes_enabled).toBe(false)
    expect(patch.bac_a_sable_reset).toBe('')
  })

  it('dit en clair ce que le réglage autorise et à quelle condition', async () => {
    const w = await ouvrir(projet('web'))
    const texte = w.find('[data-testid="bac-a-sable"]').text()
    expect(texte).toContain('https://recette.example')
    expect(texte).toContain('environnement de test')
    expect(texte).toContain('remettre à zéro')
    expect(texte).toContain('Sans cette adresse, l\'IA ne joue aucune action')
  })

  it('envoie la déclaration du porteur : autorisation et adresse de remise à zéro', async () => {
    const w = await ouvrir(projet('web'))
    await w.find('[data-testid="bac-a-sable-autorise"]').setValue(true)
    await w.find('[data-testid="bac-a-sable-reset"]').setValue('/reset')
    await w.find('form').trigger('submit')
    await flushPromises()

    const patch = updateProject.mock.calls[0][1]
    expect(patch.calibration_writes_enabled).toBe(true)
    expect(patch.bac_a_sable_reset).toBe('/reset')
  })

  it('réaffiche la déclaration enregistrée, et la retire quand l\'adresse est vidée', async () => {
    const w = await ouvrir(projet('web', { calibration_writes_enabled: true, bac_a_sable_reset: '/reset' }))
    expect((w.find('[data-testid="bac-a-sable-autorise"]').element as HTMLInputElement).checked).toBe(true)
    expect((w.find('[data-testid="bac-a-sable-reset"]').element as HTMLInputElement).value).toBe('/reset')

    await w.find('[data-testid="bac-a-sable-reset"]').setValue('')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(updateProject.mock.calls[0][1].bac_a_sable_reset).toBe('')
  })

  it('FALSIFIABLE : un refus du serveur reste à l\'écran, la fenêtre ne se ferme pas', async () => {
    updateProject.mockRejectedValue(new Error('adresse de remise à zéro refusée : « http://autre.example/reset » n\'est pas une adresse de l\'application du projet'))
    const w = await ouvrir(projet('web'))
    await w.find('[data-testid="bac-a-sable-reset"]').setValue('http://autre.example/reset')
    await w.find('form').trigger('submit')
    await flushPromises()

    expect(w.text()).toContain('adresse de remise à zéro refusée')
    expect(w.find('[data-testid="bac-a-sable"]').exists()).toBe(true)
  })

  it('sans marque, aucun avertissement', async () => {
    const w = await ouvrir(projet('web'))
    expect(w.find('[data-testid="bac-a-sable-non-remis"]').exists()).toBe(false)
  })

  it('FALSIFIABLE : une application laissée par un essai est signalée, et le porteur déclare l\'avoir remise à zéro', async () => {
    updateProject.mockResolvedValue(projet('web', { bac_a_sable_non_remis: false }))
    const w = await ouvrir(projet('web', { calibration_writes_enabled: true, bac_a_sable_reset: 'https://recette.example/reset',
                                         bac_a_sable_non_remis: true }))
    const alerte = w.find('[data-testid="bac-a-sable-non-remis"]')
    expect(alerte.exists()).toBe(true)
    expect(alerte.text()).toContain('les exécutions de ce projet sont retenues')

    await w.find('[data-testid="bac-a-sable-declarer-remis"]').trigger('click')
    await flushPromises()

    expect(updateProject.mock.calls[0][1]).toEqual({ bac_a_sable_remis_a_zero: true })
    expect(w.find('[data-testid="bac-a-sable-non-remis"]').exists()).toBe(false)
  })
})
