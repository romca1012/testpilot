/**
 * Garde de NON-RÉGRESSION : on doit pouvoir MODIFIER un projet et sa connexion.
 *
 * ⚠️ Pourquoi ce fichier existe. L'écran permettait de créer un projet et de le supprimer — pas
 * de le corriger. Une faute de frappe dans l'URL obligeait à supprimer le projet, donc à perdre
 * ses modules, ses cas et son historique. Côté serveur, `PATCH` acceptait les champs de connexion
 * et les jetait en silence.
 *
 * L'invariant décisif est celui du MOT DE PASSE : l'API ne le renvoie jamais (write-only,
 * décision 0005), donc le champ est toujours raffiché vide. S'il partait tel quel, ouvrir un
 * projet et cliquer « Enregistrer » sans rien changer effacerait le secret — et toutes les
 * exécutions du projet échoueraient ensuite, sans cause visible.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const listProjects = vi.fn()
const updateProject = vi.fn()
const getExploration = vi.fn()
const startExploration = vi.fn()

const PAS_EXPLORE = { explored: false, running: false, job_id: '', mesure_le: '',
                      pages: 0, transitions: 0, champs: 0, resume: '', error: '' }
const EXPLORE = { ...PAS_EXPLORE, explored: true, mesure_le: '2026-07-20',
                  pages: 38, transitions: 37, champs: 120 }

vi.mock('../lib/api', () => ({
  api: {
    listProjects: (...a: any[]) => listProjects(...a),
    listAdminProjects: (...a: any[]) => listProjects(...a),
    updateProject: (...a: any[]) => updateProject(...a),
    createProject: vi.fn(),
    deleteProject: vi.fn(),
    getExploration: (...a: any[]) => getExploration(...a),
    startExploration: (...a: any[]) => startExploration(...a),
  },
}))
vi.mock('../lib/useProjects', () => ({ useProjects: () => ({ ensureLoaded: vi.fn() }) }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  // Ces tests couvrent les opérations techniques, désormais volontairement
  // isolées de la page de sélection des projets.
  useRoute: () => ({ name: 'admin-projects' }),
}))

import ProjectsList from '../pages/ProjectsList.vue'

const PROJET = {
  id: 1, name: 'Portail Sapian', description: '', connector_type: 'odoo',
  base_url: 'http://localhost:10017', database: 'sapian', username: 'admin',
  module_count: 1, case_count: 3,
}

const stubs = { Card: true, Icon: true, ConfirmDialog: true, Button: { template: '<button><slot/></button>' } }

beforeEach(() => {
  vi.clearAllMocks()
  listProjects.mockResolvedValue([PROJET])
  updateProject.mockResolvedValue(PROJET)
  getExploration.mockResolvedValue(PAS_EXPLORE)
  startExploration.mockResolvedValue({ ...PAS_EXPLORE, running: true, job_id: 'J1' })
})

async function ouvrirEdition() {
  const w = mount(ProjectsList, { global: { stubs } })
  await flushPromises()
  const crayon = w.findAll('button').find((b) => b.attributes('title')?.includes('Modifier'))!
  await crayon.trigger('click')
  return w
}

/** Le bouton « Enregistrer » est un composant stubé : on soumet le FORMULAIRE d'édition
 *  (le dernier de la page — celui de la modale), ce que fait un vrai clic. */
async function enregistrer(w: any) {
  const forms = w.findAll('form')
  await forms[forms.length - 1].trigger('submit')
  await flushPromises()
}

describe('ProjectsList — édition d\'un projet et de sa connexion', () => {
  it('affiche la connexion sur la carte du projet', async () => {
    // C'est ce qui distingue deux projets du même connecteur — et ce qu'on vient vérifier
    // quand une exécution tape la mauvaise instance.
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('http://localhost:10017')
  })

  it('signale un projet SANS connexion au lieu de le laisser paraître prêt', async () => {
    listProjects.mockResolvedValue([{ ...PROJET, base_url: '' }])
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('Aucune connexion configurée')
  })

  it('pré-remplit le formulaire avec la connexion, mot de passe TOUJOURS vide', async () => {
    const w = await ouvrirEdition()

    const valeurs = w.findAll('input').map((i) => (i.element as HTMLInputElement).value)
    expect(valeurs).toContain('http://localhost:10017')
    expect(valeurs).toContain('sapian')
    const mdp = w.find('input[type="password"]').element as HTMLInputElement
    expect(mdp.value).toBe('')
  })

  it('N\'ENVOIE PAS le mot de passe quand il n\'a pas été saisi', async () => {
    // ⚠️ L'invariant vital : sans ce filtrage, enregistrer sans rien changer efface le secret.
    const w = await ouvrirEdition()
    await enregistrer(w)

    expect(updateProject).toHaveBeenCalled()
    const patch = updateProject.mock.calls[0][1]
    expect(patch).not.toHaveProperty('password')
    expect(patch.base_url).toBe('http://localhost:10017')
  })

  it('envoie le mot de passe quand il EST saisi', async () => {
    const w = await ouvrirEdition()
    await w.find('input[type="password"]').setValue('nouveau-secret')
    await enregistrer(w)

    expect(updateProject.mock.calls[0][1].password).toBe('nouveau-secret')
  })

  it('transmet une URL corrigée', async () => {
    const w = await ouvrirEdition()
    const url = w.findAll('input').find(
      (i) => (i.element as HTMLInputElement).value === 'http://localhost:10017')!
    await url.setValue('http://localhost:9999')
    await enregistrer(w)

    expect(updateProject.mock.calls[0][1].base_url).toBe('http://localhost:9999')
  })
})

// ── Version DÉCLARÉE du connecteur (migration 38) ──────────────────────────────
// Distincte du connecteur lui-même (ex. Odoo 17 vs Odoo 19) : un projet peut la déclarer, ou la
// laisser vide si l'application ne l'expose pas — jamais un champ à l'air obligatoire.
describe('ProjectsList — version déclarée du connecteur', () => {
  it("n'affiche rien de plus sur la carte quand la version est absente", async () => {
    // '' = indéterminée : ne rien afficher, jamais une valeur inventée du type « v? ».
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('odoo · http://localhost:10017')
  })

  it('affiche la version sur la carte quand elle est déclarée', async () => {
    listProjects.mockResolvedValue([{ ...PROJET, connector_version: '17' }])
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('odoo 17 · http://localhost:10017')
  })

  it('pré-remplit le formulaire d\'édition avec la version déclarée', async () => {
    listProjects.mockResolvedValue([{ ...PROJET, connector_version: '17' }])
    const w = await ouvrirEdition()

    const valeurs = w.findAll('input').map((i) => (i.element as HTMLInputElement).value)
    expect(valeurs).toContain('17')
  })

  it('transmet la version modifiée', async () => {
    const w = await ouvrirEdition()
    const champVersion = w.findAll('input').find(
      (i) => i.attributes('placeholder') === 'ex. 17')!
    await champVersion.setValue('19')
    await enregistrer(w)

    expect(updateProject.mock.calls[0][1].connector_version).toBe('19')
  })

  it('reste facultative : le formulaire se soumet vide sans erreur', async () => {
    // Aucune contrainte de remplissage — l'API accepte explicitement une chaîne vide.
    const w = await ouvrirEdition()
    await enregistrer(w)

    expect(updateProject).toHaveBeenCalled()
    expect(updateProject.mock.calls[0][1].connector_version).toBe('')
  })
})

describe("ProjectsList — exploration de l'application (étape 2 du flux)", () => {
  it("dit clairement qu'une application n'est PAS explorée", async () => {
    // Laisser la carte muette ferait croire que la génération sait où elle va.
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('Application non explorée')
  })

  it('affiche la couverture ET LA DATE quand la carto existe', async () => {
    // La cartographie est une PHOTO : sans sa date, impossible de savoir si elle vaut encore.
    getExploration.mockResolvedValue(EXPLORE)
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('38 routes')
    expect(w.text()).toContain('37 transitions')
    expect(w.text()).toContain('2026-07-20')
  })

  it('affiche les RÈGLES DE SAISIE mesurées', async () => {
    // ⚠️ Le 2026-07-21, une ré-exploration lancée depuis cet écran a réécrit la cartographie À
    // L'IDENTIQUE — code de crawl périmé encore chargé en mémoire — en affichant « terminée ».
    // Mêmes routes, mêmes champs : RIEN à l'écran ne pouvait le trahir. Les règles de saisie sont
    // le seul compteur qui distingue une mesure fraîche d'une mesure périmée.
    getExploration.mockResolvedValue({ ...EXPLORE, contraintes: 36 })
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('36 règles de saisie')
  })

  it("N'AFFICHE PAS un compteur de règles à zéro", async () => {
    // « 0 règles de saisie » se lirait comme « ce portail n'en a pas », alors que ça veut dire
    // « on ne les a pas mesurées ». Mieux vaut se taire que d'affirmer une absence non vérifiée.
    getExploration.mockResolvedValue({ ...EXPLORE, contraintes: 0 })
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).not.toContain('règles de saisie')
  })

  it('affiche les MODÈLES BACK-OFFICE découverts (Odoo, énumération de menus)', async () => {
    // Sans ce compteur, rien à l'écran ne dit si `discover_menus` a effectivement tourné sur
    // cette mesure — le seul moyen de le savoir était de lire le fichier domain/…json à la main
    // (mesuré : projet Sapian, 149 modèles trouvés, 2026-09-18).
    getExploration.mockResolvedValue({ ...EXPLORE, modeles_backoffice: 149 })
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).toContain('149 modèles back-office')
  })

  it("N'AFFICHE PAS un compteur de modèles back-office à zéro", async () => {
    getExploration.mockResolvedValue({ ...EXPLORE, modeles_backoffice: 0 })
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    expect(w.text()).not.toContain('modèles back-office')
  })

  it("DÉSACTIVE le bouton tant qu'aucune connexion n'est saisie", async () => {
    // « Affiché ≠ réel » : ne jamais proposer une action que le serveur refusera (422).
    listProjects.mockResolvedValue([{ ...PROJET, base_url: '' }])
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    const btn = w.findAll('button').find((b) => b.text() === 'Explorer')!
    expect(btn.attributes('disabled')).toBeDefined()
  })

  it("lance réellement l'exploration au clic", async () => {
    const w = mount(ProjectsList, { global: { stubs } })
    await flushPromises()

    await w.findAll('button').find((b) => b.text() === 'Explorer')!.trigger('click')
    await flushPromises()

    expect(startExploration).toHaveBeenCalledWith(1)
  })
})
