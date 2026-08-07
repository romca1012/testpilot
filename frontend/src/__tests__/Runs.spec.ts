/**
 * Écrans RUN (campagne) — décision 0022 n°8.
 *
 * Ce que ces tests gardent :
 * - créer un run n'envoie PAS de sélection figée en mode « tous les cas » (sélection vivante) ;
 * - la sélection figée exige au moins un cas coché (bouton désactivé sinon) ;
 * - le détail d'un run affiche ses cas, et un cas SANS exécution reste « Untested »
 *   (aucun résultat fabriqué) ;
 * - le MODE D'EXÉCUTION se choisit à la CRÉATION (2026-08-04) et commande les gestes offerts :
 *   une campagne automatique se lance et ne se saisit pas, une campagne manuelle l'inverse.
 *   ⚠️ C'est le test qui empêche l'écran d'avant de revenir — celui qui proposait les deux
 *   boutons en permanence, sans qu'aucun ne s'impose.
 * - la vue « Tests & Résultats » dit la VÉRITÉ sur la campagne (2026-08-05, parité TestRail) :
 *   le grand chiffre est un taux de RÉUSSITE et non d'avancement, le reste à faire est écrit à
 *   côté, les cas sont groupés par statut avec leur compte, un statut absent ne crée pas de
 *   groupe vide, et la légende du camembert descend de `status.ts` au lieu d'être retapée.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
// ⚠️ Importés pour être COMPARÉS À, jamais recopiés : c'est ce qui rend le test capable de voir
// un écart entre la source unique des statuts et ce que l'écran en fait.
import { TEST_STATUS_ORDER, testStatusMeta } from '../lib/status'
// RunsOverview lit la couche de données (lot A) : sans elle, son `setup()` plante.
import { monter } from './_montage'

const listCases = vi.fn()
const listGroups = vi.fn()
const createRun = vi.fn()
const listRuns = vi.fn()
const getRun = vi.fn()
const launchRun = vi.fn()
const archiveRun = vi.fn()
const push = vi.fn()

vi.mock('../lib/api', () => ({
  api: {
    listCases: (...a: any[]) => listCases(...a),
    // Le picker de cas (étape « sélection figée ») groupe désormais par Section/Sous-section
    // (2026-08-07), pas seulement par Module — il lit `listGroups` via `useGroupes`.
    listGroups: (...a: any[]) => listGroups(...a),
    createRun: (...a: any[]) => createRun(...a),
    listRuns: (...a: any[]) => listRuns(...a),
    getRun: (...a: any[]) => getRun(...a),
    launchRun: (...a: any[]) => launchRun(...a),
    archiveRun: (...a: any[]) => archiveRun(...a),
  },
}))
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pid: '1', id: '7' }, query: {} }),
  useRouter: () => ({ push }),
}))

import AddTestRunForm from '../pages/AddTestRunForm.vue'
import RunsOverview from '../pages/RunsOverview.vue'
import RunDetail from '../pages/RunDetail.vue'

// Deux modules DIFFÉRENTS : une campagne doit pouvoir être TRANSVERSE (§7).
const CAS = [
  { id: 1, title: 'Cas A', module_id: 1, module: 'Facturation' },
  { id: 2, title: 'Cas B', module_id: 2, module: 'Livraison' },
]

beforeEach(() => {
  vi.clearAllMocks()
  // La liste des cas est PAGINÉE depuis le 2026-07-24 : le simulacre rend une page.
  listCases.mockResolvedValue({ items: CAS, next_cursor: null, total: CAS.length })
  listGroups.mockResolvedValue([])
  createRun.mockResolvedValue({ id: 7, name: 'R', status: 'draft', case_count: 2 })
  listRuns.mockResolvedValue([])
  launchRun.mockResolvedValue({ id: 7, status: 'running' })
  archiveRun.mockResolvedValue({ id: 7, is_archived: true })
  getRun.mockResolvedValue({
    run: { id: 7, project_id: 1, name: 'Campagne', status: 'draft', selection_mode: 'frozen',
           mode: 'automatique', case_count: 2, tested_count: 1, is_archived: false,
           created_at: '2026-07-21T10:00:00' },
    description: '', refs: '', statuts_manuels: ['passed', 'failed', 'retest', 'blocked'],
    cases: [
      { id: 1, title: 'Cas A', execution_status: 'success', functional_status: 'conforme',
        execution_id: 30, statut: 'passed', result_mode: 'automatique',
        statut_manuel: '', comment: '', created_by: 'TestPilot',
        result_at: '2026-08-04T10:00:00+00:00' },
      { id: 2, title: 'Cas B', execution_status: null, functional_status: null,
        execution_id: null, statut: 'untested', result_mode: '',
        statut_manuel: '', comment: '', created_by: '', result_at: '' },
    ],
  })
})

describe('AddTestRunForm — création d\'une campagne', () => {
  it('mode « tous les cas » : n\'envoie AUCUNE sélection figée', async () => {
    const w = monter(AddTestRunForm)
    await flushPromises()

    await w.find('form').trigger('submit')
    await flushPromises()

    expect(createRun).toHaveBeenCalledWith('1', expect.objectContaining({
      selection_mode: 'all', case_ids: [],
    }))
  })

  it('le MODE D\'EXÉCUTION part avec la création, et vaut « automatique » par défaut', async () => {
    // ⚠️ Le mode ne se devine plus résultat par résultat : il se choisit ici. Automatique par
    // défaut — le manuel est un choix délibéré, jamais une valeur dans laquelle on tombe.
    const w = monter(AddTestRunForm)
    await flushPromises()

    await w.find('form').trigger('submit')
    await flushPromises()
    expect(createRun).toHaveBeenCalledWith('1', expect.objectContaining({ mode: 'automatique' }))

    createRun.mockClear()
    await w.findAll('input[type="radio"]')[1].setValue()   // « Manuelle »
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(createRun).toHaveBeenCalledWith('1', expect.objectContaining({ mode: 'manuelle' }))
  })

  it('sélection figée : exige au moins un cas coché', async () => {
    const w = monter(AddTestRunForm)
    await flushPromises()
    await w.findAll('input[type="radio"]')[3].setValue()
    await flushPromises()

    const submit = w.findAll('button').find((b) => b.text().includes('Ajouter une exécution'))!
    expect(submit.attributes('disabled')).toBeDefined()

    await w.find('input[type="checkbox"]').setValue(true)
    await flushPromises()
    expect(submit.attributes('disabled')).toBeUndefined()
  })

  it('permet une sélection TRANSVERSE : cas de plusieurs modules (§7)', async () => {
    // Le JTBD « régression transverse » : une campagne pioche dans plusieurs modules. Le backend
    // le permet ; l'écran doit le rendre VISIBLE (groupes par module + mention « Transverse »).
    const w = monter(AddTestRunForm)
    await flushPromises()
    await w.findAll('input[type="radio"]')[3].setValue()
    await flushPromises()

    expect(w.text()).toContain('Facturation')
    expect(w.text()).toContain('Livraison')

    const boxes = w.findAll('input[type="checkbox"]')
    await boxes[0].setValue(true)   // Cas A — Facturation
    await boxes[1].setValue(true)   // Cas B — Livraison
    await flushPromises()

    expect(w.text()).toContain('Transverse — 2 modules')

    await w.find('form').trigger('submit')
    await flushPromises()
    expect(createRun).toHaveBeenCalledWith('1', expect.objectContaining({
      selection_mode: 'frozen', case_ids: [1, 2],
    }))
  })
})

describe('RunsOverview — liste des campagnes', () => {
  it('invite à créer quand il n\'y a aucune campagne', async () => {
    const w = monter(RunsOverview)
    await flushPromises()
    expect(w.text()).toContain('Aucune exécution pour ce projet')
  })

  it('affiche le % de complétion (note fonctionnelle)', async () => {
    listRuns.mockResolvedValue([{ id: 7, project_id: 1, name: 'Campagne', status: 'running',
                                  selection_mode: 'all', case_count: 4, tested_count: 1,
                                  is_archived: false, created_at: '2026-07-21T10:00:00' }])
    const w = monter(RunsOverview)
    await flushPromises()

    expect(w.text()).toContain('1/4 cas testés')
    expect(w.text()).toContain('25 %')
  })
})

describe('RunDetail — les cas du run et leur résultat', () => {
  it('liste les cas avec leur statut, « Untested » si non exécuté', async () => {
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('Cas A')
    expect(w.text()).toContain('Cas B')
    expect(w.text()).toContain('Passed')     // Cas A : success/conforme
    expect(w.text()).toContain('Untested')   // Cas B : aucune exécution dans ce run
  })

  it('dit ce que la campagne VAUT et ce qui n\'a rien prouvé, sans confondre les deux', async () => {
    // ⚠️ L'écran affichait « 50 % » pour dire « la moitié des cas ont TOURNÉ ». Lu vite, ce
    // chiffre passait pour un taux de réussite : une campagne dont tous les cas échouent aurait
    // affiché « 100 % ». Le grand chiffre dit désormais la RÉUSSITE (cas verts / total), et le
    // reste à faire est écrit juste en dessous, en toutes lettres.
    // Simulacre : 2 cas, 1 Passed, 1 Untested.
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('50 %')
    expect(w.text()).toContain('réussi')
    expect(w.text()).toContain('1 / 2 non testés (50 %)')
  })

  it('la légende du camembert vient de `status.ts`, pas d\'une liste retapée', async () => {
    // ⚠️ Une liste de statuts recopiée dans l'écran est une deuxième source de vérité : le jour
    // où un statut est ajouté ou renommé dans `status.ts`, le graphique continue d'afficher
    // l'ancienne — sans que rien n'échoue. Le test compare donc à l'ordre canonique lui-même.
    const w = mount(RunDetail)
    await flushPromises()

    const texte = w.text()
    for (const code of TEST_STATUS_ORDER) {
      const libelle = testStatusMeta(code).label
      expect(texte, `« ${libelle} » manque à la légende`).toContain(libelle)
      expect(texte).toContain(`% défini sur ${libelle}`)
    }
    // Un camembert = un arc par statut PRÉSENT (2 ici), jamais un arc à zéro degré.
    expect(w.findAll('svg[role="img"] path')).toHaveLength(2)
  })

  it('groupe les cas par statut, chaque groupe portant son compte', async () => {
    // Le regroupement de TestRail : un bandeau par statut, avec le nombre de cas qu'il contient.
    // Le compte est ce qui empêche le bandeau de mentir par omission quand la liste est longue.
    const w = mount(RunDetail)
    await flushPromises()

    const bandeaux = w.findAll('section')
    expect(bandeaux).toHaveLength(2)          // Passed et Untested, dans l'ordre canonique
    expect(bandeaux[0].text()).toContain('Passed')
    expect(bandeaux[0].text()).toContain('Cas A')
    expect(bandeaux[1].text()).toContain('Untested')
    expect(bandeaux[1].text()).toContain('Cas B')
  })

  it('un statut ABSENT ne crée aucun groupe vide', async () => {
    // ⚠️ Dérouler cinq bandeaux dont trois sont vides ferait passer pour « une campagne qui a du
    // Blocked » une campagne qui n'en a aucun : on retient les intitulés, pas les zéros.
    const w = mount(RunDetail)
    await flushPromises()

    const bandeaux = w.findAll('section').map((s) => s.text())
    expect(bandeaux.some((t) => t.startsWith('Blocked'))).toBe(false)
    expect(bandeaux.some((t) => t.startsWith('Failed'))).toBe(false)
  })

  it('dit COMMENT chaque résultat a été obtenu — et rien du tout quand il n\'y en a pas', async () => {
    // ⚠️ L'invariant du produit : un résultat manuel ne doit JAMAIS pouvoir passer pour un
    // résultat automatique. Le mode est donc écrit en toutes lettres sur chaque ligne.
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('Automatique')   // Cas A : une machine l'a produit
    // Cas B n'a AUCUN résultat : pas de pastille du tout. Une pastille « inconnu » laisserait
    // croire qu'un résultat existe mais qu'on ignore comment il a été obtenu.
    expect(w.text()).not.toContain('Manuelle')
  })

  it('affiche « Manuelle » quand un humain a joué le cas, sans les deux axes', async () => {
    getRun.mockResolvedValue({
      run: { id: 7, project_id: 1, name: 'Campagne', status: 'completed', selection_mode: 'frozen',
             mode: 'manuelle', case_count: 1, tested_count: 1, manuel_count: 1,
             is_archived: false, created_at: '' },
      description: '', refs: '', target_url: '', target_database: '', target_mixed: false,
      statuts_manuels: ['passed', 'failed', 'retest', 'blocked'],
      cases: [
        // Un résultat MANUEL ne porte aucun des deux axes : aucune machine n'a rien mesuré.
        { id: 1, title: 'Cas A', execution_status: null, functional_status: null,
          execution_id: null, statut: 'blocked', result_mode: 'manuelle',
          statut_manuel: 'blocked', comment: 'environnement indisponible',
          created_by: 'Romaric', result_at: '2026-08-04T11:00:00+00:00' },
      ],
    })
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('Manuelle')
    expect(w.text()).toContain('Blocked')
    expect(w.text()).not.toContain('Automatique')
  })
})

describe('RunDetail — le MODE de la campagne commande les gestes offerts', () => {
  // ⚠️ **Le défaut que ces deux tests empêchent de revenir.** Avant le 2026-08-04, chaque ligne
  // portait « + Résultat » ET l'en-tête portait « Lancer », quelle que soit la campagne : deux
  // gestes proposés en permanence, aucun qui s'impose, et un utilisateur qui choisit au hasard —
  // donc un historique où le manuel et l'automatique se mélangent sans que personne l'ait voulu.
  it('automatique : « Lancer » est là, « + Résultat » n\'existe pas', async () => {
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.findAll('button').find((b) => b.text().includes("Lancer l'exécution"))).toBeDefined()
    expect(w.findAll('button').find((b) => b.text().includes('+ Résultat'))).toBeUndefined()
  })

  it('manuelle : aucun « Lancer », et « + Résultat » sur chaque ligne', async () => {
    getRun.mockResolvedValue({
      run: { id: 7, project_id: 1, name: 'Recette manuelle', status: 'draft',
             selection_mode: 'frozen', mode: 'manuelle', case_count: 2, tested_count: 0,
             manuel_count: 0, is_archived: false, created_at: '' },
      description: '', refs: '', target_url: '', target_database: '', target_mixed: false,
      statuts_manuels: ['passed', 'failed', 'retest', 'blocked'],
      cases: [
        { id: 1, title: 'Cas A', execution_status: null, functional_status: null,
          execution_id: null, statut: 'untested', result_mode: '', statut_manuel: '',
          comment: '', created_by: '', result_at: '' },
        { id: 2, title: 'Cas B', execution_status: null, functional_status: null,
          execution_id: null, statut: 'untested', result_mode: '', statut_manuel: '',
          comment: '', created_by: '', result_at: '' },
      ],
    })
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.findAll('button').find((b) => b.text().includes("Lancer l'exécution"))).toBeUndefined()
    expect(w.findAll('button').filter((b) => b.text().includes('+ Résultat'))).toHaveLength(2)
  })
})

describe('RunDetail — lancement de la campagne', () => {
  it('propose « Lancer » sur un brouillon et appelle le backend', async () => {
    const w = mount(RunDetail)
    await flushPromises()

    const btn = w.findAll('button').find((b) => b.text().includes("Lancer l'exécution"))!
    expect(btn).toBeDefined()
    await btn.trigger('click')
    await flushPromises()

    expect(launchRun).toHaveBeenCalledWith(7)
  })

  it("pendant l'exécution : pas de bouton, avancement affiché", async () => {
    getRun.mockResolvedValue({
      run: { id: 7, project_id: 1, name: 'C', status: 'running', selection_mode: 'frozen',
             case_count: 2, tested_count: 1, is_archived: false, created_at: '2026-07-21T10:00:00' },
      description: '', refs: '',
      cases: [
        { id: 1, title: 'A', execution_status: 'success', functional_status: 'conforme',
          execution_id: 30, statut: 'passed' },
        { id: 2, title: 'B', execution_status: null, functional_status: null,
          execution_id: null, statut: 'untested' },
      ],
    })
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('Exécution en cours')
    expect(w.findAll('button').find((b) => b.text().includes("Lancer l'exécution"))).toBeUndefined()
  })

  it('propose « Relancer » quand la campagne est terminée', async () => {
    getRun.mockResolvedValue({
      run: { id: 7, project_id: 1, name: 'C', status: 'completed', selection_mode: 'frozen',
             case_count: 1, tested_count: 1, is_archived: false, created_at: '2026-07-21T10:00:00' },
      description: '', refs: '',
      cases: [{ id: 1, title: 'A', execution_status: 'success', functional_status: 'conforme', execution_id: 30 }],
    })
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.findAll('button').find((b) => b.text().includes('Relancer'))).toBeDefined()
  })
})

describe('RunDetail — archivage (lecture seule, reversible)', () => {
  it('cloture la campagne', async () => {
    const w = mount(RunDetail)
    await flushPromises()

    await w.findAll('button').find((b) => b.text() === 'Clôturer')!.trigger('click')
    await flushPromises()

    expect(archiveRun).toHaveBeenCalledWith(7, true)
  })

  it('archivee : bandeau affiche, plus de bouton Lancer, « Rouvrir » propose', async () => {
    getRun.mockResolvedValue({
      run: { id: 7, project_id: 1, name: 'C', status: 'completed', selection_mode: 'frozen',
             case_count: 1, tested_count: 1, is_archived: true, created_at: '2026-07-21T10:00:00' },
      description: '', refs: '',
      cases: [{ id: 1, title: 'A', execution_status: 'success', functional_status: 'conforme', execution_id: 30 }],
    })
    const w = mount(RunDetail)
    await flushPromises()

    expect(w.text()).toContain('archivée')
    expect(w.findAll('button').find((b) => b.text().includes('Relancer'))).toBeUndefined()
    expect(w.findAll('button').find((b) => b.text() === 'Rouvrir')).toBeDefined()
  })
})

describe('RunsOverview — les archivees ne polluent pas la vue de travail', () => {
  it('separe les archivees, repliees par defaut', async () => {
    listRuns.mockResolvedValue([
      { id: 7, project_id: 1, name: 'Active', status: 'draft', selection_mode: 'all',
        case_count: 2, tested_count: 0, is_archived: false, created_at: '2026-07-21T10:00:00' },
      { id: 8, project_id: 1, name: 'Ancienne', status: 'completed', selection_mode: 'all',
        case_count: 2, tested_count: 2, is_archived: true, created_at: '2026-07-20T10:00:00' },
    ])
    const w = monter(RunsOverview)
    await flushPromises()

    expect(w.text()).toContain('Active')
    expect(w.text()).toContain('Archivées (1)')
    expect(w.text()).not.toContain('Ancienne')   // repliee

    await w.findAll('button').find((b) => b.text().includes('Archivées'))!.trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Ancienne')
  })
})
