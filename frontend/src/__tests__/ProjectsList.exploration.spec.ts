/**
 * Étape 4, morceau 6 (A69 révisée, A77-A83 — porteur, 2026-10-21) : ce que l'écran du projet dit de l'exploration.
 * - pendant : la progression (« 142 pages vues · compte 2 sur 3 (Lecteur) »), l'attente des tests en cours, et « Arrêter » ;
 * - après : une exploration arrêtée est « incomplète », jamais présentée comme complète ;
 * - par compte : combien sont explorés, lesquels ont échoué (et pourquoi), lesquels sont à actualiser ;
 * - un projet sans autre compte que le principal garde l'affichage d'avant.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listProjects = vi.fn()
const getExploration = vi.fn()
const stopExploration = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listProjects: (...a: any[]) => listProjects(...a),
    listAdminProjects: (...a: any[]) => listProjects(...a),
    updateProject: vi.fn(), createProject: vi.fn(), deleteProject: vi.fn(),
    getExploration: (...a: any[]) => getExploration(...a), startExploration: vi.fn(),
    stopExploration: (...a: any[]) => stopExploration(...a),
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

const PROJET = {
  id: 1, name: 'Boutique', description: '', connector_type: 'web', base_url: 'https://recette.example', database: '',
  username: 'admin', module_count: 1, case_count: 3, auth_strategie: 'formulaire', has_totp_secret: false,
  has_injected_session: false, calibration_writes_enabled: false, bac_a_sable_reset: '',
}
const stubs = { Card: true, Icon: true, ConfirmDialog: true, RouterLink: { template: '<a><slot/></a>' },
                Button: { template: '<button type="button"><slot/></button>' } }
const EXPLORE = { explored: true, running: false, job_id: '', mesure_le: '2026-10-21', pages: 12, transitions: 30, champs: 40,
                  contraintes: 0, modeles_backoffice: 0, resume: '', error: '' }

async function ecran(etat: any) {
  listProjects.mockResolvedValue([PROJET])
  getExploration.mockResolvedValue(etat)
  const w = mount(ProjectsList, { global: { stubs } })
  await flushPromises()
  return w
}
const texte = (w: any, id: string) => w.get(`[data-testid="${id}"]`).text().replace(/\s+/g, ' ')

beforeEach(() => { vi.clearAllMocks() })

describe('ProjectsList — exploration de l’application (étape 4, morceau 6)', () => {
  it('un projet sans autre compte garde l’affichage d’avant', async () => {
    const w = await ecran({ ...EXPLORE, comptes_total: 0, comptes: [] })
    expect(w.find('[data-testid="exploration-comptes"]').exists()).toBe(false)
    expect(w.find('[data-testid="exploration-incomplete"]').exists()).toBe(false)
    expect(w.text()).toContain('12 routes')
  })

  it('dit combien de comptes sont explorés, lesquels ont échoué et lesquels sont à actualiser', async () => {
    const w = await ecran({ ...EXPLORE, comptes_total: 3, comptes: [
      { id: 4, libelle: 'Lecteur', statut: 'echec', message: 'connexion impossible : l’écran de connexion est resté affiché — vérifiez son mot de passe' },
      { id: 5, libelle: 'Comptable', statut: 'explore', message: '' },
      { id: 6, libelle: 'Stagiaire', statut: 'a_actualiser', message: 'pas encore exploré' },
    ] })
    expect(texte(w, 'exploration-comptes')).toBe('· 1 compte exploré sur 3')
    expect(texte(w, 'exploration-compte-echec')).toContain('Lecteur : connexion impossible')
    expect(texte(w, 'exploration-a-actualiser')).toBe('À actualiser : Stagiaire (pas encore exploré)')
  })

  it('FALSIFIABLE (revue) : un compte arrêté en route n’est jamais compté comme exploré', async () => {
    const w = await ecran({ ...EXPLORE, comptes_total: 1, comptes: [
      { id: 4, libelle: 'Lecteur', statut: 'incomplet', message: 'exploration incomplète (arrêtée)' }] })
    expect(texte(w, 'exploration-comptes')).toBe('· 0 compte exploré sur 1')
    expect(texte(w, 'exploration-compte-echec')).toBe('Lecteur : exploration incomplète (arrêtée)')
  })

  it('A84 : une exploration arrêtée qui a gardé la carte précédente le dit, avec les deux dates', async () => {
    const w = await ecran({ ...EXPLORE, mesure_le: '2026-10-14',
                            derniere_tentative: { le: '2026-10-21', raison: 'arrêtée', pages: 40, carte_gardee_du: '2026-10-14' } })
    expect(texte(w, 'exploration-tentative'))
      .toBe('Dernière exploration arrêtée le 2026-10-21 à 40 pages — la carte du 2026-10-14 est gardée')
    expect(w.find('[data-testid="exploration-incomplete"]').exists()).toBe(false)   // la carte affichée, elle, est complète
    const session = await ecran({ ...EXPLORE, derniere_tentative: { le: '2026-10-21', raison: 'session perdue en cours de route',
                                                                    pages: 40, carte_gardee_du: '2026-10-14' } })
    expect(texte(session, 'exploration-tentative'))
      .toBe('Dernière exploration dont la session s\'est perdue le 2026-10-21 à 40 pages — la carte du 2026-10-14 est gardée')
  })

  it('FALSIFIABLE : une exploration arrêtée est dite incomplète', async () => {
    const w = await ecran({ ...EXPLORE, incomplete: 'arrêtée', incomplete_pages: 142 })
    expect(texte(w, 'exploration-incomplete')).toBe('· incomplète (arrêtée à 142 pages)')
  })

  it('pendant l’exploration : la progression, puis « Arrêter » à la place d’« Actualiser »', async () => {
    stopExploration.mockResolvedValue({ ...EXPLORE, running: true, arret_demande: true,
                                        progression: { rang: 2, total: 3, libelle: 'Lecteur', pages: 142 } })
    const w = await ecran({ ...EXPLORE, running: true, progression: { rang: 2, total: 3, libelle: 'Lecteur', pages: 142 } })
    expect(texte(w, 'exploration-en-cours')).toBe('Exploration en cours… 142 pages vues · compte 2 sur 3 (Lecteur)')
    const arreter = w.findAll('button').find((b: any) => b.text() === 'Arrêter')!
    expect(w.findAll('button').some((b: any) => b.text() === 'Actualiser')).toBe(false)
    await arreter.trigger('click')
    await flushPromises()
    expect(stopExploration).toHaveBeenCalledWith(1)
    expect(texte(w, 'exploration-en-cours')).toContain('— arrêt demandé')
  })

  it('dit quand l’exploration attend la fin des tests en cours (A77)', async () => {
    const w = await ecran({ ...EXPLORE, running: true, progression: { rang: 1, total: 1, libelle: 'principal', pages: 0, attente: true } })
    expect(texte(w, 'exploration-en-cours')).toBe('En attente de la fin des tests en cours sur l\'application…')
  })
})
